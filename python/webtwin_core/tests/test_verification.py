from webtwin_core.models.rule_status import RuleStatus
from webtwin_core.verification.engine import (
    VerificationExperimentResult,
    generate_verification_experiments,
    summarize_verification,
)
from webtwin_core.models import BusinessRule, RuleCondition, RuleEffect


def test_generate_verification_experiments_includes_positive_and_negative() -> None:
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="condition affects reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
    )
    experiments = generate_verification_experiments(rule)
    assert len(experiments) == 2
    assert experiments[0].set_fields["condition"] == "no"
    assert experiments[1].set_fields["condition"] == "yes"


def test_generate_verification_experiments_uses_select_options() -> None:
    from webtwin_core.verification.engine import _alternate_value

    assert _alternate_value("IT", ["IT", "FR", "DE"]) == "FR"
    # Non-binary select alternates must NOT invent exclusive visibility FPs
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="country shows province",
        condition=RuleCondition(field="country", operator="equals", value="IT"),
        effect=RuleEffect(field="province", visible=True),
    )
    experiments = generate_verification_experiments(rule, alternate_options=["IT", "FR", "DE"])
    assert experiments[0].set_fields["country"] == "IT"
    assert not any(
        exp.set_fields.get("country") == "FR" and exp.expectations.get("province", {}).get("visible") is False
        for exp in experiments
    )


def test_clicked_rule_includes_setup_and_skips_network_by_default() -> None:
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="submit shows validation_error",
        condition=RuleCondition(field="submit", operator="clicked", value=True),
        effect=RuleEffect(field="validation_error", visible=True),
        setup_fields={"start_date": "2020-01-01", "end_date": "2019-01-01"},
    )
    experiments = generate_verification_experiments(rule)
    assert len(experiments) == 1
    assert experiments[0].set_fields["submit"] == "__click__"
    assert experiments[0].set_fields["start_date"] == "2020-01-01"
    assert experiments[0].network_expectations == {}


def test_summarize_verification_budget_is_inconclusive_not_contradicted() -> None:
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="test",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.6,
    )
    results = [
        VerificationExperimentResult(
            experiment_id=__import__("uuid").uuid4(),
            passed=False,
            details="budget",
            inconclusive=True,
        ),
    ]
    run = summarize_verification(rule, results)
    assert run.status == RuleStatus.UNDER_VERIFICATION
    assert run.confidence == 0.6


def test_summarize_verification_marks_verified_when_all_pass() -> None:
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="test",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.6,
    )
    results = [
        VerificationExperimentResult(experiment_id=__import__("uuid").uuid4(), passed=True, details="ok"),
        VerificationExperimentResult(experiment_id=__import__("uuid").uuid4(), passed=True, details="ok"),
    ]
    run = summarize_verification(rule, results)
    assert run.status == RuleStatus.VERIFIED
    assert run.confidence == 0.95


def test_summarize_verification_marks_contradicted_when_all_fail() -> None:
    rule = BusinessRule(
        investigation_id=__import__("uuid").uuid4(),
        name="test",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.6,
    )
    results = [
        VerificationExperimentResult(experiment_id=__import__("uuid").uuid4(), passed=False, details="unexpected"),
        VerificationExperimentResult(experiment_id=__import__("uuid").uuid4(), passed=False, details="unexpected"),
    ]
    run = summarize_verification(rule, results)
    assert run.status == RuleStatus.CONTRADICTED
    assert run.confidence == 0.2
