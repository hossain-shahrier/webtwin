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
    """Deterministic heuristics — no LLM. Supports multi-trigger and required-field rules."""
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
    required_changes = [
        change
        for change in diff.changes
        if change.attribute == "required" and change.before is False and change.after is True
    ]

    # Multi-trigger: prefer the latest value change as primary cause (reduces FP noise)
    click_hints = ("submit", "validate", "unlock", "login", "save", "continue", "next", "check")
    click_fields = [
        name
        for name in after_fields
        if any(hint in name.lower() for hint in click_hints)
    ]
    primary_value_changes = value_changes if value_changes else []

    for visibility in visibility_changes:
        field_name = visibility.field.lower()
        is_alert = any(token in field_name for token in ("error", "alert", "validation", "warning"))
        if is_alert and click_fields:
            continue
        # Skip newly revealed controls that are themselves buttons (not effect fields)
        if any(hint in visibility.field.lower() for hint in click_hints):
            continue
        for trigger_change in primary_value_changes:
            trigger = trigger_change.field
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
                    confidence=0.6 if len(value_changes) == 1 else 0.55,
                    status=RuleStatus.CANDIDATE,
                )
            )

    # Validation / alert / newly revealed fields after click-style interactions
    for visibility in visibility_changes:
        field_name = visibility.field.lower()
        is_alert = any(token in field_name for token in ("error", "alert", "validation", "warning"))
        if any(hint in field_name for hint in click_hints):
            continue
        if any(
            rule.effect.field == visibility.field
            and rule.effect.visible is True
            and rule.condition.operator == "clicked"
            for rule in rules
        ):
            continue
        if not value_changes or is_alert or not any(
            rule.effect.field == visibility.field and rule.effect.visible is True for rule in rules
        ):
            for click_field in click_fields or (["submit"] if is_alert else []):
                rules.append(
                    BusinessRule(
                        investigation_id=diff.investigation_id,
                        name=f"{click_field} shows {visibility.field}",
                        condition=RuleCondition(field=click_field, operator="clicked", value=True),
                        effect=RuleEffect(field=visibility.field, visible=True),
                        confidence=0.55 if is_alert else 0.5,
                        status=RuleStatus.CANDIDATE,
                    )
                )
                break

    # Required-field candidates — skip if visibility rule already covers same trigger+field
    existing = {
        (rule.condition.field, rule.effect.field)
        for rule in rules
        if rule.effect.visible is True
    }
    for required in required_changes:
        trigger = value_changes[-1].field if value_changes else None
        if trigger is None:
            # Fall back: field became required without a clear trigger — still emit weak candidate
            rules.append(
                BusinessRule(
                    investigation_id=diff.investigation_id,
                    name=f"{required.field} becomes required",
                    condition=RuleCondition(field=required.field, operator="equals", value="submitted"),
                    effect=RuleEffect(field=required.field, required=True),
                    confidence=0.4,
                    status=RuleStatus.CANDIDATE,
                )
            )
            continue
        if (trigger, required.field) in existing:
            continue
        trigger_value = after_fields.get(trigger)
        if trigger_value is None or trigger_value.value is None:
            continue
        rules.append(
            BusinessRule(
                investigation_id=diff.investigation_id,
                name=f"{trigger} makes {required.field} required",
                condition=RuleCondition(
                    field=trigger,
                    operator="equals",
                    value=trigger_value.value,
                ),
                effect=RuleEffect(field=required.field, required=True),
                confidence=0.65,
                status=RuleStatus.CANDIDATE,
            )
        )

    # Disabled / enabled transitions (e.g. submit button)
    enabled_changes = [
        change
        for change in diff.changes
        if change.attribute == "enabled" and change.before is True and change.after is False
    ]
    for disabled in enabled_changes:
        field_name = disabled.field.lower()
        if not any(token in field_name for token in ("submit", "save", "continue", "next", "send")):
            continue
        for trigger_change in primary_value_changes:
            trigger = trigger_change.field
            trigger_value = after_fields.get(trigger)
            if trigger_value is None or trigger_value.value is None:
                continue
            rules.append(
                BusinessRule(
                    investigation_id=diff.investigation_id,
                    name=f"{trigger} disables {disabled.field}",
                    condition=RuleCondition(
                        field=trigger,
                        operator="equals",
                        value=trigger_value.value,
                    ),
                    effect=RuleEffect(field=disabled.field, enabled=False),
                    confidence=0.55,
                    status=RuleStatus.CANDIDATE,
                )
            )

    # Deduplicate by signature
    seen: set[tuple] = set()
    unique: list[BusinessRule] = []
    for rule in rules:
        signature = (
            rule.condition.field,
            str(rule.condition.value),
            rule.effect.field,
            rule.effect.visible,
            rule.effect.required,
            getattr(rule.effect, "enabled", None),
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(rule)
    return unique
