from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    Evidence,
    FieldState,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.models.evidence import EvidenceType
from webtwin_core.qa import answer_from_evidence


def test_answer_why_end_date_appears() -> None:
    investigation_id = __import__("uuid").uuid4()
    evidence = Evidence(
        investigation_id=investigation_id,
        type=EvidenceType.DOM,
        payload={"summary": "employment_type -> end_date"},
    )
    rule = BusinessRule(
        investigation_id=investigation_id,
        name="employment_type affects end_date visibility",
        condition=RuleCondition(field="employment_type", operator="equals", value="contract"),
        effect=RuleEffect(field="end_date", visible=True),
        confidence=0.9,
        status=RuleStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    answer = answer_from_evidence("Why does End Date appear?", [rule], [evidence])
    assert answer.refused is False
    assert answer.citations
    assert answer.citations[0].rule_id == rule.id
    assert "end_date" in answer.answer.lower()


def test_refuse_without_evidence() -> None:
    answer = answer_from_evidence("What is the meaning of life?", [], [])
    assert answer.refused is True
