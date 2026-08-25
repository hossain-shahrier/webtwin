from uuid import uuid4

from webtwin_core.capsules import build_prompt_capsules
from webtwin_core.counterfactual import CounterfactualRequest, plan_counterfactual
from webtwin_core.models import BusinessRule, Evidence, RuleCondition, RuleEffect, RuleStatus
from webtwin_core.models.evidence import EvidenceType


def test_capsule_requires_resolvable_evidence() -> None:
    investigation_id = uuid4()
    evidence = Evidence(
        investigation_id=investigation_id,
        type=EvidenceType.DOM,
        payload={"summary": "condition -> reason"},
    )
    verified = BusinessRule(
        investigation_id=investigation_id,
        name="condition shows reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        evidence_ids=[evidence.id],
    )
    orphan = BusinessRule(
        investigation_id=investigation_id,
        name="no evidence rule",
        condition=RuleCondition(field="x", operator="equals", value="1"),
        effect=RuleEffect(field="y", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.9,
        evidence_ids=[],
    )
    export = build_prompt_capsules(investigation_id, [verified, orphan], [evidence])
    assert len(export.capsules) == 1
    assert export.capsules[0].prompt_markdown.startswith("# WebTwin Prompt Capsule")
    assert "Required evidence" in export.capsules[0].prompt_markdown
    assert "no evidence rule" in export.skipped_without_evidence


def test_plan_counterfactual_marks_absence_hypothesis() -> None:
    plan = plan_counterfactual(
        CounterfactualRequest(
            condition_field="country",
            condition_value="FR",
            effect_field="province",
            expect_visible=False,
        )
    )
    assert plan.hypothesized_absence is True
    assert plan.experiment.set_fields["country"] == "FR"
    assert plan.experiment.expectations["province"]["visible"] is False
    assert plan.status == "planned"
