from uuid import uuid4

from webtwin_core.models import BusinessRule, RuleCondition, RuleEffect, RuleStatus
from webtwin_core.negative_space import derive_absences_from_rules


def test_derive_absence_from_binary_show_rule() -> None:
    rule = BusinessRule(
        investigation_id=uuid4(),
        name="condition shows reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        evidence_ids=[uuid4()],
    )
    absences = derive_absences_from_rules([rule])
    assert len(absences) == 1
    absence = absences[0]
    assert absence.condition_value == "yes"
    assert absence.effect_field == "reason"
    assert absence.assert_attribute == "visible"
    assert absence.assert_value is False
    assert "assert_never" in absence.test_scenario


def test_derive_absence_from_hide_rule() -> None:
    rule = BusinessRule(
        investigation_id=uuid4(),
        name="country hides province",
        condition=RuleCondition(field="country", operator="equals", value="US"),
        effect=RuleEffect(field="province", visible=False),
        status=RuleStatus.VERIFIED,
        confidence=0.9,
    )
    absences = derive_absences_from_rules([rule])
    assert len(absences) == 1
    assert absences[0].condition_value == "US"
    assert absences[0].assert_value is False


def test_candidates_do_not_emit_absences() -> None:
    rule = BusinessRule(
        investigation_id=uuid4(),
        name="guess",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        status=RuleStatus.CANDIDATE,
        confidence=0.5,
    )
    assert derive_absences_from_rules([rule]) == []
