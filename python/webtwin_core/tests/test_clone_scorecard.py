"""Tests for clone scorecard and network verification helpers."""

from uuid import uuid4

from webtwin_core.models import (
    BusinessRule,
    Investigation,
    InvestigationStatus,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.reference_system import build_reference_system_context
from webtwin_core.reference_system.clone_scorecard import compute_clone_scorecard
from webtwin_core.verification.engine import (
    evaluate_network_expectations,
    generate_verification_experiments,
)


class _FakeEvent:
    def __init__(self, method: str = "GET", status_code: int = 200) -> None:
        self.method = method
        self.status_code = status_code


def test_compute_clone_scorecard_flags_gaps() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="test",
        target_url="https://example.com",
        status=InvestigationStatus.COMPLETED,
    )
    reference = build_reference_system_context(investigation, observations=[], events=[], rules=[])
    scorecard = compute_clone_scorecard([], reference)
    assert scorecard.verified_rules == 0
    assert scorecard.clone_ready is False
    assert "No verified rules" in scorecard.gaps


def test_compute_clone_scorecard_ready_when_verified() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="test",
        target_url="https://example.com",
        status=InvestigationStatus.COMPLETED,
    )
    rule = BusinessRule(
        investigation_id=inv_id,
        name="show province",
        condition=RuleCondition(field="country", operator="equals", value="IT"),
        effect=RuleEffect(field="province", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        evidence_ids=[uuid4()],
    )
    reference = build_reference_system_context(
        investigation, observations=[], events=[], rules=[rule]
    )
    scorecard = compute_clone_scorecard([rule], reference, exploration_coverage=0.8)
    assert scorecard.verified_rules == 1
    assert scorecard.exploration_coverage == 0.8


def test_clicked_rule_includes_network_expectations() -> None:
    rule = BusinessRule(
        investigation_id=uuid4(),
        name="validate network",
        condition=RuleCondition(field="validate", operator="clicked", value=True),
        effect=RuleEffect(field="network_error", visible=True),
    )
    experiments = generate_verification_experiments(rule)
    assert len(experiments) == 1
    assert experiments[0].network_expectations.get("min_events") == 1


def test_evaluate_network_expectations() -> None:
    passed, _ = evaluate_network_expectations([], {"min_events": 1})
    assert passed is False
    passed, _ = evaluate_network_expectations([_FakeEvent()], {"min_events": 1})
    assert passed is True
