from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from webtwin_core.evaluation.runs import EvaluationRun
from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    ElementSnapshot,
    Evidence,
    FieldChange,
    FieldState,
    FormSnapshot,
    Investigation,
    InvestigationSession,
    Observation,
    RuleCondition,
    RuleEffect,
    StateDiff,
    TimelineEvent,
)
from webtwin_core.models.investigation import InvestigationTransition
from webtwin_core.verification.engine import (
    VerificationExperimentResult,
    VerificationRun,
)

from api.db.schema import (
    ApplicationStateRow,
    EvaluationRunRow,
    EvidenceRow,
    ExperimentResultRow,
    ExperimentRow,
    FieldChangeRow,
    InvestigationRow,
    InvestigationTransitionRow,
    ObservationElementRow,
    ObservationFormRow,
    ObservationRow,
    RuleEvidenceRow,
    RuleExperimentRow,
    RuleRow,
    SessionRow,
    StateFieldRow,
    StateTransitionRow,
    TimelineEventRow,
)


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def investigation_to_row(model: Investigation) -> InvestigationRow:
    return InvestigationRow(
        id=model.id,
        goal=model.goal,
        target_url=model.target_url,
        status=model.status.value,
        application_name=model.application_name,
        application_key=model.application_key,
        feature_scope=model.feature_scope,
        session_id=model.session_id,
        goal_spec=_jsonable(model.goal_spec.model_dump(mode="json")) if model.goal_spec else None,
        auth_pause=_jsonable(model.auth_pause.model_dump(mode="json")) if model.auth_pause else None,
        checkpoint=_jsonable(model.checkpoint.model_dump(mode="json")) if model.checkpoint else None,
        failure_reason=model.failure_reason,
        blocked_reason=model.blocked_reason,
        application_version=model.application_version,
        environment=model.environment,
        role_scope=model.role_scope,
        spa_mode=model.spa_mode,
        exploration_policy=getattr(model, "exploration_policy", None),
        investigation_scope=getattr(model, "investigation_scope", None),
        url_prefix=getattr(model, "url_prefix", None),
        start_url=getattr(model, "start_url", None),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def investigation_from_row(row: InvestigationRow) -> Investigation:
    payload = {
        "id": row.id,
        "goal": row.goal,
        "target_url": row.target_url,
        "status": row.status,
        "application_name": row.application_name,
        "application_key": getattr(row, "application_key", None),
        "feature_scope": row.feature_scope,
        "session_id": row.session_id,
        "goal_spec": row.goal_spec,
        "auth_pause": row.auth_pause,
        "checkpoint": row.checkpoint,
        "failure_reason": row.failure_reason,
        "blocked_reason": row.blocked_reason,
        "application_version": row.application_version,
        "environment": row.environment,
        "role_scope": row.role_scope,
        "spa_mode": bool(getattr(row, "spa_mode", False)),
        "exploration_policy": getattr(row, "exploration_policy", None),
        "investigation_scope": getattr(row, "investigation_scope", None),
        "url_prefix": getattr(row, "url_prefix", None),
        "start_url": getattr(row, "start_url", None),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    return Investigation.model_validate(payload)


def session_to_row(model: InvestigationSession) -> SessionRow:
    return SessionRow(
        id=model.id,
        investigation_id=model.investigation_id,
        auth_state=model.auth_state.value,
        session_status=model.session_status.value,
        storage_state_ref=model.storage_state_ref,
        checkpoint=_jsonable(model.checkpoint.model_dump(mode="json")) if model.checkpoint else None,
        human_ready_at=model.human_ready_at,
        auth_verified_at=model.auth_verified_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def session_from_row(row: SessionRow) -> InvestigationSession:
    return InvestigationSession.model_validate(
        {
            "id": row.id,
            "investigation_id": row.investigation_id,
            "auth_state": row.auth_state,
            "session_status": row.session_status,
            "storage_state_ref": row.storage_state_ref,
            "checkpoint": row.checkpoint,
            "human_ready_at": row.human_ready_at,
            "auth_verified_at": row.auth_verified_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def transition_to_row(model: InvestigationTransition) -> InvestigationTransitionRow:
    return InvestigationTransitionRow(
        id=model.id,
        investigation_id=model.investigation_id,
        from_status=model.from_status.value,
        to_status=model.to_status.value,
        event=model.event.value,
        reason=model.reason,
        occurred_at=model.occurred_at,
    )


def transition_from_row(row: InvestigationTransitionRow) -> InvestigationTransition:
    return InvestigationTransition.model_validate(
        {
            "id": row.id,
            "investigation_id": row.investigation_id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "event": row.event,
            "reason": row.reason,
            "occurred_at": row.occurred_at,
        }
    )


def observation_to_row(model: Observation) -> ObservationRow:
    return ObservationRow(
        id=model.id,
        investigation_id=model.investigation_id,
        captured_at=model.captured_at,
        url=model.url,
        title=model.title,
        screenshot_path=model.screenshot_path,
        html_length=model.html_length,
        accessibility=_jsonable(model.accessibility) or {},
        visible_elements=list(model.visible_elements),
        interactive_elements=list(model.interactive_elements),
        route=_jsonable(model.route.model_dump(mode="json")) if model.route else None,
        framework_hints=_jsonable(model.framework_hints) or {},
        elements=[
            ObservationElementRow(
                selector=element.selector,
                tag=element.tag,
                role=element.role,
                name=element.name,
                label=element.label,
                value=element.value,
                visible=element.visible,
                enabled=element.enabled,
                required=element.required,
                options=list(element.options),
                text=element.text,
                input_type=element.input_type,
                testid=element.testid,
                stable_key=element.stable_key,
                selector_candidates=list(element.selector_candidates),
                in_shadow_dom=element.in_shadow_dom,
            )
            for element in model.elements
        ],
        forms=[
            ObservationFormRow(
                selector=form.selector,
                name=form.name,
                fields=_jsonable([field.model_dump(mode="json") for field in form.fields]) or [],
            )
            for form in model.forms
        ],
    )


def observation_from_row(row: ObservationRow) -> Observation:
    from webtwin_core.models.spa import RouteSnapshot

    route = None
    if getattr(row, "route", None):
        route = RouteSnapshot.model_validate(row.route)
    return Observation(
        id=row.id,
        investigation_id=row.investigation_id,
        captured_at=row.captured_at,
        url=row.url,
        title=row.title,
        screenshot_path=row.screenshot_path,
        html_length=row.html_length,
        accessibility=row.accessibility or {},
        visible_elements=list(row.visible_elements or []),
        interactive_elements=list(row.interactive_elements or []),
        route=route,
        framework_hints=getattr(row, "framework_hints", None) or {},
        elements=[
            ElementSnapshot(
                selector=element.selector,
                tag=element.tag,
                role=element.role,
                name=element.name,
                label=element.label,
                value=element.value,
                visible=element.visible,
                enabled=element.enabled,
                required=element.required,
                options=list(element.options or []),
                text=element.text,
                input_type=element.input_type,
                testid=getattr(element, "testid", None),
                stable_key=getattr(element, "stable_key", None),
                selector_candidates=list(getattr(element, "selector_candidates", None) or []),
                in_shadow_dom=bool(getattr(element, "in_shadow_dom", False)),
            )
            for element in row.elements
        ],
        forms=[
            FormSnapshot(
                selector=form.selector,
                name=form.name,
                fields=[ElementSnapshot.model_validate(field) for field in (form.fields or [])],
            )
            for form in row.forms
        ],
    )


def state_to_row(model: ApplicationState) -> ApplicationStateRow:
    return ApplicationStateRow(
        id=model.id,
        investigation_id=model.investigation_id,
        sequence=model.sequence,
        captured_at=model.captured_at,
        url=model.url,
        triggered_by_event_id=model.triggered_by_event_id,
        fields=[
            StateFieldRow(
                name=field.name,
                label=field.label,
                value=field.value,
                visible=field.visible,
                enabled=field.enabled,
                required=field.required,
            )
            for field in model.fields
        ],
    )


def state_from_row(row: ApplicationStateRow) -> ApplicationState:
    return ApplicationState(
        id=row.id,
        investigation_id=row.investigation_id,
        sequence=row.sequence,
        captured_at=row.captured_at,
        url=row.url,
        triggered_by_event_id=row.triggered_by_event_id,
        fields=[
            FieldState(
                name=field.name,
                label=field.label,
                value=field.value,
                visible=field.visible,
                enabled=field.enabled,
                required=field.required,
            )
            for field in row.fields
        ],
    )


def event_to_row(model: TimelineEvent) -> TimelineEventRow:
    return TimelineEventRow(
        id=model.id,
        investigation_id=model.investigation_id,
        type=model.type.value,
        description=model.description,
        occurred_at=model.occurred_at,
        state_before_id=model.state_before_id,
        state_after_id=model.state_after_id,
        evidence_ids=[str(item) for item in model.evidence_ids],
    )


def event_from_row(row: TimelineEventRow) -> TimelineEvent:
    return TimelineEvent.model_validate(
        {
            "id": row.id,
            "investigation_id": row.investigation_id,
            "type": row.type,
            "description": row.description,
            "occurred_at": row.occurred_at,
            "state_before_id": row.state_before_id,
            "state_after_id": row.state_after_id,
            "evidence_ids": row.evidence_ids or [],
        }
    )


def diff_to_row(model: StateDiff) -> StateTransitionRow:
    return StateTransitionRow(
        id=model.id,
        investigation_id=model.investigation_id,
        before_state_id=model.before_state_id,
        after_state_id=model.after_state_id,
        summary=model.summary,
        changes=[
            FieldChangeRow(
                field=change.field,
                attribute=change.attribute,
                before_value=None if change.before is None else str(change.before),
                after_value=None if change.after is None else str(change.after),
            )
            for change in model.changes
        ],
    )


def _coerce_value(raw: str | None) -> Any:
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "none":
        return None
    return raw


def diff_from_row(row: StateTransitionRow) -> StateDiff:
    return StateDiff(
        id=row.id,
        investigation_id=row.investigation_id,
        before_state_id=row.before_state_id,
        after_state_id=row.after_state_id,
        summary=row.summary,
        changes=[
            FieldChange(
                field=change.field,
                attribute=change.attribute,
                before=_coerce_value(change.before_value),
                after=_coerce_value(change.after_value),
            )
            for change in row.changes
        ],
    )


def evidence_to_row(model: Evidence) -> EvidenceRow:
    return EvidenceRow(
        id=model.id,
        investigation_id=model.investigation_id,
        type=model.type.value,
        sensitivity=model.sensitivity.value,
        captured_at=model.captured_at,
        url=model.url,
        knowledge_kind=model.knowledge_kind.value,
        confidence=model.confidence,
        artifact_uri=model.artifact_uri,
        content_hash=model.content_hash,
        payload=_jsonable(model.payload) or {},
    )


def evidence_from_row(row: EvidenceRow) -> Evidence:
    return Evidence.model_validate(
        {
            "id": row.id,
            "investigation_id": row.investigation_id,
            "type": row.type,
            "sensitivity": row.sensitivity,
            "captured_at": row.captured_at,
            "url": row.url,
            "knowledge_kind": row.knowledge_kind,
            "confidence": row.confidence,
            "artifact_uri": row.artifact_uri,
            "content_hash": row.content_hash,
            "payload": row.payload or {},
        }
    )


def rule_to_row(model: BusinessRule) -> RuleRow:
    return RuleRow(
        id=model.id,
        investigation_id=model.investigation_id,
        name=model.name,
        status=model.status.value,
        confidence=model.confidence,
        knowledge_kind=model.knowledge_kind.value,
        condition_field=model.condition.field,
        condition_operator=model.condition.operator,
        condition_value=None if model.condition.value is None else str(model.condition.value),
        effect_field=model.effect.field,
        effect_visible=model.effect.visible,
        effect_required=model.effect.required,
        effect_enabled=model.effect.enabled,
    )


def rule_from_row(
    row: RuleRow,
    evidence_ids: list[UUID] | None = None,
    verification_run_ids: list[UUID] | None = None,
) -> BusinessRule:
    return BusinessRule(
        id=row.id,
        investigation_id=row.investigation_id,
        name=row.name,
        status=row.status,  # type: ignore[arg-type]
        confidence=row.confidence,
        knowledge_kind=row.knowledge_kind,  # type: ignore[arg-type]
        condition=RuleCondition(
            field=row.condition_field,
            operator=row.condition_operator,
            value=row.condition_value,
        ),
        effect=RuleEffect(
            field=row.effect_field,
            visible=row.effect_visible,
            required=row.effect_required,
            enabled=row.effect_enabled,
        ),
        evidence_ids=evidence_ids or [],
        verification_run_ids=verification_run_ids or [],
    )


def experiment_to_row(model: VerificationRun) -> ExperimentRow:
    return ExperimentRow(
        id=model.id,
        rule_id=model.rule_id,
        investigation_id=model.investigation_id,
        status=model.status.value,
        confidence=model.confidence,
        results=[
            ExperimentResultRow(
                experiment_item_id=result.experiment_id,
                passed=result.passed,
                details=result.details,
                observation_id=result.observation_id,
            )
            for result in model.results
        ],
    )


def experiment_from_row(row: ExperimentRow) -> VerificationRun:
    return VerificationRun(
        id=row.id,
        rule_id=row.rule_id,
        investigation_id=row.investigation_id,
        status=row.status,  # type: ignore[arg-type]
        confidence=row.confidence,
        results=[
            VerificationExperimentResult(
                experiment_id=result.experiment_item_id,
                passed=result.passed,
                details=result.details,
                observation_id=result.observation_id,
            )
            for result in row.results
        ],
    )


def rule_evidence_links(rule_id: UUID, evidence_ids: list[UUID], relation: str = "supported_by") -> list[RuleEvidenceRow]:
    return [
        RuleEvidenceRow(rule_id=rule_id, evidence_id=evidence_id, relation=relation)
        for evidence_id in evidence_ids
    ]


def rule_experiment_links(
    rule_id: UUID,
    experiment_ids: list[UUID],
    relation: str = "verified_by",
) -> list[RuleExperimentRow]:
    return [
        RuleExperimentRow(rule_id=rule_id, experiment_id=experiment_id, relation=relation)
        for experiment_id in experiment_ids
    ]


def evaluation_run_to_row(model: EvaluationRun) -> EvaluationRunRow:
    return EvaluationRunRow(
        id=model.id,
        investigation_id=model.investigation_id,
        policy=model.policy,
        level=model.level,
        exploration_coverage=model.exploration_coverage,
        state_coverage=model.state_coverage,
        actions_taken=model.actions_taken,
        candidate_rules=model.candidate_rules,
        verified_rules=model.verified_rules,
        rules_per_action=model.rules_per_action,
        safety_violations=model.safety_violations,
        blocked_unsafe_actions=model.blocked_unsafe_actions,
        pages_seen=model.pages_seen,
        discovery_precision=model.discovery_precision,
        discovery_recall=model.discovery_recall,
        discovery_f1=model.discovery_f1,
        verification_accuracy=model.verification_accuracy,
        settle_timeouts=getattr(model, "settle_timeouts", 0) or 0,
        soft_nav_success_rate=getattr(model, "soft_nav_success_rate", None),
        routes_seen=getattr(model, "routes_seen", 0) or 0,
        created_at=model.created_at,
    )


def evaluation_run_from_row(row: EvaluationRunRow) -> EvaluationRun:
    return EvaluationRun.model_validate(
        {
            "id": row.id,
            "investigation_id": row.investigation_id,
            "policy": row.policy,
            "level": row.level,
            "exploration_coverage": row.exploration_coverage,
            "state_coverage": row.state_coverage,
            "actions_taken": row.actions_taken,
            "candidate_rules": row.candidate_rules,
            "verified_rules": row.verified_rules,
            "rules_per_action": row.rules_per_action,
            "safety_violations": row.safety_violations,
            "blocked_unsafe_actions": row.blocked_unsafe_actions,
            "pages_seen": row.pages_seen,
            "discovery_precision": row.discovery_precision,
            "discovery_recall": row.discovery_recall,
            "discovery_f1": row.discovery_f1,
            "verification_accuracy": row.verification_accuracy,
            "settle_timeouts": getattr(row, "settle_timeouts", 0) or 0,
            "soft_nav_success_rate": getattr(row, "soft_nav_success_rate", None),
            "routes_seen": getattr(row, "routes_seen", 0) or 0,
            "created_at": row.created_at,
        }
    )


def workflow_to_row(model: "Workflow") -> "WorkflowRow":
    from api.db.schema import WorkflowRow

    return WorkflowRow(
        id=model.id,
        investigation_id=model.investigation_id,
        name=model.name,
        steps=[step.model_dump(mode="json") for step in model.steps],
        trigger_action_ids=list(model.trigger_action_ids),
        confidence=model.confidence,
        created_at=model.created_at,
    )


def workflow_from_row(row: "WorkflowRow") -> "Workflow":
    from webtwin_core.models.workflow import Workflow, WorkflowStep

    return Workflow(
        id=row.id,
        investigation_id=row.investigation_id,
        name=row.name,
        steps=[WorkflowStep.model_validate(step) for step in (row.steps or [])],
        trigger_action_ids=list(row.trigger_action_ids or []),
        confidence=row.confidence,
        created_at=row.created_at,
    )


def network_event_to_row(value) -> "NetworkEventRow":
    from datetime import UTC, datetime
    from uuid import UUID

    from api.db.schema import NetworkEventRow

    if isinstance(value, dict):
        data = value
    else:
        data = value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)

    def _uuid(raw):
        if raw is None:
            return None
        return raw if isinstance(raw, UUID) else UUID(str(raw))

    captured = data.get("captured_at")
    if isinstance(captured, str):
        captured_at = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    elif captured is None:
        captured_at = datetime.now(UTC)
    else:
        captured_at = captured

    return NetworkEventRow(
        id=_uuid(data.get("id")),
        investigation_id=_uuid(data["investigation_id"]),
        timeline_event_id=_uuid(data.get("timeline_event_id")),
        method=str(data.get("method") or "GET"),
        url=str(data.get("url") or ""),
        status_code=data.get("status_code"),
        timing_ms=data.get("timing_ms"),
        request_headers=data.get("request_headers") or {},
        response_headers=data.get("response_headers") or {},
        body_shape=data.get("body_shape") or {},
        evidence_id=_uuid(data.get("evidence_id")),
        captured_at=captured_at,
    )


def network_event_from_row(row: "NetworkEventRow") -> dict:
    return {
        "id": str(row.id),
        "investigation_id": str(row.investigation_id),
        "timeline_event_id": str(row.timeline_event_id) if row.timeline_event_id else None,
        "method": row.method,
        "url": row.url,
        "status_code": row.status_code,
        "timing_ms": row.timing_ms,
        "request_headers": row.request_headers or {},
        "response_headers": row.response_headers or {},
        "body_shape": row.body_shape or {},
        "evidence_id": str(row.evidence_id) if row.evidence_id else None,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
    }


def discovered_link_to_row(link) -> "DiscoveredLinkRow":
    from api.db.schema import DiscoveredLinkRow

    return DiscoveredLinkRow(
        id=link.id,
        investigation_id=link.investigation_id,
        from_screen_id=link.from_screen_id,
        to_screen_id=link.to_screen_id,
        href=link.href,
        label=link.label,
        selector=link.selector,
        link_type=link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type),
        visited=link.visited,
        discovered_at=link.discovered_at,
    )


def discovered_link_from_row(row: "DiscoveredLinkRow"):
    from webtwin_core.reference_system.site_graph import DiscoveredLink, LinkType

    return DiscoveredLink(
        id=row.id,
        investigation_id=row.investigation_id,
        from_screen_id=row.from_screen_id,
        to_screen_id=row.to_screen_id,
        href=row.href,
        label=row.label,
        selector=row.selector,
        link_type=LinkType(row.link_type),
        visited=row.visited,
        discovered_at=row.discovered_at,
    )
