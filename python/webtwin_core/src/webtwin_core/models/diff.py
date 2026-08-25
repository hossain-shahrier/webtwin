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

    def _is_nav_chrome(name: str) -> bool:
        lowered = name.lower()
        # Substring "nav"/"menu" is too broad (matches "unavailable", etc.)
        nav_tokens = (
            lowered.startswith("nav_")
            or lowered.endswith("_nav")
            or "_nav_" in lowered
            or lowered in {"navbar", "navigation", "main_nav", "main_menu", "main_menu_toggle"}
            or lowered.startswith("menu_")
            or lowered.endswith("_menu")
            or lowered.endswith("_menu_toggle")
        )
        return (
            lowered == "a"
            or lowered.startswith("a[")
            or "href=" in lowered
            or lowered.startswith("visit_")
            or lowered.endswith("_icon_link")
            or lowered.endswith("_nav_link")
            or lowered in {"q", "query", "search", "s", "account_icon_link", "gorur_ghash"}
            or nav_tokens
            or lowered.startswith("_wp_")
            or lowered.startswith("wc_order_attribution")
            or "nonce" in lowered
        )

    def _looks_like_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = value.strip().lower()
        if text.startswith(("http://", "https://", "mailto:", "tel:")):
            return True
        # Absolute site paths used as nav action payloads (not form values)
        if text.startswith("/") and len(text) > 1 and " " not in text:
            return True
        return False

    def _is_form_control(name: str) -> bool:
        if _is_nav_chrome(name):
            return False
        # Prefer named inputs/selects over raw anchors
        return not name.lower().startswith("a[")

    value_changes = [
        change for change in diff.changes if change.attribute == "value" and change.before != change.after
    ]
    # SPA remounts often show up as appeared/disappeared rather than visible flips.
    visibility_changes = [
        change
        for change in diff.changes
        if (
            (change.attribute == "visible" and change.before is False and change.after is True)
            or (change.attribute == "appeared" and change.after is True)
        )
        and _is_form_control(change.field)
    ]
    hide_changes = [
        change
        for change in diff.changes
        if (
            (change.attribute == "visible" and change.before is True and change.after is False)
            or (change.attribute == "disappeared" and change.before is True)
        )
        and _is_form_control(change.field)
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
        if any(hint in name.lower() for hint in click_hints) and _is_form_control(name)
    ]
    primary_value_changes = []
    for change in value_changes:
        if not _is_form_control(change.field):
            continue
        after_field = after_fields.get(change.field)
        if after_field is not None and _looks_like_url(after_field.value):
            continue
        primary_value_changes.append(change)

    # One causal trigger per diff — latest value change (not Cartesian product)
    primary_trigger = primary_value_changes[-1] if primary_value_changes else None

    def _setup_fields(*, exclude: set[str]) -> dict[str, str]:
        setup: dict[str, str] = {}
        for name, field in after_fields.items():
            if name in exclude or not _is_form_control(name):
                continue
            if field.value in (None, "") or _looks_like_url(field.value):
                continue
            setup[name] = str(field.value)
        return setup

    if primary_trigger is not None:
        trigger = primary_trigger.field
        trigger_value = after_fields.get(trigger)
        if trigger_value is not None and trigger_value.value not in (None, ""):
            for visibility in visibility_changes:
                field_name = visibility.field.lower()
                if visibility.field == trigger:
                    continue
                if any(hint in visibility.field.lower() for hint in click_hints):
                    continue
                is_alert = any(
                    token in field_name for token in ("error", "alert", "validation", "warning")
                )
                if is_alert and click_fields:
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
                        confidence=0.62 if visibility.attribute == "appeared" else 0.6,
                        status=RuleStatus.CANDIDATE,
                        setup_fields=_setup_fields(exclude={trigger, visibility.field}),
                    )
                )

            for hidden in hide_changes:
                if hidden.field == trigger:
                    continue
                rules.append(
                    BusinessRule(
                        investigation_id=diff.investigation_id,
                        name=f"{trigger} hides {hidden.field}",
                        condition=RuleCondition(
                            field=trigger,
                            operator="equals",
                            value=trigger_value.value,
                        ),
                        effect=RuleEffect(field=hidden.field, visible=False),
                        confidence=0.58,
                        status=RuleStatus.CANDIDATE,
                        setup_fields=_setup_fields(exclude={trigger, hidden.field}),
                    )
                )

    # Validation / alert after click-style interactions (DOM-only; no invented network)
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
        if not click_fields:
            continue
        if not primary_value_changes or is_alert or not any(
            rule.effect.field == visibility.field and rule.effect.visible is True for rule in rules
        ):
            for click_field in click_fields:
                if field_name in {"q", "query", "search", "s"} and not is_alert:
                    continue
                rules.append(
                    BusinessRule(
                        investigation_id=diff.investigation_id,
                        name=f"{click_field} shows {visibility.field}",
                        condition=RuleCondition(field=click_field, operator="clicked", value=True),
                        effect=RuleEffect(field=visibility.field, visible=True),
                        confidence=0.55 if is_alert else 0.5,
                        status=RuleStatus.CANDIDATE,
                        setup_fields=_setup_fields(exclude={click_field, visibility.field}),
                    )
                )
                break

    # Required-field candidates — never invent a phantom "submitted" condition
    existing = {
        (rule.condition.field, rule.effect.field)
        for rule in rules
        if rule.effect.visible is True
    }
    for required in required_changes:
        if primary_trigger is None:
            continue
        trigger = primary_trigger.field
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
                setup_fields=_setup_fields(exclude={trigger, required.field}),
            )
        )

    enabled_changes = [
        change
        for change in diff.changes
        if change.attribute == "enabled" and change.before is True and change.after is False
    ]
    if primary_trigger is not None:
        for disabled in enabled_changes:
            field_name = disabled.field.lower()
            if not any(token in field_name for token in ("submit", "save", "continue", "next", "send")):
                continue
            trigger = primary_trigger.field
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

    # Deduplicate by signature — prefer equals over clicked for same effect field
    seen: set[tuple] = set()
    unique: list[BusinessRule] = []
    for rule in sorted(rules, key=lambda r: 0 if r.condition.operator == "equals" else 1):
        signature = (
            rule.condition.field,
            str(rule.condition.value),
            rule.effect.field,
            rule.effect.visible,
            rule.effect.required,
            getattr(rule.effect, "enabled", None),
        )
        effect_key = (rule.effect.field, rule.effect.visible)
        if any(
            (u.effect.field, u.effect.visible) == effect_key
            and u.condition.operator == "equals"
            and rule.condition.operator == "clicked"
            for u in unique
        ):
            continue
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(rule)
    return unique
