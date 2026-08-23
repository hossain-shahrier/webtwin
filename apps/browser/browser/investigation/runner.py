import os
from pathlib import Path
from uuid import UUID

import httpx
from playwright.sync_api import Page, sync_playwright
from webtwin_core.defaults import DEFAULT_API_URL
from webtwin_core.evaluation.metrics import ExplorationMetrics, compute_exploration_metrics
from webtwin_core.exploration import ExplorationBudget, PolicyName
from webtwin_core.models import (
    AuthState,
    BusinessRule,
    Investigation,
    InvestigationGoal,
    InvestigationGoalType,
    InvestigationStatus,
    TimelineEvent,
    TimelineEventType,
    TransitionEvent,
)

from browser.client.api import ApiClient
from browser.exploration.controller import ExplorationController
from browser.observer.snapshot import capture_observation
from browser.recorder.timeline import TimelineRecorder
from browser.session.manager import SessionManager
from browser.session.auth_wait import wait_for_dashboard_auth_resume
from browser.session.store import SessionStore
from browser.verification.runner import verify_rule_on_page


def _set_field(page: Page, field: str, value: str) -> None:
    locator = page.locator(f'#{field}, [name="{field}"]')
    if value == "__click__":
        locator.click()
        page.wait_for_timeout(200)
        return
    tag = locator.evaluate("(el) => el.tagName.toLowerCase()")
    if tag == "select":
        locator.select_option(value)
    elif tag == "button" or (tag == "input" and locator.get_attribute("type") in {"button", "submit"}):
        locator.click()
    else:
        locator.fill(value)
    page.wait_for_timeout(150)


def _transition(
    client: ApiClient,
    investigation_id: UUID,
    event: TransitionEvent,
    reason: str | None = None,
    auth_pause=None,
) -> None:
    client.transition(investigation_id, event, reason, auth_pause)


def _handle_auth(
    page: Page,
    context,
    client: ApiClient,
    investigation_id: UUID,
    session_manager: SessionManager,
    session_store: SessionStore,
) -> None:
    pause_metadata = session_manager.detect_pause(
        page.url,
        SessionManager.password_field_visible(page),
        SessionManager.otp_field_visible(page),
    )
    if pause_metadata is not None:
        _transition(
            client,
            investigation_id,
            TransitionEvent.AUTH_REQUIRED,
            reason=pause_metadata.reason.value,
            auth_pause=pause_metadata,
        )
        client.upsert_session(investigation_id, auth_state=AuthState.REQUIRED)
        wait_for_dashboard_auth_resume(
            client,
            investigation_id,
            page,
            context,
            session_store,
            session_manager,
        )
    else:
        _transition(client, investigation_id, TransitionEvent.AUTH_OK)
        client.upsert_session(investigation_id, auth_state=AuthState.AUTHENTICATED)


def _fetch_rules(client: ApiClient, investigation_id: UUID) -> list[BusinessRule]:
    return [
        BusinessRule.model_validate(rule)
        for rule in httpx.get(f"{client.base_url}/investigations/{investigation_id}/rules").json()
    ]


def _exploration_loop(
    page: Page,
    client: ApiClient,
    investigation_id: UUID,
    controller: ExplorationController,
    timeline: TimelineRecorder,
    network=None,
) -> int:
    """Observe → plan → act → diff → rules until budget or coverage exhausted."""
    _transition(client, investigation_id, TransitionEvent.BEGIN_EXPLORATION)
    _transition(client, investigation_id, TransitionEvent.CAPTURE_OBSERVATION)

    before_observation = capture_observation(page, investigation_id)
    controller.record_state_signature(before_observation)
    client.record_observation(before_observation)
    before_state = client.record_state(before_observation.to_application_state(sequence=1))
    timeline.record(
        client.record_event(
            TimelineEvent(
                investigation_id=investigation_id,
                type=TimelineEventType.NAVIGATE,
                description=f"Opened {page.url}",
            )
        )
    )

    actions_taken = 1
    sequence = 2

    while True:
        plan = controller.plan_next(page, investigation_id)
        if plan is None:
            break

        investigation = client.get_investigation(investigation_id)
        if investigation.status == InvestigationStatus.OBSERVING:
            _transition(client, investigation_id, TransitionEvent.BEGIN_EXPLORATION)

        controller.apply_plan(page, plan)
        actions_taken += 1
        timeline.record(
            client.record_event(
                TimelineEvent(
                    investigation_id=investigation_id,
                    type=TimelineEventType.SELECT,
                    description=f"{plan.action.target}={plan.value} ({plan.reason})",
                )
            )
        )

        _transition(client, investigation_id, TransitionEvent.CAPTURE_OBSERVATION)
        after_observation = capture_observation(page, investigation_id)
        controller.record_state_signature(after_observation)
        client.record_observation(after_observation)
        after_state = client.record_state(after_observation.to_application_state(sequence=sequence))
        client.diff_states(investigation_id, before_state.id, after_state.id)

        before_observation = after_observation
        before_state = after_state
        sequence += 1

    if network is not None:
        nearest = timeline.events[-1].id if timeline.events else None
        for evidence in network.to_evidence(timeline_event_id=nearest):
            client.record_evidence(evidence)

    _transition(client, investigation_id, TransitionEvent.GENERATE_RULES)
    return actions_taken


def run_exploration_and_verification(
    target: Path | str,
    *,
    policy: PolicyName = "first_unexplored",
    api_base_url: str | None = None,
    headless: bool = True,
    budget: ExplorationBudget | None = None,
    seed: int | None = None,
    investigation_id: UUID | None = None,
) -> tuple[UUID, list[BusinessRule], list[BusinessRule], int, ExplorationMetrics]:
    from browser.observer.network import NetworkCollector
    from urllib.parse import urlparse

    client = ApiClient(api_base_url or os.environ.get("WEBTWIN_API_URL") or DEFAULT_API_URL)
    session_manager = SessionManager()
    session_store = SessionStore()
    timeline = TimelineRecorder()
    controller = ExplorationController(
        policy=policy,
        budget=budget or ExplorationBudget(max_actions=int(os.environ.get("WEBTWIN_MAX_ACTIONS", "20"))),
        seed=seed,
    )
    candidate_rules: list[BusinessRule] = []
    verified_rules: list[BusinessRule] = []
    actions_taken = 0

    if isinstance(target, Path):
        target_url = target.as_uri()
        target_name = target.name
        target_scope = target.parent.name
    else:
        target_url = target
        parsed = urlparse(target_url)
        target_name = Path(parsed.path).name or "target"
        target_scope = "worker"

    if investigation_id is not None:
        investigation = client.get_investigation(investigation_id)
        target_url = investigation.target_url or target_url
        if investigation.status == InvestigationStatus.CREATED:
            investigation = client.claim_investigation(investigation_id)
        if investigation.status == InvestigationStatus.INITIALIZING:
            _transition(client, investigation.id, TransitionEvent.INIT_COMPLETE)
    else:
        investigation = client.create_investigation(
            Investigation(
                goal=f"Explore business logic in {target_name}",
                target_url=target_url,
                feature_scope=target_scope,
                application_version=os.environ.get("WEBTWIN_APP_VERSION", "synthetic-1"),
                environment=os.environ.get("WEBTWIN_ENVIRONMENT", "eval"),
                role_scope=os.environ.get("WEBTWIN_ROLE_SCOPE"),
                goal_spec=InvestigationGoal(
                    type=InvestigationGoalType.DISCOVER_BUSINESS_LOGIC,
                    target=target_url,
                    scope=target_scope,
                    description=f"Explore business logic in {target_name}",
                ),
            )
        )
        client.upsert_session(investigation.id, auth_state=AuthState.UNKNOWN)
        _transition(client, investigation.id, TransitionEvent.START)
        _transition(client, investigation.id, TransitionEvent.INIT_COMPLETE)

    client.upsert_session(investigation.id, auth_state=AuthState.UNKNOWN)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = session_store.new_context(browser, investigation.id)
        page = context.new_page()
        network = NetworkCollector(investigation.id)
        network.attach(page)

        try:
            page.goto(target_url)
            _handle_auth(page, context, client, investigation.id, session_manager, session_store)
            actions_taken = _exploration_loop(
                page, client, investigation.id, controller, timeline, network=network
            )

            candidate_rules = _fetch_rules(client, investigation.id)
            controller.state.register_rules(candidate_rules)
            controller.known_rules = candidate_rules

            # Return to the investigation target before verification experiments
            page.goto(target_url)
            page.wait_for_timeout(100)
            page_fields = {
                element.name or element.selector.lstrip("#")
                for element in capture_observation(page, investigation.id, with_screenshot=False).elements
            }

            for rule in candidate_rules:
                if rule.condition.field not in page_fields and rule.condition.operator != "clicked":
                    verified_rules.append(rule)
                    continue
                _transition(client, investigation.id, TransitionEvent.START_VERIFICATION)
                updated = verify_rule_on_page(page, client, investigation.id, rule)
                verified_rules.append(updated)
                actions_taken += 2
                _transition(client, investigation.id, TransitionEvent.VERIFICATION_COMPLETE)

            session_store.save(context, investigation.id)
            _transition(client, investigation.id, TransitionEvent.COMPLETE)
        except Exception as error:
            current = client.get_investigation(investigation.id)
            if current.status not in {
                InvestigationStatus.FAILED,
                InvestigationStatus.CANCELLED,
                InvestigationStatus.COMPLETED,
            }:
                _transition(client, investigation.id, TransitionEvent.FAIL, reason=str(error))
            raise
        finally:
            context.close()
            browser.close()

    pages_seen = len(controller.state.pages_seen_urls) or len(controller.state.states_seen) or 1
    verified_count = sum(1 for rule in verified_rules if rule.status.value == "verified")
    exploration_metrics = compute_exploration_metrics(
        policy=policy,
        state=controller.state,
        candidate_rules=len(candidate_rules),
        verified_rules=verified_count,
        actions_taken=actions_taken,
        safety_violations=controller.safety_violations,
        blocked_unsafe_actions=controller.blocked_unsafe_actions,
        pages_seen=pages_seen,
    )
    from webtwin_core.evaluation.runs import EvaluationRun

    client.record_metrics(
        investigation.id,
        EvaluationRun.from_exploration_metrics(investigation.id, exploration_metrics),
    )
    return investigation.id, candidate_rules, verified_rules, actions_taken, exploration_metrics


def run_discovery_and_verification(
    target: Path,
    discovery_actions: list[dict[str, str]],
    api_base_url: str | None = None,
    headless: bool = True,
) -> tuple[UUID, list[BusinessRule], list[BusinessRule], int]:
    """Fixed-action discovery path (M1/M2 benchmark compatibility)."""
    from browser.observer.network import NetworkCollector

    client = ApiClient(api_base_url or os.environ.get("WEBTWIN_API_URL") or DEFAULT_API_URL)
    session_manager = SessionManager()
    session_store = SessionStore()
    timeline = TimelineRecorder()
    actions_taken = 0
    candidate_rules: list[BusinessRule] = []
    verified_rules: list[BusinessRule] = []

    investigation = client.create_investigation(
        Investigation(
            goal=f"Discover business logic in {target.name}",
            target_url=target.as_uri(),
            feature_scope=target.parent.name,
            application_version=os.environ.get("WEBTWIN_APP_VERSION", "synthetic-1"),
            environment=os.environ.get("WEBTWIN_ENVIRONMENT", "eval"),
            role_scope=os.environ.get("WEBTWIN_ROLE_SCOPE"),
            goal_spec=InvestigationGoal(
                type=InvestigationGoalType.DISCOVER_BUSINESS_LOGIC,
                target=target.as_uri(),
                scope=target.parent.name,
                description=f"Discover business logic in {target.name}",
            ),
        )
    )

    client.upsert_session(investigation.id, auth_state=AuthState.UNKNOWN)
    _transition(client, investigation.id, TransitionEvent.START)
    _transition(client, investigation.id, TransitionEvent.INIT_COMPLETE)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = session_store.new_context(browser, investigation.id)
        page = context.new_page()
        network = NetworkCollector(investigation.id)
        network.attach(page)

        try:
            page.goto(target.as_uri())
            actions_taken += 1
            _handle_auth(page, context, client, investigation.id, session_manager, session_store)

            _transition(client, investigation.id, TransitionEvent.BEGIN_EXPLORATION)
            _transition(client, investigation.id, TransitionEvent.CAPTURE_OBSERVATION)
            before_observation = capture_observation(page, investigation.id)
            client.record_observation(before_observation)
            before_state = client.record_state(before_observation.to_application_state(sequence=1))
            timeline.record(
                client.record_event(
                    TimelineEvent(
                        investigation_id=investigation.id,
                        type=TimelineEventType.NAVIGATE,
                        description=f"Opened {page.url}",
                    )
                )
            )

            _transition(client, investigation.id, TransitionEvent.BEGIN_EXPLORATION)
            for action in discovery_actions:
                _set_field(page, action["field"], action["value"])
                actions_taken += 1
                timeline.record(
                    client.record_event(
                        TimelineEvent(
                            investigation_id=investigation.id,
                            type=TimelineEventType.SELECT,
                            description=f"Set {action['field']}={action['value']}",
                        )
                    )
                )

            _transition(client, investigation.id, TransitionEvent.CAPTURE_OBSERVATION)
            after_observation = capture_observation(page, investigation.id)
            client.record_observation(after_observation)
            after_state = client.record_state(after_observation.to_application_state(sequence=2))
            client.diff_states(investigation.id, before_state.id, after_state.id)

            for evidence in network.to_evidence(
                timeline_event_id=timeline.events[-1].id if timeline.events else None
            ):
                client.record_evidence(evidence)

            _transition(client, investigation.id, TransitionEvent.GENERATE_RULES)
            candidate_rules = _fetch_rules(client, investigation.id)

            for rule in candidate_rules:
                _transition(client, investigation.id, TransitionEvent.START_VERIFICATION)
                updated = verify_rule_on_page(page, client, investigation.id, rule)
                verified_rules.append(updated)
                actions_taken += 2
                _transition(client, investigation.id, TransitionEvent.VERIFICATION_COMPLETE)

            session_store.save(context, investigation.id)
            _transition(client, investigation.id, TransitionEvent.COMPLETE)
        except Exception as error:
            current = client.get_investigation(investigation.id)
            if current.status not in {
                InvestigationStatus.FAILED,
                InvestigationStatus.CANCELLED,
                InvestigationStatus.COMPLETED,
            }:
                _transition(client, investigation.id, TransitionEvent.FAIL, reason=str(error))
            raise
        finally:
            context.close()
            browser.close()

    verified_count = sum(1 for rule in verified_rules if rule.status.value == "verified")
    rules_per_action = (verified_count / actions_taken) if actions_taken else 0.0
    from webtwin_core.evaluation.runs import EvaluationRun

    metrics_run = EvaluationRun(
        investigation_id=investigation.id,
        policy="fixed_discovery",
        level=target.parent.name,
        actions_taken=actions_taken,
        candidate_rules=len(candidate_rules),
        verified_rules=verified_count,
        rules_per_action=round(rules_per_action, 3),
        pages_seen=1,
        verification_accuracy=round(verified_count / len(verified_rules), 3) if verified_rules else 0.0,
    )
    client.record_metrics(investigation.id, metrics_run)

    return investigation.id, candidate_rules, verified_rules, actions_taken
