from playwright.sync_api import Page
from webtwin_core.exploration.budget import ExplorationBudget
from webtwin_core.models import BusinessRule
from webtwin_core.models.observation import Observation
from webtwin_core.verification.engine import (
    VerificationExperimentResult,
    evaluate_expectations,
    evaluate_network_expectations,
    generate_verification_experiments,
    summarize_verification,
)

from browser.client.api import ApiClient
from browser.observer.network import NetworkCollector
from browser.observer.settle import settle_after_action
from browser.observer.snapshot import capture_observation


def _candidates_for_field(observation: Observation | None, field: str) -> list[str]:
    """Prefer observation selectors/stable_key candidates over name-only heuristics."""
    if observation is None:
        return []
    candidates: list[str] = []
    for element in observation.elements:
        keys = {
            element.stable_key,
            element.name,
            element.selector,
            (element.selector or "").lstrip("#"),
        }
        if field not in keys:
            continue
        if element.selector:
            candidates.append(element.selector)
        for item in element.selector_candidates or []:
            if item:
                candidates.append(item)
        if element.testid:
            candidates.append(f'[data-testid="{element.testid}"]')
        if element.name:
            candidates.append(f'[name="{element.name}"]')
        break
    return candidates


def _resolve_locator(page: Page, field: str, candidates: list[str] | None = None):
    selectors = list(candidates or [])
    selectors.extend(
        [
            f'[data-testid="{field}"]',
            f"#{field}",
            f'[name="{field}"]',
            f'[aria-label="{field}"]',
        ]
    )
    # de-dupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for sel in selectors:
        if sel and sel not in seen:
            seen.add(sel)
            ordered.append(sel)
    for sel in ordered:
        locator = page.locator(sel)
        if locator.count() > 0:
            return locator
    return page.locator(f'#{field}, [name="{field}"], [data-testid="{field}"]')


def _set_field(page: Page, field: str, value: str, *, candidates: list[str] | None = None) -> None:
    locator = _resolve_locator(page, field, candidates)
    if value == "__click__":
        locator.first.click(timeout=5000)
        settle_after_action(page)
        return
    if locator.count() == 0:
        raise RuntimeError(f"Field not found for verification: {field}")
    tag = locator.first.evaluate("(el) => el.tagName.toLowerCase()")
    if tag == "select":
        locator.first.select_option(value)
    elif tag == "button" or (tag == "input" and locator.first.get_attribute("type") == "button"):
        locator.first.click()
    else:
        locator.first.fill(value)
    settle_after_action(page)


def soft_return_to_route(page: Page, route_path: str) -> None:
    """Return to a SPA route via hash/History click when possible; fall back to hash assign."""
    if not route_path:
        return
    link = page.locator(
        f'a[href="{route_path}"], a[href="#{route_path.lstrip("#")}"], '
        f'[data-testid="nav-{route_path.strip("/#")}"]'
    )
    if link.count() > 0:
        link.first.click()
        settle_after_action(
            page,
            expect_url_contains=route_path.lstrip("#")[:24] if route_path else None,
        )
        return
    if route_path.startswith("#") or route_path.startswith("/"):
        hash_target = route_path if route_path.startswith("#") else f"#{route_path.lstrip('/')}"
        page.evaluate("(h) => { location.hash = h }", hash_target)
        settle_after_action(page, expect_url_contains=hash_target)
        return
    page.goto(route_path)
    settle_after_action(page)


def verify_rule_on_page(
    page: Page,
    client: ApiClient,
    investigation_id,
    rule: BusinessRule,
    sequence_start: int = 10,
    *,
    spa_mode: bool = False,
    baseline_route: str | None = None,
    budget: ExplorationBudget | None = None,
    network: NetworkCollector | None = None,
) -> BusinessRule:
    experiments = generate_verification_experiments(rule)
    results: list[VerificationExperimentResult] = []

    for index, experiment in enumerate(experiments):
        if budget is not None and not budget.can_run_experiment():
            results.append(
                VerificationExperimentResult(
                    experiment_id=experiment.id,
                    passed=False,
                    details="verification budget exhausted (max_experiments)",
                )
            )
            break
        if budget is not None:
            budget.consume_experiment()

        events_before = len(network.events) if network is not None else 0
        try:
            if spa_mode and baseline_route:
                soft_return_to_route(page, baseline_route)
            # Capture current DOM so we can resolve stable_key → real selectors
            locator_obs = capture_observation(page, investigation_id, with_screenshot=False)
            for field, value in experiment.set_fields.items():
                _set_field(
                    page,
                    field,
                    value,
                    candidates=_candidates_for_field(locator_obs, field),
                )

            observation = capture_observation(page, investigation_id)
            client.record_observation(observation)
            state = client.record_state(
                observation.to_application_state(sequence=sequence_start + index)
            )
            passed, details = evaluate_expectations(state, experiment.expectations)
            if passed and experiment.network_expectations and network is not None:
                new_events = network.events[events_before:]
                net_passed, net_details = evaluate_network_expectations(
                    new_events, experiment.network_expectations
                )
                if not net_passed:
                    passed, details = False, net_details
        except Exception as error:
            passed, details = False, f"verification error: {error}"
            observation = None

        results.append(
            VerificationExperimentResult(
                experiment_id=experiment.id,
                passed=passed,
                details=details,
                observation_id=observation.id if observation is not None else None,
            )
        )

    run = summarize_verification(rule, results)
    updated = client.verify_rule(investigation_id, rule.id, run)
    return updated
