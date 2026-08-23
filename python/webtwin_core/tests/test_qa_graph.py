"""Graph-backed Ask path tests."""

from uuid import uuid4

from webtwin_core.models import BusinessRule, Evidence, RuleCondition, RuleEffect, RuleStatus
from webtwin_core.models.common import KnowledgeKind
from webtwin_core.models.evidence import EvidenceType
from webtwin_core.qa import answer_from_evidence


def test_graph_preferred_verified_rule_short_circuits() -> None:
    inv_id = uuid4()
    evidence = Evidence(
        investigation_id=inv_id,
        type=EvidenceType.DOM,
        payload={"summary": "province visible for IT"},
    )
    rule = BusinessRule(
        investigation_id=inv_id,
        name="country IT shows province",
        condition=RuleCondition(field="country", operator="equals", value="IT"),
        effect=RuleEffect(field="province", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        evidence_ids=[evidence.id],
    )
    answer = answer_from_evidence(
        "Why does province appear for Italy?",
        [rule],
        [evidence],
        preferred_rule_ids=[rule.id],
    )
    assert answer.refused is False
    assert answer.knowledge_kind == KnowledgeKind.OBSERVED
    assert "province" in answer.answer.lower()
    assert "graph" in answer.answer.lower()
