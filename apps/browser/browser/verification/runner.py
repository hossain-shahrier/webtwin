from playwright.sync_api import Page
from webtwin_core.models import BusinessRule
from webtwin_core.verification.engine import (
    VerificationExperimentResult,
    evaluate_expectations,
    generate_verification_experiments,
    summarize_verification,
)

from browser.client.api import ApiClient
from browser.observer.snapshot import capture_observation


def _set_field(page: Page, field: str, value: str) -> None:
    locator = page.locator(f'#{field}, [name="{field}"]')
    tag = locator.evaluate("(el) => el.tagName.toLowerCase()")
    if tag == "select":
        locator.select_option(value)
    else:
        locator.fill(value)
    page.wait_for_timeout(150)


def verify_rule_on_page(
    page: Page,
    client: ApiClient,
    investigation_id,
    rule: BusinessRule,
    sequence_start: int = 10,
) -> BusinessRule:
    experiments = generate_verification_experiments(rule)
    results: list[VerificationExperimentResult] = []

    for index, experiment in enumerate(experiments):
        for field, value in experiment.set_fields.items():
            _set_field(page, field, value)

        observation = capture_observation(page, investigation_id)
        client.record_observation(observation)
        state = client.record_state(
            observation.to_application_state(sequence=sequence_start + index)
        )
        passed, details = evaluate_expectations(state, experiment.expectations)
        results.append(
            VerificationExperimentResult(
                experiment_id=experiment.id,
                passed=passed,
                details=details,
                observation_id=observation.id,
            )
        )

    run = summarize_verification(rule, results)
    updated = client.verify_rule(investigation_id, rule.id, run)
    return updated
