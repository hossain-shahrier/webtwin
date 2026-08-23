from webtwin_core.models import (
    BusinessRule,
    Evidence,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.models.evidence import EvidenceType

from api.services import investigations as svc
from api.store import store


def test_ask_question_with_citations() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="test", target_url="file:///tmp/x.html")
    )
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "condition shows reason"},
    )
    store.evidence[evidence.id] = evidence
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition affects reason visibility",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.85,
        status=RuleStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    store.rules[rule.id] = rule

    answer = svc.ask_question(investigation.id, "Why does reason appear?")
    assert answer.refused is False
    assert answer.citations[0].rule_id == rule.id
