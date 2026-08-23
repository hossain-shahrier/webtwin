from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
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

router = APIRouter(prefix="/investigations", tags=["investigations"])


class TransitionRequest(BaseModel):
    event: TransitionEvent
    reason: str | None = None
    auth_pause: AuthPauseMetadata | None = None


class SessionUpdateRequest(BaseModel):
    auth_state: AuthState | None = None
    storage_state_ref: str | None = None


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


def _get_investigation(investigation_id: UUID) -> Investigation:
    investigation = store.investigations.get(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


def _get_rule(rule_id: UUID) -> BusinessRule:
    rule = store.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def _get_or_create_session(investigation: Investigation) -> InvestigationSession:
    if investigation.session_id is not None and investigation.session_id in store.sessions:
        return store.sessions[investigation.session_id]

    session = InvestigationSession(investigation_id=investigation.id)
    store.sessions[session.id] = session
    investigation.session_id = session.id
    store.investigations[investigation.id] = investigation
    return session


def _last_transition(investigation_id: UUID) -> InvestigationTransition | None:
    transitions = [
        transition
        for transition in store.transitions.values()
        if transition.investigation_id == investigation_id
    ]
    if not transitions:
        return None
    return max(transitions, key=lambda transition: transition.occurred_at)


def _observation_count(investigation_id: UUID) -> int:
    return sum(
        1 for observation in store.observations.values() if observation.investigation_id == investigation_id
    )


def _to_session_public(session: InvestigationSession) -> SessionPublic:
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


def _save_session(session: InvestigationSession) -> SessionPublic:
    session.updated_at = datetime.now(UTC)
    store.sessions[session.id] = session
    return _to_session_public(session)


@router.post("", response_model=Investigation, status_code=201)
def create_investigation(investigation: Investigation) -> Investigation:
    investigation.status = InvestigationStatus.CREATED
    store.investigations[investigation.id] = investigation
    session = _get_or_create_session(investigation)
    session.session_status = SessionStatus.NOT_STARTED
    _save_session(session)
    return investigation


@router.post("/{investigation_id}/transition", response_model=Investigation)
def transition_investigation(
    investigation_id: UUID,
    request: TransitionRequest,
) -> Investigation:
    investigation = _get_investigation(investigation_id)
    previous = investigation.status
    try:
        new_status = apply_transition(
            investigation,
            request.event,
            request.reason,
            auth_pause=request.auth_pause,
            last_transition=_last_transition(investigation_id),
            observation_count=_observation_count(investigation_id),
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

    session = _get_or_create_session(investigation)
    session.checkpoint = investigation.checkpoint
    sync_session_from_investigation(session, investigation)
    if request.event == TransitionEvent.AUTH_REQUIRED:
        session.human_ready_at = None
        session.auth_verified_at = None
    _save_session(session)

    return investigation


@router.post("/{investigation_id}/resume", response_model=Investigation)
def resume_investigation(investigation_id: UUID) -> Investigation:
    investigation = _get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed investigations can use /resume")
    if investigation.checkpoint is None:
        raise HTTPException(status_code=409, detail="No checkpoint available to resume")

    request = TransitionRequest(event=TransitionEvent.RESUME)
    return transition_investigation(investigation_id, request)


@router.post("/{investigation_id}/auth/begin", response_model=SessionPublic)
def begin_authentication(investigation_id: UUID) -> SessionPublic:
    investigation = _get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    session = _get_or_create_session(investigation)
    if (
        session.auth_state == AuthState.AUTHENTICATED
        and session.storage_state_ref
        and session.session_status == SessionStatus.AUTHENTICATED
    ):
        return _to_session_public(session)

    session.session_status = SessionStatus.AUTHENTICATING
    session.auth_state = AuthState.REQUIRED
    session.human_ready_at = None
    return _save_session(session)


@router.post("/{investigation_id}/auth/mark-ready", response_model=SessionPublic)
def mark_authentication_ready(investigation_id: UUID) -> SessionPublic:
    investigation = _get_investigation(investigation_id)
    session = _get_or_create_session(investigation)

    if investigation.status == InvestigationStatus.AUTHENTICATED:
        return _to_session_public(session)

    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    if session.session_status not in {SessionStatus.AUTHENTICATING, SessionStatus.AUTHENTICATED}:
        raise HTTPException(status_code=409, detail="Open the browser and begin authentication first")

    session.human_ready_at = datetime.now(UTC)
    return _save_session(session)


@router.post("/{investigation_id}/auth/resume", response_model=Investigation)
def resume_after_authentication(investigation_id: UUID) -> Investigation:
    investigation = _get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTHENTICATED:
        return investigation

    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    session = _get_or_create_session(investigation)
    if session.human_ready_at is None:
        raise HTTPException(status_code=409, detail="Confirm authentication completion before resuming")
    if session.auth_state != AuthState.AUTHENTICATED or not session.storage_state_ref:
        raise HTTPException(
            status_code=409,
            detail="Authentication not verified — browser session must confirm login before resume",
        )

    session.auth_verified_at = datetime.now(UTC)
    session.session_status = SessionStatus.AUTHENTICATED
    _save_session(session)

    request = TransitionRequest(event=TransitionEvent.AUTH_COMPLETED)
    return transition_investigation(investigation_id, request)


@router.post("/{investigation_id}/session", response_model=SessionPublic)
def upsert_session(investigation_id: UUID, request: SessionUpdateRequest) -> SessionPublic:
    investigation = _get_investigation(investigation_id)
    session = _get_or_create_session(investigation)

    if request.auth_state is not None:
        session.auth_state = request.auth_state
        if request.auth_state == AuthState.AUTHENTICATED:
            session.auth_verified_at = datetime.now(UTC)
            session.session_status = SessionStatus.AUTHENTICATED
    if request.storage_state_ref is not None:
        session.storage_state_ref = request.storage_state_ref
    if investigation.checkpoint is not None:
        session.checkpoint = investigation.checkpoint

    if request.auth_state != AuthState.AUTHENTICATED:
        sync_session_from_investigation(session, investigation)
    return _save_session(session)


@router.get("/{investigation_id}/session", response_model=SessionPublic)
def get_session(investigation_id: UUID) -> SessionPublic:
    investigation = _get_investigation(investigation_id)
    if investigation.session_id is None or investigation.session_id not in store.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_session_public(store.sessions[investigation.session_id])


@router.get("/{investigation_id}/detail", response_model=InvestigationDetail)
def get_investigation_detail(investigation_id: UUID) -> InvestigationDetail:
    investigation = _get_investigation(investigation_id)
    session = None
    if investigation.session_id and investigation.session_id in store.sessions:
        session = _to_session_public(store.sessions[investigation.session_id])
    return InvestigationDetail(investigation=investigation, session=session)


@router.get("/{investigation_id}/transitions", response_model=list[InvestigationTransition])
def get_transitions(investigation_id: UUID) -> list[InvestigationTransition]:
    _get_investigation(investigation_id)
    return [
        transition
        for transition in store.transitions.values()
        if transition.investigation_id == investigation_id
    ]


@router.get("/{investigation_id}", response_model=Investigation)
def get_investigation(investigation_id: UUID) -> Investigation:
    return _get_investigation(investigation_id)


@router.get("", response_model=list[Investigation])
def list_investigations() -> list[Investigation]:
    return list(store.investigations.values())


@router.post("/{investigation_id}/observations", response_model=Observation, status_code=201)
def record_observation(investigation_id: UUID, observation: Observation) -> Observation:
    _get_investigation(investigation_id)
    store.observations[observation.id] = observation
    return observation


@router.post("/{investigation_id}/states", response_model=ApplicationState, status_code=201)
def record_state(investigation_id: UUID, state: ApplicationState) -> ApplicationState:
    _get_investigation(investigation_id)
    store.states[state.id] = state
    return state


@router.post("/{investigation_id}/events", response_model=TimelineEvent, status_code=201)
def record_event(investigation_id: UUID, event: TimelineEvent) -> TimelineEvent:
    _get_investigation(investigation_id)
    store.events[event.id] = event
    return event


@router.post("/{investigation_id}/evidence", response_model=Evidence, status_code=201)
def record_evidence(investigation_id: UUID, evidence: Evidence) -> Evidence:
    _get_investigation(investigation_id)
    store.evidence[evidence.id] = evidence
    return evidence


@router.post("/{investigation_id}/diff", response_model=StateDiff)
def diff_states(
    investigation_id: UUID,
    before_state_id: UUID,
    after_state_id: UUID,
) -> StateDiff:
    _get_investigation(investigation_id)
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


@router.post("/{investigation_id}/rules/{rule_id}/verify", response_model=BusinessRule)
def verify_rule(
    investigation_id: UUID,
    rule_id: UUID,
    verification_run: VerificationRun,
) -> BusinessRule:
    _get_investigation(investigation_id)
    rule = _get_rule(rule_id)
    if rule.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Rule not found for investigation")

    store.verification_runs[verification_run.id] = verification_run
    rule.status = verification_run.status
    rule.confidence = verification_run.confidence
    rule.verification_run_ids.append(verification_run.id)
    store.rules[rule.id] = rule
    return rule


@router.get("/{investigation_id}/timeline", response_model=list[TimelineEvent])
def get_timeline(investigation_id: UUID) -> list[TimelineEvent]:
    _get_investigation(investigation_id)
    return [
        event
        for event in store.events.values()
        if event.investigation_id == investigation_id
    ]


@router.get("/{investigation_id}/rules", response_model=list[BusinessRule])
def get_rules(investigation_id: UUID) -> list[BusinessRule]:
    _get_investigation(investigation_id)
    return [
        rule for rule in store.rules.values() if rule.investigation_id == investigation_id
    ]
