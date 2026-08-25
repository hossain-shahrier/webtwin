"""Negative Space Spec — evidence-backed assert_never clauses for clone exports."""

from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule
from webtwin_core.verification.engine import _alternate_value


class AbsenceAssertion(BaseModel):
    """Proven absence: under this condition, an effect must NOT hold."""

    id: str
    condition_field: str
    condition_operator: str = "equals"
    condition_value: str | bool | int | float | None = None
    effect_field: str
    assert_attribute: str = "visible"
    assert_value: bool = False
    source_rule_id: str | None = None
    confidence: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    test_scenario: str = ""
    setup_fields: dict[str, str] = Field(default_factory=dict)


_BINARY = {"yes", "no", "true", "false", "0", "1", "on", "off"}


def _absence_id(
    condition_field: str,
    condition_value: object,
    effect_field: str,
    assert_attribute: str,
    assert_value: bool,
) -> str:
    key = (
        f"{condition_field}|{condition_value!r}|{effect_field}|"
        f"{assert_attribute}|{assert_value}"
    )
    return str(uuid5(NAMESPACE_URL, f"webtwin:absence:{key}"))


def _scenario(
    condition_field: str,
    condition_operator: str,
    condition_value: object,
    effect_field: str,
    assert_attribute: str,
    assert_value: bool,
    setup: dict[str, str] | None = None,
) -> str:
    setup_bits = ""
    if setup:
        setup_bits = " after setting " + ", ".join(
            f"{key}={value!r}" for key, value in setup.items()
        )
    return (
        f"Given {condition_field} {condition_operator} {condition_value!r}{setup_bits}, "
        f"assert_never {effect_field}.{assert_attribute}={not assert_value} "
        f"(must be {assert_value})"
    )


def derive_absences_from_rules(
    rules: list[BusinessRule],
    *,
    alternate_options_by_field: dict[str, list[str]] | None = None,
) -> list[AbsenceAssertion]:
    """Derive assert_never clauses from verified visibility rules.

    Sources:
    - Hide rules (visible=False) → absence under the positive condition
    - Show rules with binary triggers → absence under the alternate value
    """
    options_map = alternate_options_by_field or {}
    absences: list[AbsenceAssertion] = []
    seen: set[str] = set()

    verified = [rule for rule in rules if rule.status.value == "verified"]
    for rule in verified:
        effect_field = rule.effect.field
        condition_field = rule.condition.field
        condition_value = rule.condition.value
        evidence_ids = [str(eid) for eid in rule.evidence_ids]
        setup = dict(rule.setup_fields or {})

        # Direct hide / never-show under this condition
        if rule.effect.visible is False:
            absence_id = _absence_id(
                condition_field, condition_value, effect_field, "visible", False
            )
            if absence_id not in seen:
                seen.add(absence_id)
                absences.append(
                    AbsenceAssertion(
                        id=absence_id,
                        condition_field=condition_field,
                        condition_operator=rule.condition.operator,
                        condition_value=condition_value,
                        effect_field=effect_field,
                        assert_attribute="visible",
                        assert_value=False,
                        source_rule_id=str(rule.id),
                        confidence=rule.confidence,
                        evidence_ids=evidence_ids,
                        rationale=(
                            f"Verified hide rule '{rule.name}': {effect_field} must not "
                            f"appear when {condition_field}={condition_value!r}."
                        ),
                        test_scenario=_scenario(
                            condition_field,
                            rule.condition.operator,
                            condition_value,
                            effect_field,
                            "visible",
                            False,
                            setup,
                        ),
                        setup_fields=setup,
                    )
                )

        # Exclusive show rules: binary alternate must not show the effect
        if rule.effect.visible is True and rule.condition.operator == "equals":
            trigger = str(condition_value) if condition_value is not None else ""
            options = options_map.get(condition_field)
            alternate = _alternate_value(trigger, options)
            is_binary = trigger.lower() in _BINARY
            if alternate is not None and is_binary:
                absence_id = _absence_id(
                    condition_field, alternate, effect_field, "visible", False
                )
                if absence_id not in seen:
                    seen.add(absence_id)
                    absences.append(
                        AbsenceAssertion(
                            id=absence_id,
                            condition_field=condition_field,
                            condition_operator="equals",
                            condition_value=alternate,
                            effect_field=effect_field,
                            assert_attribute="visible",
                            assert_value=False,
                            source_rule_id=str(rule.id),
                            confidence=min(rule.confidence, 0.9),
                            evidence_ids=evidence_ids,
                            rationale=(
                                f"Exclusive with verified show rule '{rule.name}': when "
                                f"{condition_field}={alternate!r}, {effect_field} must stay hidden."
                            ),
                            test_scenario=_scenario(
                                condition_field,
                                "equals",
                                alternate,
                                effect_field,
                                "visible",
                                False,
                                setup,
                            ),
                            setup_fields=setup,
                        )
                    )

    absences.sort(key=lambda item: (item.condition_field, item.effect_field, str(item.condition_value)))
    return absences


def format_absences_markdown(absences: list[AbsenceAssertion]) -> list[str]:
    if not absences:
        return ["_No proven absences yet — exclusive experiments may still be pending._"]
    lines: list[str] = []
    for item in absences:
        lines.append(
            f"- **assert_never** `{item.effect_field}.{item.assert_attribute}` "
            f"when `{item.condition_field} {item.condition_operator} {item.condition_value!r}` "
            f"(confidence={item.confidence})"
        )
        if item.rationale:
            lines.append(f"  - {item.rationale}")
        if item.test_scenario:
            lines.append(f"  - scenario: {item.test_scenario}")
    return lines
