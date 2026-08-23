"""API service layer — business logic extracted from routers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from webtwin_core.evaluation.runs import EvaluationRun
from webtwin_core.investigation.session_sync import sync_session_from_investigation
from webtwin_core.investigation.state_machine import InvalidTransitionError, apply_transition
from webtwin_core.models import (
    ApplicationState,
    AuthPauseMetadata,
    AuthState,
    BusinessRule,
    Evidence,
    EvidenceType,
    Investigation,
    InvestigationSession,
    InvestigationStatus,
    Observation,
    SessionStatus,
    StateDiff,
    TimelineEvent,
    compute_state_diff,
    infer_candidate_rules,
)
from webtwin_core.models.investigation import InvestigationTransition, TransitionEvent
from webtwin_core.verification.engine import VerificationRun

from api.store import store


class TransitionRequest(BaseModel):
    event: TransitionEvent
    reason: str | None = None
    auth_pause: AuthPauseMetadata | None = None


class SessionUpdateRequest(BaseModel):
    auth_state: AuthState | None = None
    storage_state_ref: str | None = None
    role_scope: str | None = None


class SessionPublic(BaseModel):
    id: UUID
    investigation_id: UUID
    auth_state: AuthState
    session_status: SessionStatus
    has_persisted_storage: bool
    human_ready: bool
    auth_verified: bool
    checkpoint_status: InvestigationStatus | None = None
    created_at: datetime
    updated_at: datetime


class InvestigationDetail(BaseModel):
    investigation: Investigation
    session: SessionPublic | None = None


class RuleProvenance(BaseModel):
    rule: BusinessRule
    evidence: list[Evidence]
    experiments: list[VerificationRun]


def get_investigation(investigation_id: UUID) -> Investigation:
    investigation = store.investigations.get(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


def get_rule(rule_id: UUID) -> BusinessRule:
    rule = store.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def get_or_create_session(investigation: Investigation) -> InvestigationSession:
    if investigation.session_id is not None and investigation.session_id in store.sessions:
        return store.sessions[investigation.session_id]

    session = InvestigationSession(investigation_id=investigation.id)
    store.sessions[session.id] = session
    investigation.session_id = session.id
    store.investigations[investigation.id] = investigation
    return session


def last_transition(investigation_id: UUID) -> InvestigationTransition | None:
    transitions = [
        transition
        for transition in store.transitions.values()
        if transition.investigation_id == investigation_id
    ]
    if not transitions:
        return None
    return max(transitions, key=lambda transition: transition.occurred_at)


def observation_count(investigation_id: UUID) -> int:
    return sum(
        1 for observation in store.observations.values() if observation.investigation_id == investigation_id
    )


def to_session_public(session: InvestigationSession) -> SessionPublic:
    return SessionPublic(
        id=session.id,
        investigation_id=session.investigation_id,
        auth_state=session.auth_state,
        session_status=session.session_status,
        has_persisted_storage=session.storage_state_ref is not None,
        human_ready=session.human_ready_at is not None,
        auth_verified=session.auth_verified_at is not None,
        checkpoint_status=session.checkpoint.status if session.checkpoint else None,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def save_session(session: InvestigationSession) -> SessionPublic:
    session.updated_at = datetime.now(UTC)
    store.sessions[session.id] = session
    return to_session_public(session)


def create_investigation(investigation: Investigation) -> Investigation:
    investigation.status = InvestigationStatus.CREATED
    store.investigations[investigation.id] = investigation
    session = get_or_create_session(investigation)
    session.session_status = SessionStatus.NOT_STARTED
    save_session(session)
    return investigation


def list_investigations() -> list[Investigation]:
    return list(store.investigations.values())


def list_pending_investigations() -> list[Investigation]:
    """Investigations waiting for a browser worker (created, or orphaned auth pause)."""
    return [
        item
        for item in store.investigations.values()
        if item.status
        in {
            InvestigationStatus.CREATED,
            InvestigationStatus.AUTH_REQUIRED,
        }
    ]


def claim_investigation(investigation_id: UUID) -> Investigation:
    """Atomically claim a created (or orphaned auth_required) investigation for the worker."""
    investigation = get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTH_REQUIRED:
        # Worker crashed mid-login — allow reclaim without resetting to created.
        return investigation
    if investigation.status != InvestigationStatus.CREATED:
        raise HTTPException(status_code=409, detail="Investigation is not claimable")
    return transition_investigation(
        investigation_id,
        TransitionRequest(event=TransitionEvent.START, reason="claimed_by_worker"),
    )


def transition_investigation(investigation_id: UUID, request: TransitionRequest) -> Investigation:
    investigation = get_investigation(investigation_id)
    previous = investigation.status
    try:
        new_status = apply_transition(
            investigation,
            request.event,
            request.reason,
            auth_pause=request.auth_pause,
            last_transition=last_transition(investigation_id),
            observation_count=observation_count(investigation_id),
        )
    except InvalidTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if new_status is None:
        return investigation

    record = InvestigationTransition(
        investigation_id=investigation_id,
        from_status=previous,
        to_status=new_status,
        event=request.event,
        reason=request.reason,
    )
    store.transitions[record.id] = record
    store.investigations[investigation.id] = investigation

    session = get_or_create_session(investigation)
    session.checkpoint = investigation.checkpoint
    sync_session_from_investigation(session, investigation)
    if request.event == TransitionEvent.AUTH_REQUIRED:
        session.human_ready_at = None
        session.auth_verified_at = None
    save_session(session)

    if new_status == InvestigationStatus.COMPLETED:
        try:
            discover_workflows_from_diffs(investigation_id)
        except Exception:
            pass
        try:
            sync_knowledge_graph(investigation_id)
        except Exception:
            pass

    return investigation


def resume_failed(investigation_id: UUID) -> Investigation:
    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed investigations can use /resume")
    if investigation.checkpoint is None:
        raise HTTPException(status_code=409, detail="No checkpoint available to resume")
    return transition_investigation(investigation_id, TransitionRequest(event=TransitionEvent.RESUME))


def restart_failed(investigation_id: UUID) -> Investigation:
    """Re-queue a failed investigation with no usable checkpoint (worker can claim again)."""
    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed investigations can use /restart")
    investigation.status = InvestigationStatus.CREATED
    investigation.failure_reason = None
    investigation.blocked_reason = None
    investigation.auth_pause = None
    investigation.checkpoint = None
    investigation.updated_at = datetime.now(UTC)
    store.investigations[investigation.id] = investigation
    session = get_or_create_session(investigation)
    session.session_status = SessionStatus.NOT_STARTED
    session.auth_state = AuthState.UNKNOWN
    session.human_ready_at = None
    session.checkpoint = None
    save_session(session)
    return investigation


def begin_authentication(investigation_id: UUID) -> SessionPublic:
    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    session = get_or_create_session(investigation)
    if (
        session.auth_state == AuthState.AUTHENTICATED
        and session.storage_state_ref
        and session.session_status == SessionStatus.AUTHENTICATED
    ):
        return to_session_public(session)

    session.session_status = SessionStatus.AUTHENTICATING
    session.auth_state = AuthState.REQUIRED
    session.human_ready_at = None
    return save_session(session)


def mark_authentication_ready(investigation_id: UUID) -> SessionPublic:
    investigation = get_investigation(investigation_id)
    session = get_or_create_session(investigation)

    if investigation.status == InvestigationStatus.AUTHENTICATED:
        return to_session_public(session)

    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    if session.session_status not in {SessionStatus.AUTHENTICATING, SessionStatus.AUTHENTICATED}:
        raise HTTPException(status_code=409, detail="Open the browser and begin authentication first")

    session.human_ready_at = datetime.now(UTC)
    return save_session(session)


def resume_after_authentication(investigation_id: UUID) -> Investigation:
    investigation = get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTHENTICATED:
        return investigation

    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    session = get_or_create_session(investigation)
    if session.human_ready_at is None:
        raise HTTPException(status_code=409, detail="Confirm authentication completion before resuming")
    if session.auth_state != AuthState.AUTHENTICATED or not session.storage_state_ref:
        raise HTTPException(
            status_code=409,
            detail="Authentication not verified — browser session must confirm login before resume",
        )

    session.auth_verified_at = datetime.now(UTC)
    session.session_status = SessionStatus.AUTHENTICATED
    save_session(session)
    return transition_investigation(
        investigation_id, TransitionRequest(event=TransitionEvent.AUTH_COMPLETED)
    )


def upsert_session(investigation_id: UUID, request: SessionUpdateRequest) -> SessionPublic:
    investigation = get_investigation(investigation_id)
    session = get_or_create_session(investigation)

    if request.auth_state is not None:
        session.auth_state = request.auth_state
        if request.auth_state == AuthState.AUTHENTICATED:
            session.auth_verified_at = datetime.now(UTC)
            session.session_status = SessionStatus.AUTHENTICATED
    if request.storage_state_ref is not None:
        session.storage_state_ref = request.storage_state_ref
    if investigation.checkpoint is not None:
        session.checkpoint = investigation.checkpoint
    if request.role_scope is not None:
        investigation.role_scope = request.role_scope
        store.investigations[investigation.id] = investigation

    if request.auth_state != AuthState.AUTHENTICATED:
        sync_session_from_investigation(session, investigation)
    return save_session(session)


def get_session(investigation_id: UUID) -> SessionPublic:
    investigation = get_investigation(investigation_id)
    if investigation.session_id is None or investigation.session_id not in store.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return to_session_public(store.sessions[investigation.session_id])


def get_detail(investigation_id: UUID) -> InvestigationDetail:
    investigation = get_investigation(investigation_id)
    session = None
    if investigation.session_id and investigation.session_id in store.sessions:
        session = to_session_public(store.sessions[investigation.session_id])
    return InvestigationDetail(investigation=investigation, session=session)


def get_transitions(investigation_id: UUID) -> list[InvestigationTransition]:
    get_investigation(investigation_id)
    return [
        transition
        for transition in store.transitions.values()
        if transition.investigation_id == investigation_id
    ]


def record_observation(investigation_id: UUID, observation: Observation) -> Observation:
    get_investigation(investigation_id)
    store.observations[observation.id] = observation
    # Persist screenshot as first-class evidence when path is present (H4)
    if observation.screenshot_path:
        shot = Evidence(
            investigation_id=investigation_id,
            type=EvidenceType.SCREENSHOT,
            url=observation.url,
            artifact_uri=observation.screenshot_path,
            payload={"observation_id": str(observation.id), "label": "observation"},
        )
        store.evidence[shot.id] = shot
    return observation


def record_state(investigation_id: UUID, state: ApplicationState) -> ApplicationState:
    get_investigation(investigation_id)
    store.states[state.id] = state
    return state


def record_event(investigation_id: UUID, event: TimelineEvent) -> TimelineEvent:
    get_investigation(investigation_id)
    store.events[event.id] = event
    return event


def record_evidence(investigation_id: UUID, evidence: Evidence) -> Evidence:
    get_investigation(investigation_id)
    store.evidence[evidence.id] = evidence

    if evidence.type == EvidenceType.NETWORK:
        # Persist network_events store entry
        if not hasattr(store, "network_events"):
            store.network_events = {}
        raw_id = (evidence.payload or {}).get("network_event_id")
        try:
            event_id = UUID(str(raw_id)) if raw_id else evidence.id
        except Exception:
            event_id = evidence.id
        store.network_events[event_id] = {
            "id": str(event_id),
            "investigation_id": str(investigation_id),
            "timeline_event_id": (evidence.payload or {}).get("timeline_event_id"),
            "method": (evidence.payload or {}).get("method"),
            "url": evidence.url,
            "status_code": (evidence.payload or {}).get("status_code"),
            "body_shape": (evidence.payload or {}).get("body_shape") or {},
            "request_headers": (evidence.payload or {}).get("request_headers") or {},
            "response_headers": (evidence.payload or {}).get("response_headers") or {},
            "evidence_id": str(evidence.id),
        }
        # Supporting evidence only — attach to existing rules
        for rule in store.rules.values():
            if rule.investigation_id != investigation_id:
                continue
            if evidence.id not in rule.evidence_ids:
                rule.evidence_ids.append(evidence.id)
                store.rules[rule.id] = rule

    return evidence


def diff_states(investigation_id: UUID, before_state_id: UUID, after_state_id: UUID) -> StateDiff:
    get_investigation(investigation_id)
    before = store.states.get(before_state_id)
    after = store.states.get(after_state_id)
    if before is None or after is None:
        raise HTTPException(status_code=404, detail="State not found")

    diff = compute_state_diff(before, after)
    store.diffs[diff.id] = diff

    for rule in infer_candidate_rules(diff, before, after):
        evidence = Evidence(
            investigation_id=investigation_id,
            type=EvidenceType.DOM,
            payload={
                "state_transition_id": str(diff.id),
                "before_state_id": str(before.id),
                "after_state_id": str(after.id),
                "summary": diff.summary,
            },
            url=after.url,
        )
        store.evidence[evidence.id] = evidence
        rule.evidence_ids.append(evidence.id)
        store.rules[rule.id] = rule

    return diff


def verify_rule(
    investigation_id: UUID,
    rule_id: UUID,
    verification_run: VerificationRun,
) -> BusinessRule:
    get_investigation(investigation_id)
    rule = get_rule(rule_id)
    if rule.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Rule not found for investigation")

    store.verification_runs[verification_run.id] = verification_run
    rule.status = verification_run.status
    rule.confidence = verification_run.confidence
    if verification_run.id not in rule.verification_run_ids:
        rule.verification_run_ids.append(verification_run.id)
    store.rules[rule.id] = rule
    return rule


def list_timeline(investigation_id: UUID) -> list[TimelineEvent]:
    get_investigation(investigation_id)
    return [event for event in store.events.values() if event.investigation_id == investigation_id]


def list_rules(investigation_id: UUID) -> list[BusinessRule]:
    get_investigation(investigation_id)
    return [rule for rule in store.rules.values() if rule.investigation_id == investigation_id]


def list_observations(investigation_id: UUID) -> list[Observation]:
    get_investigation(investigation_id)
    return [item for item in store.observations.values() if item.investigation_id == investigation_id]


def list_states(investigation_id: UUID) -> list[ApplicationState]:
    get_investigation(investigation_id)
    return [item for item in store.states.values() if item.investigation_id == investigation_id]


def list_diffs(investigation_id: UUID) -> list[StateDiff]:
    get_investigation(investigation_id)
    return [item for item in store.diffs.values() if item.investigation_id == investigation_id]


def list_evidence(investigation_id: UUID) -> list[Evidence]:
    get_investigation(investigation_id)
    return [item for item in store.evidence.values() if item.investigation_id == investigation_id]


def get_rule_provenance(investigation_id: UUID, rule_id: UUID) -> RuleProvenance:
    get_investigation(investigation_id)
    rule = get_rule(rule_id)
    if rule.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Rule not found for investigation")
    evidence = [store.evidence[eid] for eid in rule.evidence_ids if eid in store.evidence]
    experiments = [
        store.verification_runs[rid]
        for rid in rule.verification_run_ids
        if rid in store.verification_runs
    ]
    return RuleProvenance(rule=rule, evidence=evidence, experiments=experiments)


def save_evaluation_run(investigation_id: UUID, run: EvaluationRun) -> EvaluationRun:
    get_investigation(investigation_id)
    run.investigation_id = investigation_id
    store.evaluation_runs[run.id] = run
    return run


def list_metrics(investigation_id: UUID) -> list[EvaluationRun]:
    get_investigation(investigation_id)
    return [item for item in store.evaluation_runs.values() if item.investigation_id == investigation_id]


def ask_question(investigation_id: UUID, question: str):
    from webtwin_core.qa import answer_from_evidence
    from webtwin_core.qa.models import QuestionAnswer

    get_investigation(investigation_id)
    rules = list_rules(investigation_id)
    evidence = list_evidence(investigation_id)
    answer: QuestionAnswer = answer_from_evidence(question, rules, evidence)
    return answer


def list_workflows(investigation_id: UUID):
    from webtwin_core.models.workflow import Workflow

    get_investigation(investigation_id)
    workflows = getattr(store, "workflows", {})
    return [item for item in workflows.values() if item.investigation_id == investigation_id]


def save_workflow(investigation_id: UUID, workflow):
    get_investigation(investigation_id)
    workflow.investigation_id = investigation_id
    if not hasattr(store, "workflows"):
        store.workflows = {}
    store.workflows[workflow.id] = workflow
    return workflow


def discover_workflows_from_diffs(investigation_id: UUID):
    """Lightweight causal chains from ordered state diffs."""
    from webtwin_core.models.workflow import Workflow, WorkflowStep

    get_investigation(investigation_id)
    diffs = sorted(list_diffs(investigation_id), key=lambda item: str(item.id))
    if len(diffs) < 1:
        return []

    steps = [
        WorkflowStep(
            order=index,
            description=diff.summary or "state transition",
            from_state_id=diff.before_state_id,
            to_state_id=diff.after_state_id,
        )
        for index, diff in enumerate(diffs[:12])
    ]
    workflow = Workflow(
        investigation_id=investigation_id,
        name=f"Observed transitions ({len(steps)} steps)",
        steps=steps,
        confidence=0.5 if len(steps) >= 2 else 0.3,
        role_scope=get_investigation(investigation_id).role_scope,
    )
    return [save_workflow(investigation_id, workflow)]


def sync_knowledge_graph(investigation_id: UUID) -> dict:
    from api.kg.sync import sync_investigation_to_kg

    investigation = get_investigation(investigation_id)
    return sync_investigation_to_kg(
        investigation_id=investigation.id,
        application_name=investigation.application_name,
        target_url=investigation.target_url,
        rules=list_rules(investigation_id),
        evidence=list_evidence(investigation_id),
        role_scope=investigation.role_scope,
        application_version=investigation.application_version,
        environment=investigation.environment,
    )
