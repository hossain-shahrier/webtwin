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
    AuthFormSchema,
    AuthFormSubmission,
    AuthPauseMetadata,
    AuthPauseReason,
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
from webtwin_core.reference_system import (
    build_reference_system_context,
    format_reference_system_markdown,
)
from webtwin_core.reference_system.catalog import ApplicationCatalog, upsert_catalog_from_run
from webtwin_core.reference_system.site_graph import (
    DiscoveredLink,
    SiteGraph,
    extract_discovered_links,
    mark_links_visited,
    merge_discovered_links,
)
from webtwin_core.reference_system.identity import (
    application_key_for,
    normalize_host,
    normalize_role_scope,
)
from webtwin_core.verification.engine import VerificationRun

from api.store import store


class TransitionRequest(BaseModel):
    event: TransitionEvent
    reason: str | None = None
    auth_pause: AuthPauseMetadata | None = None


class AuthFormSubmitRequest(BaseModel):
    values: dict[str, str] = {}
    use_dummy: bool = False


class AuthFillAppliedRequest(BaseModel):
    status: str = "applied"
    error: str | None = None


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
    if not investigation.application_key:
        investigation.application_key = application_key_for(
            investigation.target_url,
            application_name=investigation.application_name,
            application_key=investigation.application_key,
        )
    if investigation.role_scope:
        investigation.role_scope = normalize_role_scope(investigation.role_scope)
    store.investigations[investigation.id] = investigation
    session = get_or_create_session(investigation)
    session.session_status = SessionStatus.NOT_STARTED
    save_session(session)
    return investigation


def get_application_catalog(application_key: str):
    catalog_store = getattr(store, "catalog_store", None)
    if catalog_store is not None:
        catalog = catalog_store.get(application_key)
        if catalog is not None:
            return catalog
    catalogs = getattr(store, "application_catalogs", {})
    catalog = catalogs.get(application_key)
    if catalog is None:
        raise HTTPException(status_code=404, detail="Application catalog not found")
    return catalog


def list_application_catalogs():
    catalog_store = getattr(store, "catalog_store", None)
    if catalog_store is not None:
        return catalog_store.list_all()
    return list(getattr(store, "application_catalogs", {}).values())


def pin_golden_catalog(application_key: str, version: str) -> dict:
    catalog = get_application_catalog(application_key)
    catalog_store = getattr(store, "catalog_store", None)
    if catalog_store is None:
        raise HTTPException(status_code=501, detail="Catalog store unavailable")
    return catalog_store.pin_golden(application_key, version, catalog)


def get_golden_catalog(application_key: str, version: str | None = None) -> dict:
    catalog_store = getattr(store, "catalog_store", None)
    if catalog_store is None:
        raise HTTPException(status_code=501, detail="Catalog store unavailable")
    golden = catalog_store.get_golden(application_key, version)
    if golden is None:
        raise HTTPException(status_code=404, detail="Golden catalog not found")
    return golden


def list_investigations_for_application(application_key: str) -> list[Investigation]:
    return [
        item
        for item in store.investigations.values()
        if (item.application_key or application_key_for(item.target_url, application_name=item.application_name))
        == application_key
    ]


def merge_reference_into_catalog(investigation_id: UUID):
    """Upsert this investigation's role map + entities into the shared application catalog."""
    reference = get_reference_system_context(investigation_id, include_catalog=False)
    investigation = get_investigation(investigation_id)
    key = reference.application_key or investigation.application_key
    if not key:
        return None
    catalog_store = getattr(store, "catalog_store", None)
    existing = None
    if catalog_store is not None:
        existing = catalog_store.get(key)
    elif hasattr(store, "application_catalogs"):
        existing = store.application_catalogs.get(key)
    if reference.role_map is None:
        return existing
    catalog = upsert_catalog_from_run(
        existing,
        application_key=key,
        application_name=investigation.application_name,
        host=normalize_host(investigation.target_url),
        investigation_id=investigation.id,
        entities=reference.entities,
        role_map=reference.role_map,
        discovered_links=reference.discovered_links,
    )
    if catalog_store is not None:
        catalog_store.save(catalog)
    elif hasattr(store, "application_catalogs"):
        store.application_catalogs[key] = catalog
    return catalog


def _compute_unexplored_fields(screens, rules) -> list[str]:
    referenced = set()
    for rule in rules:
        referenced.add(rule.condition.field.lower())
        referenced.add(rule.effect.field.lower())
    unknown: list[str] = []
    for screen in screens:
        for field in screen.fields:
            if field.name.lower() not in referenced:
                unknown.append(f"{screen.id}:{field.name}")
    return unknown[:40]


def get_reference_system_context(investigation_id: UUID, *, include_catalog: bool = True):
    investigation = get_investigation(investigation_id)
    if not investigation.application_key:
        investigation.application_key = application_key_for(
            investigation.target_url,
            application_name=investigation.application_name,
        )
        store.investigations[investigation.id] = investigation
    catalog = None
    if include_catalog:
        catalog_store = getattr(store, "catalog_store", None)
        if catalog_store is not None and investigation.application_key:
            catalog = catalog_store.get(investigation.application_key)
        elif hasattr(store, "application_catalogs") and investigation.application_key:
            catalog = store.application_catalogs.get(investigation.application_key)
    rules = list_rules(investigation_id)
    metrics = list_metrics(investigation_id)
    latest = metrics[-1] if metrics else None
    coverage = latest.exploration_coverage if latest else 0.0
    return build_reference_system_context(
        investigation,
        observations=list_observations(investigation_id),
        events=list_timeline(investigation_id),
        rules=rules,
        workflows=list_workflows(investigation_id),
        states=list_states(investigation_id),
        catalog=catalog,
        exploration_coverage=coverage,
        discovered_links=list_discovered_links(investigation_id),
    )


def list_discovered_links(investigation_id: UUID) -> list[DiscoveredLink]:
    get_investigation(investigation_id)
    return sorted(
        [
            link
            for link in store.discovered_links.values()
            if getattr(link, "investigation_id", None) == investigation_id
        ],
        key=lambda item: (item.from_screen_id, item.href),
    )


def upsert_discovered_links_from_observation(observation: Observation) -> list[DiscoveredLink]:
    incoming = extract_discovered_links(observation, origin_url=observation.url)
    merged = merge_discovered_links(list_discovered_links(observation.investigation_id), incoming)
    for link in merged:
        store.discovered_links[link.id] = link
    return merged


def mark_discovered_links_visited_for_screen(
    investigation_id: UUID,
    *,
    to_screen_id: str,
    href: str | None = None,
) -> None:
    links = list_discovered_links(investigation_id)
    mark_links_visited(links, to_screen_id=to_screen_id, href=href)
    for link in links:
        store.discovered_links[link.id] = link


def get_site_graph(investigation_id: UUID) -> SiteGraph:
    reference = get_reference_system_context(investigation_id)
    from webtwin_core.reference_system.site_graph import build_site_graph

    investigation = get_investigation(investigation_id)
    return build_site_graph(
        reference.screens,
        reference.discovered_links,
        reference.navigation,
        origin_url=investigation.target_url,
    )


def get_application_site_graph(application_key: str) -> dict:
    catalog = None
    try:
        catalog = get_application_catalog(application_key)
    except HTTPException:
        pass
    investigations = list_investigations_for_application(application_key)
    all_links: list[DiscoveredLink] = []
    screens_by_id = {}
    navigation = []
    target_url = ""
    for investigation in investigations:
        reference = get_reference_system_context(investigation.id, include_catalog=False)
        all_links = merge_discovered_links(all_links, reference.discovered_links)
        for screen in reference.screens:
            existing = screens_by_id.get(screen.id)
            if existing is None or screen.visit_count > existing.visit_count:
                screens_by_id[screen.id] = screen
        navigation.extend(reference.navigation)
        if not target_url:
            target_url = investigation.target_url
    from webtwin_core.reference_system.site_graph import build_site_graph

    screens = list(screens_by_id.values())
    graph = build_site_graph(screens, all_links, navigation, origin_url=target_url or application_key)
    return {
        "application_key": application_key,
        "nodes": [screen.model_dump(mode="json") for screen in graph.nodes],
        "edges": [
            {
                "from": link.from_screen_id,
                "to": link.to_screen_id,
                "href": link.href,
                "visited": link.visited,
                "link_type": link.link_type.value,
            }
            for link in graph.discovered_links
        ],
        "visited_edges": [edge.model_dump(mode="json") for edge in graph.visited_edges],
        "stats": graph.stats.model_dump(mode="json"),
        "investigation_ids": [str(item.id) for item in investigations],
        "catalog": catalog.model_dump(mode="json") if catalog else None,
    }


def list_investigations() -> list[Investigation]:
    return list(store.investigations.values())


_RECLAIMABLE_STATUSES = {
    InvestigationStatus.INITIALIZING,
    InvestigationStatus.AUTH_CHECK,
    InvestigationStatus.AUTH_REQUIRED,
    InvestigationStatus.EXPLORING,
    InvestigationStatus.OBSERVING,
    InvestigationStatus.AUTHENTICATED,
    InvestigationStatus.GENERATING_RULE,
    InvestigationStatus.VERIFYING,
}


def _claim_ttl_seconds() -> int:
    import os

    try:
        return max(60, int(os.environ.get("WEBTWIN_CLAIM_TTL_SECONDS", "1800")))
    except ValueError:
        return 1800


def _release_claim(investigation_id: UUID) -> None:
    claims = getattr(store, "investigation_claims", None)
    if claims is not None:
        claims.pop(investigation_id, None)
    claim_times = getattr(store, "investigation_claim_at", None)
    if claim_times is not None:
        claim_times.pop(investigation_id, None)


def _set_claim(investigation_id: UUID, worker_id: str) -> None:
    claims = getattr(store, "investigation_claims", None)
    if claims is not None:
        claims[investigation_id] = worker_id
    claim_times = getattr(store, "investigation_claim_at", None)
    if claim_times is not None:
        claim_times[investigation_id] = datetime.now(UTC)


def _claim_is_stale(investigation_id: UUID) -> bool:
    claim_times = getattr(store, "investigation_claim_at", None) or {}
    stamped = claim_times.get(investigation_id)
    if stamped is None:
        # Legacy claim without timestamp — treat as reclaimable
        return True
    age = (datetime.now(UTC) - stamped).total_seconds()
    return age >= _claim_ttl_seconds()


def _record_audit(action: str, investigation_id: UUID, **detail) -> None:
    from webtwin_core.audit import make_audit_event

    events = getattr(store, "audit_events", None)
    if events is None:
        return
    event = make_audit_event(action, investigation_id=investigation_id, **detail)
    events[event.id] = event


def list_pending_investigations() -> list[Investigation]:
    """Investigations waiting for a browser worker (created, orphaned auth, or resumed mid-run)."""
    claims = getattr(store, "investigation_claims", {}) or {}
    pending: list[Investigation] = []
    for item in store.investigations.values():
        if item.status == InvestigationStatus.CREATED:
            pending.append(item)
            continue
        if item.status not in _RECLAIMABLE_STATUSES:
            continue
        holder = claims.get(item.id)
        if holder is None or _claim_is_stale(item.id):
            pending.append(item)
    return pending


def claim_investigation(investigation_id: UUID) -> Investigation:
    """Atomically claim a created (or orphaned / stale) investigation for the worker."""
    import os

    investigation = get_investigation(investigation_id)
    worker_id = os.environ.get("WEBTWIN_WORKER_ID") or "local-worker"
    claims = getattr(store, "investigation_claims", None)
    if claims is not None:
        holder = claims.get(investigation_id)
        if (
            holder
            and holder != worker_id
            and not _claim_is_stale(investigation_id)
            and investigation.status
            not in {
                InvestigationStatus.CREATED,
                InvestigationStatus.AUTH_REQUIRED,
            }
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Investigation already claimed by worker {holder}",
            )
    if investigation.status in _RECLAIMABLE_STATUSES:
        if claims is not None:
            _set_claim(investigation_id, worker_id)
        _record_audit(
            "investigation.claimed",
            investigation_id,
            status=investigation.status.value,
            worker_id=worker_id,
        )
        return investigation
    if investigation.status != InvestigationStatus.CREATED:
        raise HTTPException(status_code=409, detail="Investigation is not claimable")
    claimed = transition_investigation(
        investigation_id,
        TransitionRequest(event=TransitionEvent.START, reason="claimed_by_worker"),
    )
    if claims is not None:
        _set_claim(investigation_id, worker_id)
    _record_audit(
        "investigation.claimed",
        investigation_id,
        status=claimed.status.value,
        worker_id=worker_id,
    )
    return claimed


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
        # Release claim so another worker (or the same after human login) can resume
        _release_claim(investigation_id)
    save_session(session)

    _record_audit(
        "investigation.transition",
        investigation_id,
        event=request.event.value,
        from_status=previous.value,
        to_status=new_status.value,
        reason=request.reason,
    )

    if new_status in {InvestigationStatus.COMPLETED, InvestigationStatus.FAILED}:
        _release_claim(investigation_id)

    if new_status == InvestigationStatus.COMPLETED:
        import logging

        logger = logging.getLogger(__name__)
        try:
            discover_workflows_from_diffs(investigation_id)
        except Exception as error:
            logger.warning("Workflow discovery failed for %s: %s", investigation_id, error)
        try:
            merge_reference_into_catalog(investigation_id)
        except Exception as error:
            logger.warning("Catalog merge failed for %s: %s", investigation_id, error)
        try:
            sync_knowledge_graph(investigation_id)
        except Exception as error:
            logger.warning("KG sync failed for %s: %s", investigation_id, error)

    return investigation


def resume_failed(investigation_id: UUID) -> Investigation:
    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed investigations can use /resume")
    if investigation.checkpoint is None:
        raise HTTPException(status_code=409, detail="No checkpoint available to resume")
    _release_claim(investigation_id)
    return transition_investigation(investigation_id, TransitionRequest(event=TransitionEvent.RESUME))


def _clear_investigation_capture(investigation_id: UUID) -> None:
    """Remove observations, graph, rules, and timeline for a fresh re-run."""

    def _drop_entity_map(mapping: dict) -> None:
        for key in [
            item_id
            for item_id, value in list(mapping.items())
            if getattr(value, "investigation_id", None) == investigation_id
        ]:
            mapping.pop(key, None)

    _drop_entity_map(store.observations)
    _drop_entity_map(store.states)
    _drop_entity_map(store.events)
    _drop_entity_map(store.evidence)
    _drop_entity_map(store.diffs)
    _drop_entity_map(store.rules)
    _drop_entity_map(store.verification_runs)
    _drop_entity_map(getattr(store, "workflows", {}))
    _drop_entity_map(store.discovered_links)
    if hasattr(store, "network_events"):
        for key in [
            item_id
            for item_id, value in list(store.network_events.items())
            if str(value.get("investigation_id")) == str(investigation_id)
        ]:
            store.network_events.pop(key, None)
    for key in [
        item_id
        for item_id, value in list(store.transitions.items())
        if value.investigation_id == investigation_id
    ]:
        store.transitions.pop(key, None)
    if hasattr(store, "investigation_claims"):
        store.investigation_claims.pop(investigation_id, None)
    if hasattr(store, "investigation_claim_at"):
        store.investigation_claim_at.pop(investigation_id, None)


def restart_failed(investigation_id: UUID) -> Investigation:
    """Re-queue a failed investigation with no usable checkpoint (worker can claim again)."""
    from pathlib import Path

    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed investigations can use /restart")
    _clear_investigation_capture(investigation_id)
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
    session.auth_verified_at = None
    session.storage_state_ref = None
    session.checkpoint = None
    session_path = Path.home() / ".webtwin" / "sessions" / f"{investigation_id}.json"
    if session_path.exists():
        session_path.unlink()
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


def get_auth_form(investigation_id: UUID) -> AuthFormSchema | None:
    investigation = get_investigation(investigation_id)
    if investigation.auth_pause and investigation.auth_pause.form:
        return investigation.auth_pause.form
    return None


def upsert_auth_form_schema(investigation_id: UUID, schema: AuthFormSchema) -> AuthFormSchema:
    investigation = get_investigation(investigation_id)
    if investigation.status not in {
        InvestigationStatus.AUTH_REQUIRED,
        InvestigationStatus.AUTH_CHECK,
        InvestigationStatus.AUTHENTICATED,
    }:
        raise HTTPException(status_code=409, detail="Investigation is not in an auth phase")
    pause = investigation.auth_pause or AuthPauseMetadata(
        reason=AuthPauseReason.LOGIN_REQUIRED,
        resume_allowed=True,
        url=schema.url or investigation.target_url,
    )
    pause.form = schema
    investigation.auth_pause = pause
    investigation.updated_at = datetime.now(UTC)
    store.investigations[investigation.id] = investigation
    return schema


def submit_auth_form(investigation_id: UUID, request: AuthFormSubmitRequest) -> AuthFormSubmission:
    from webtwin_core.auth.form_schema import build_dummy_values

    investigation = get_investigation(investigation_id)
    if investigation.status != InvestigationStatus.AUTH_REQUIRED:
        raise HTTPException(status_code=409, detail="Investigation is not waiting for authentication")

    schema = get_auth_form(investigation_id)
    if schema is None or not schema.fields:
        raise HTTPException(
            status_code=409,
            detail="No auth form schema available yet — wait for the worker to detect the login/register page",
        )

    values = dict(request.values or {})
    if request.use_dummy:
        values = {**build_dummy_values(schema), **values}

    missing = [
        field.label
        for field in schema.fields
        if field.required and not str(values.get(field.key, "")).strip()
    ]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")

    # Never persist secrets into investigation.auth_pause — only ephemeral submission map.
    submission = AuthFormSubmission(
        investigation_id=investigation_id,
        values=values,
        use_dummy=request.use_dummy,
        status="pending",
    )
    if not hasattr(store, "auth_form_submissions"):
        store.auth_form_submissions = {}
    store.auth_form_submissions[investigation_id] = submission

    session = get_or_create_session(investigation)
    if session.session_status == SessionStatus.AUTH_REQUIRED:
        session.session_status = SessionStatus.AUTHENTICATING
    # Mark human-ready so worker can continue after fill + wall clear.
    session.human_ready_at = datetime.now(UTC)
    save_session(session)

    if investigation.auth_pause is None:
        investigation.auth_pause = AuthPauseMetadata(
            reason=AuthPauseReason.LOGIN_REQUIRED,
            resume_allowed=True,
            url=schema.url,
            form=schema,
            message="form_submitted",
        )
    else:
        investigation.auth_pause.message = "form_submitted"
    store.investigations[investigation.id] = investigation
    return submission


def get_pending_auth_fill(investigation_id: UUID) -> AuthFormSubmission | None:
    get_investigation(investigation_id)
    submissions = getattr(store, "auth_form_submissions", {}) or {}
    submission = submissions.get(investigation_id)
    if submission is None:
        return None
    if getattr(submission, "status", None) != "pending":
        return None
    return submission  # type: ignore[return-value]


def mark_auth_fill_applied(
    investigation_id: UUID,
    request: AuthFillAppliedRequest,
) -> AuthFormSubmission:
    get_investigation(investigation_id)
    submissions = getattr(store, "auth_form_submissions", {}) or {}
    submission = submissions.get(investigation_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="No auth form submission found")
    submission.status = request.status if request.status in {"applied", "failed", "cancelled"} else "applied"
    submission.error = request.error
    submission.applied_at = datetime.now(UTC)
    store.auth_form_submissions[investigation_id] = submission
    return submission  # type: ignore[return-value]


class ExplorationProgressRequest(BaseModel):
    """Lean crawl cursor upsert — merges into investigation.checkpoint.exploration."""

    last_url: str | None = None
    frontier: list[str] = []
    pages_seen: list[str] = []
    routes_seen: list[str] = []
    tested_action_keys: list[str] = []
    explored_field_targets: list[str] = []
    actions_taken: int = 0
    scrolls_used: int = 0
    budget_actions_used: int = 0
    budget_pages_seen: int = 0
    budget_experiments_used: int = 0
    policy: str | None = None
    url_prefix: str | None = None


def save_exploration_progress(
    investigation_id: UUID,
    request: ExplorationProgressRequest,
) -> dict:
    from webtwin_core.exploration.progress import ExplorationProgress
    from webtwin_core.models.investigation import InvestigationCheckpoint

    investigation = get_investigation(investigation_id)
    progress = ExplorationProgress(
        last_url=request.last_url,
        frontier=request.frontier,
        pages_seen=request.pages_seen,
        routes_seen=request.routes_seen,
        tested_action_keys=request.tested_action_keys,
        explored_field_targets=request.explored_field_targets,
        actions_taken=request.actions_taken,
        scrolls_used=request.scrolls_used,
        budget_actions_used=request.budget_actions_used,
        budget_pages_seen=request.budget_pages_seen,
        budget_experiments_used=request.budget_experiments_used,
        policy=request.policy,
        url_prefix=request.url_prefix,
    ).capped()

    if investigation.checkpoint is None:
        investigation.checkpoint = InvestigationCheckpoint(
            status=investigation.status,
            target_url=investigation.target_url,
            observation_count=observation_count(investigation_id),
            exploration=progress.model_dump(mode="json"),
        )
    else:
        investigation.checkpoint.exploration = progress.model_dump(mode="json")
        investigation.checkpoint.saved_at = datetime.now(UTC)
        # Keep status in sync with live investigation when still mid-crawl.
        if investigation.status in {
            InvestigationStatus.EXPLORING,
            InvestigationStatus.OBSERVING,
            InvestigationStatus.AUTHENTICATED,
            InvestigationStatus.GENERATING_RULE,
            InvestigationStatus.VERIFYING,
        }:
            investigation.checkpoint.status = investigation.status

    investigation.updated_at = datetime.now(UTC)
    store.investigations[investigation.id] = investigation

    session = get_or_create_session(investigation)
    session.checkpoint = investigation.checkpoint
    save_session(session)
    return {"ok": True, "exploration": progress.model_dump(mode="json")}


def get_exploration_progress(investigation_id: UUID) -> dict | None:
    investigation = get_investigation(investigation_id)
    if investigation.checkpoint is None:
        return None
    return investigation.checkpoint.exploration


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
    upsert_discovered_links_from_observation(observation)
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
    from webtwin_core.models.events import TimelineEventType
    from webtwin_core.reference_system.site_graph import screen_id_from_url

    get_investigation(investigation_id)
    store.events[event.id] = event
    if event.type in {TimelineEventType.NAVIGATE, TimelineEventType.ROUTE}:
        href: str | None = None
        description = event.description or ""
        if " href=" in description:
            href = description.split(" href=", 1)[1].split(" ", 1)[0]
        to_screen_id = "/"
        if event.state_after_id and event.state_after_id in store.states:
            after = store.states[event.state_after_id]
            if after.url:
                to_screen_id = screen_id_from_url(after.url)
        if href or event.state_after_id:
            mark_discovered_links_visited_for_screen(
                investigation_id,
                to_screen_id=to_screen_id,
                href=href,
            )
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
        attached_rule_ids = (evidence.payload or {}).get("rule_ids") or []
        if not attached_rule_ids:
            single = (evidence.payload or {}).get("rule_id")
            if single:
                attached_rule_ids = [single]
        for raw_rule_id in attached_rule_ids:
            try:
                rule_id = UUID(str(raw_rule_id))
            except (TypeError, ValueError):
                continue
            rule = store.rules.get(rule_id)
            if rule is None or rule.investigation_id != investigation_id:
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

    def _rule_signature(rule: BusinessRule) -> tuple:
        return (
            rule.condition.field,
            rule.condition.operator,
            str(rule.condition.value),
            rule.effect.field,
            rule.effect.visible,
            rule.effect.required,
            getattr(rule.effect, "enabled", None),
        )

    existing_signatures = {
        _rule_signature(rule)
        for rule in store.rules.values()
        if rule.investigation_id == investigation_id
    }

    for rule in infer_candidate_rules(diff, before, after):
        signature = _rule_signature(rule)
        if signature in existing_signatures:
            continue
        existing_signatures.add(signature)
        evidence = Evidence(
            investigation_id=investigation_id,
            type=EvidenceType.DOM,
            payload={
                "state_transition_id": str(diff.id),
                "before_state_id": str(before.id),
                "after_state_id": str(after.id),
                "summary": diff.summary,
                "rule_id": str(rule.id),
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
    if verification_run.status.value == "verified":
        try:
            sync_knowledge_graph(investigation_id)
        except Exception:
            pass
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
    from api.kg.sync import local_related_rule_ids, query_related_rule_ids
    from webtwin_core.qa import answer_from_evidence
    from webtwin_core.qa.models import QuestionAnswer
    from webtwin_core.reference_system.entities import match_entity_name

    get_investigation(investigation_id)
    investigation = store.investigations[investigation_id]
    rules = list_rules(investigation_id)
    evidence = list_evidence(investigation_id)
    app_key = (
        investigation.application_key
        or application_key_for(
            investigation.target_url,
            application_name=investigation.application_name,
            application_key=investigation.application_key,
        )
    )
    preferred = query_related_rule_ids(investigation_id, question, application_key=app_key)
    if not preferred:
        preferred = local_related_rule_ids(rules, question)

    # Prefer rules belonging to entities mentioned in the question
    matched_entity = match_entity_name(question)
    if matched_entity:
        reference = get_reference_system_context(investigation_id)
        entity = next((item for item in reference.entities if item.name == matched_entity), None)
        if entity and entity.rule_names:
            rule_by_name = {rule.name: str(rule.id) for rule in rules}
            for name in entity.rule_names:
                rule_id = rule_by_name.get(name)
                if rule_id and rule_id not in preferred:
                    preferred.insert(0, rule_id)

    preferred_uuids = []
    for item in preferred:
        try:
            preferred_uuids.append(UUID(str(item)))
        except ValueError:
            continue
    answer: QuestionAnswer = answer_from_evidence(
        question,
        rules,
        evidence,
        preferred_rule_ids=preferred_uuids,
    )
    return answer


def export_cursor_context(investigation_id: UUID) -> dict:
    """Markdown + structured context for AI coding assistants (Cursor, etc.)."""
    from webtwin_core.reference_system.ai_spec import build_ai_spec

    investigation = get_investigation(investigation_id)
    rules = list_rules(investigation_id)
    evidence = list_evidence(investigation_id)
    workflows = list_workflows(investigation_id)
    metrics = list_metrics(investigation_id)
    reference = get_reference_system_context(investigation_id)
    latest = metrics[-1] if metrics else None
    network_events = [
        event
        for event in getattr(store, "network_events", {}).values()
        if str(event.get("investigation_id")) == str(investigation_id)
    ]
    unknown_fields = [
        (item.split(":", 1)[0], item.split(":", 1)[1])
        if ":" in item
        else (None, item)
        for item in reference.unexplored_fields
    ]

    verified = [rule for rule in rules if rule.status.value == "verified"]
    candidates = [rule for rule in rules if rule.status.value == "candidate"]
    under_verification = [rule for rule in rules if rule.status.value == "under_verification"]
    contradicted = [rule for rule in rules if rule.status.value == "contradicted"]

    ai_spec = build_ai_spec(
        investigation,
        reference,
        rules,
        network_events=network_events,
        unknown_fields=unknown_fields,
    )
    lines = [ai_spec.markdown]
    if latest:
        lines.extend(
            [
                "",
                "## Exploration metrics",
                f"- Actions taken: {latest.actions_taken}",
                f"- Pages seen: {latest.pages_seen}",
                f"- Evidence items: {len(evidence)}",
            ]
        )
    if contradicted:
        lines.extend(
            [
                "",
                "## Contradicted rules (do not implement)",
                f"_{len(contradicted)} rule(s) failed verification._",
            ]
        )
        for rule in contradicted[:10]:
            lines.append(f"- {rule.name}")
    if under_verification:
        lines.extend(["", "## Rules under verification"])
        for rule in under_verification[:10]:
            lines.append(f"- {rule.name} (confidence={rule.confidence})")
    lines.extend(
        [
            "",
            "## Full exports",
            f"- AI spec JSON: `GET /investigations/{investigation.id}/export/ai-spec`",
            f"- Clone spec JSON: `GET /investigations/{investigation.id}/export/clone-spec`",
            f"- Prompt capsules: `GET /investigations/{investigation.id}/export/prompt-capsules`",
            f"- Site graph: `GET /investigations/{investigation.id}/site-graph`",
        ]
    )
    markdown = "\n".join(lines)
    return {
        "investigation_id": str(investigation.id),
        "target_url": investigation.target_url,
        "markdown": markdown,
        "summary": ai_spec.summary.model_dump(mode="json"),
        "verified_rules": [rule.model_dump(mode="json") for rule in verified],
        "candidate_rules": [rule.model_dump(mode="json") for rule in candidates],
        "under_verification_rules": [rule.model_dump(mode="json") for rule in under_verification],
        "contradicted_rules": [rule.model_dump(mode="json") for rule in contradicted],
        "workflow_count": len(workflows),
        "reference_system": reference.model_dump(mode="json"),
        "clone_spec_url": f"/investigations/{investigation.id}/export/clone-spec",
        "ai_spec_url": f"/investigations/{investigation.id}/export/ai-spec",
        "prompt_capsules_url": f"/investigations/{investigation.id}/export/prompt-capsules",
        "site_graph_url": f"/investigations/{investigation.id}/site-graph",
    }


def export_ai_spec(investigation_id: UUID) -> dict:
    from webtwin_core.reference_system.ai_spec import build_ai_spec

    investigation = get_investigation(investigation_id)
    reference = get_reference_system_context(investigation_id)
    rules = list_rules(investigation_id)
    network_events = [
        event
        for event in getattr(store, "network_events", {}).values()
        if str(event.get("investigation_id")) == str(investigation_id)
    ]
    unknown_fields = [
        (item.split(":", 1)[0], item.split(":", 1)[1])
        if ":" in item
        else (None, item)
        for item in reference.unexplored_fields
    ]
    spec = build_ai_spec(
        investigation,
        reference,
        rules,
        network_events=network_events,
        unknown_fields=unknown_fields,
    )
    payload = spec.model_dump(mode="json")
    payload["full_clone_spec_url"] = f"/investigations/{investigation_id}/export/clone-spec"
    return payload


def get_clone_scorecard(investigation_id: UUID) -> dict:
    from webtwin_core.reference_system.clone_scorecard import compute_clone_scorecard

    reference = get_reference_system_context(investigation_id)
    rules = list_rules(investigation_id)
    scorecard = compute_clone_scorecard(rules, reference)
    return scorecard.model_dump(mode="json")


def export_clone_spec(investigation_id: UUID) -> dict:
    from webtwin_core.reference_system.clone_spec import build_clone_spec

    investigation = get_investigation(investigation_id)
    reference = get_reference_system_context(investigation_id)
    rules = list_rules(investigation_id)
    metrics = list_metrics(investigation_id)
    latest = metrics[-1] if metrics else None
    network_events = [
        event
        for event in getattr(store, "network_events", {}).values()
        if str(event.get("investigation_id")) == str(investigation_id)
    ]
    unknown_fields = [
        (item.split(":", 1)[0], item.split(":", 1)[1])
        if ":" in item
        else (None, item)
        for item in reference.unexplored_fields
    ]
    spec = build_clone_spec(
        investigation,
        reference,
        rules,
        network_events=network_events,
        exploration_coverage=reference.exploration_coverage,
        unknown_fields=unknown_fields,
    )
    return spec.model_dump(mode="json")


def export_prompt_capsules(investigation_id: UUID) -> dict:
    from webtwin_core.capsules import build_prompt_capsules, format_capsules_bundle_markdown

    get_investigation(investigation_id)
    rules = list_rules(investigation_id)
    evidence = list_evidence(investigation_id)
    export = build_prompt_capsules(investigation_id, rules, evidence)
    payload = export.model_dump(mode="json")
    payload["markdown"] = format_capsules_bundle_markdown(export)
    return payload


def plan_counterfactual_experiment(investigation_id: UUID, body: dict) -> dict:
    from webtwin_core.counterfactual import CounterfactualRequest, plan_counterfactual
    from webtwin_core.audit import make_audit_event

    get_investigation(investigation_id)
    request = CounterfactualRequest.model_validate(body)
    plan = plan_counterfactual(request, investigation_id=investigation_id)
    events = getattr(store, "audit_events", None)
    if events is not None:
        event = make_audit_event(
            "counterfactual.planned",
            investigation_id=investigation_id,
            condition_field=request.condition_field,
            condition_value=request.condition_value,
            effect_field=request.effect_field,
            plan_id=str(plan.id),
        )
        events[event.id] = event
    pending = getattr(store, "counterfactual_plans", None)
    if pending is None:
        store.counterfactual_plans = {}
        pending = store.counterfactual_plans
    pending[plan.id] = plan
    return plan.model_dump(mode="json")


def list_absences(investigation_id: UUID) -> dict:
    from webtwin_core.negative_space import derive_absences_from_rules

    get_investigation(investigation_id)
    rules = list_rules(investigation_id)
    absences = derive_absences_from_rules(rules)
    return {
        "investigation_id": str(investigation_id),
        "absences": [item.model_dump(mode="json") for item in absences],
        "count": len(absences),
    }


def export_application_clone_spec(application_key: str) -> dict:
    catalog = get_application_catalog(application_key)
    golden = get_golden_catalog(application_key)
    site_graph = get_application_site_graph(application_key)
    return {
        "application_key": application_key,
        "catalog": catalog.model_dump(mode="json"),
        "golden": golden,
        "site_graph": {
            "nodes": site_graph.get("nodes", []),
            "edges": site_graph.get("edges", []),
            "stats": site_graph.get("stats", {}),
        },
    }


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
    """Build workflow summaries from timeline actions and state diffs."""
    from webtwin_core.models.events import TimelineEventType
    from webtwin_core.models.workflow import Workflow, WorkflowStep

    investigation = get_investigation(investigation_id)
    saved: list = []

    action_types = {
        TimelineEventType.NAVIGATE,
        TimelineEventType.CLICK,
        TimelineEventType.INPUT,
        TimelineEventType.SELECT,
        TimelineEventType.SUBMIT,
        TimelineEventType.ROUTE,
    }
    timeline_steps = [
        WorkflowStep(
            order=index,
            description=event.description,
            action_id=str(event.id),
            from_state_id=event.state_before_id,
            to_state_id=event.state_after_id,
        )
        for index, event in enumerate(
            sorted(
                [
                    event
                    for event in list_timeline(investigation_id)
                    if event.type in action_types
                ],
                key=lambda item: item.occurred_at,
            )[:24]
        )
    ]
    if len(timeline_steps) >= 2:
        saved.append(
            save_workflow(
                investigation_id,
                Workflow(
                    investigation_id=investigation_id,
                    name=f"Exploration path ({len(timeline_steps)} actions)",
                    steps=timeline_steps,
                    trigger_action_ids=[step.action_id for step in timeline_steps if step.action_id],
                    confidence=0.65 if len(timeline_steps) >= 4 else 0.45,
                    role_scope=investigation.role_scope,
                ),
            )
        )

    diffs = sorted(list_diffs(investigation_id), key=lambda item: str(item.id))
    if diffs:
        diff_steps = [
            WorkflowStep(
                order=index,
                description=diff.summary or "state transition",
                from_state_id=diff.before_state_id,
                to_state_id=diff.after_state_id,
            )
            for index, diff in enumerate(diffs[:12])
        ]
        saved.append(
            save_workflow(
                investigation_id,
                Workflow(
                    investigation_id=investigation_id,
                    name=f"State transitions ({len(diff_steps)} diffs)",
                    steps=diff_steps,
                    confidence=0.5 if len(diff_steps) >= 2 else 0.3,
                    role_scope=investigation.role_scope,
                ),
            )
        )

    return saved


def sync_knowledge_graph(investigation_id: UUID) -> dict:
    import logging

    from api.kg.sync import sync_investigation_to_kg

    logger = logging.getLogger(__name__)
    investigation = get_investigation(investigation_id)
    reference = get_reference_system_context(investigation_id)
    try:
        return sync_investigation_to_kg(
            investigation_id=investigation.id,
            application_name=investigation.application_name,
            application_key=reference.application_key,
            target_url=investigation.target_url,
            rules=list_rules(investigation_id),
            evidence=list_evidence(investigation_id),
            role_scope=investigation.role_scope,
            application_version=investigation.application_version,
            environment=investigation.environment,
            screens=reference.screens,
            entities=reference.entities,
            flows=reference.flows,
            discovered_links=reference.discovered_links,
            navigation=reference.navigation,
            rules_by_screen=reference.rules_by_screen,
        )
    except Exception as error:
        logger.warning("Knowledge graph sync failed for %s: %s", investigation_id, error)
        return {"nodes": 0, "edges": 0, "skipped": 1, "reason": str(error)}
