from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.rule_status import RuleStatus
from webtwin_core.models.rules import BusinessRule, RuleCondition, RuleEffect
from webtwin_core.models.state import ApplicationState, FieldState


class FieldChange(BaseModel):
    field: str
    attribute: str
    before: Any
    after: Any


class StateDiff(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    before_state_id: UUID
    after_state_id: UUID
    changes: list[FieldChange] = Field(default_factory=list)
    summary: str = ""


def _field_map(state: ApplicationState) -> dict[str, FieldState]:
    return {field.name: field for field in state.fields}


def compute_state_diff(before: ApplicationState, after: ApplicationState) -> StateDiff:
    changes: list[FieldChange] = []
    before_fields = _field_map(before)
    after_fields = _field_map(after)
    all_names = sorted(set(before_fields) | set(after_fields))

    for name in all_names:
        prev = before_fields.get(name)
        nxt = after_fields.get(name)
        if prev is None and nxt is not None:
            changes.append(FieldChange(field=name, attribute="appeared", before=None, after=True))
            continue
        if prev is not None and nxt is None:
            changes.append(FieldChange(field=name, attribute="disappeared", before=True, after=None))
            continue
        if prev is None or nxt is None:
            continue

        for attribute in ("visible", "enabled", "required", "value"):
            old = getattr(prev, attribute)
            new = getattr(nxt, attribute)
            if old != new:
                changes.append(
                    FieldChange(field=name, attribute=attribute, before=old, after=new)
                )

    summaries = [
        f"{change.field}.{change.attribute}: {change.before!r} -> {change.after!r}"
        for change in changes
    ]
    summary = "; ".join(summaries) if summaries else "No observable field changes"

    return StateDiff(
        investigation_id=before.investigation_id,
        before_state_id=before.id,
        after_state_id=after.id,
        changes=changes,
        summary=summary,
    )


def infer_candidate_rules(
    diff: StateDiff,
    before: ApplicationState,
    after: ApplicationState,
) -> list[BusinessRule]:
    """Deterministic heuristics — no LLM."""
    rules: list[BusinessRule] = []
    before_fields = _field_map(before)
    after_fields = _field_map(after)

    value_changes = [
        change for change in diff.changes if change.attribute == "value" and change.before != change.after
    ]
    visibility_changes = [
        change
        for change in diff.changes
        if change.attribute == "visible" and change.before is False and change.after is True
    ]

    for visibility in visibility_changes:
        trigger = value_changes[0].field if value_changes else None
        if trigger is None:
            continue

        trigger_value = after_fields.get(trigger)
        if trigger_value is None or trigger_value.value is None:
            continue

        effect_field = after_fields.get(visibility.field)
        rules.append(
            BusinessRule(
                investigation_id=diff.investigation_id,
                name=f"{trigger} affects {visibility.field} visibility",
                condition=RuleCondition(
                    field=trigger,
                    operator="equals",
                    value=trigger_value.value,
                ),
                effect=RuleEffect(
                    field=visibility.field,
                    visible=True,
                    required=effect_field.required if effect_field else None,
                ),
                confidence=0.6,
                status=RuleStatus.CANDIDATE,
            )
        )

    return rules
