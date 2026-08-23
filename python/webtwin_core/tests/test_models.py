from webtwin_core.models import BusinessRule, Investigation, RuleCondition, RuleEffect


def test_investigation_defaults() -> None:
    investigation = Investigation(goal="Understand Conditions", target_url="https://example.com")
    assert investigation.goal == "Understand Conditions"
    assert investigation.status == "created"


def test_business_rule_model() -> None:
    investigation = Investigation(goal="Test", target_url="https://example.com")
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="Contract shows End Date",
        condition=RuleCondition(field="employment_type", operator="equals", value="contract"),
        effect=RuleEffect(field="end_date", visible=True, required=True),
        confidence=0.96,
    )
    assert rule.effect.required is True
