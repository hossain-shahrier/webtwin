import os
from pathlib import Path
from uuid import UUID

import httpx
from playwright.sync_api import Page, sync_playwright
from webtwin_core.defaults import DEFAULT_API_URL
from webtwin_core.evaluation.metrics import ExplorationMetrics, compute_exploration_metrics
from webtwin_core.exploration import ExplorationBudget, PolicyName, budget_for_policy
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
from browser.exploration.navigate import goto_resilient
from browser.exploration.progress_sync import ExplorationProgressSync
from browser.observer.snapshot import capture_observation
from browser.recorder.timeline import TimelineRecorder
from browser.session.manager import SessionManager
from browser.session.auth_wait import wait_for_dashboard_auth_resume
from browser.session.consent import dismiss_consent_banners
from browser.session.store import SessionStore
from browser.verification.runner import soft_return_to_route, verify_rule_on_page

_SCOPE_URL_PREFIX = {
    "catalog": "/product-category",
    "product": "/product",
    "checkout": "/checkout",
    "account": "/account",
}
_BEHAVIOR_SCOPES = {"checkout", "account"}
_POLICY_SCOPES = {"information_gain", "first_unexplored", "random", "site_map"}
_POST_EXPLORATION_STATUSES = {
    InvestigationStatus.GENERATING_RULE,
    InvestigationStatus.VERIFYING,
}
_RESUMABLE_STATUSES = {
    InvestigationStatus.EXPLORING,
    InvestigationStatus.OBSERVING,
    InvestigationStatus.AUTHENTICATED,
    InvestigationStatus.GENERATING_RULE,
    InvestigationStatus.VERIFYING,
}


def _resolve_exploration_config(
    investigation: Investigation,
    policy: PolicyName,
) -> tuple[PolicyName, str | None]:
    url_prefix = getattr(investigation, "url_prefix", None) or os.environ.get("WEBTWIN_URL_PREFIX")
    scope = getattr(investigation, "investigation_scope", None) or "full_site"
    if not url_prefix and scope in _SCOPE_URL_PREFIX:
        url_prefix = _SCOPE_URL_PREFIX[scope]
    resolved_policy: PolicyName = investigation.exploration_policy or policy
    if not investigation.exploration_policy:
        if scope in _BEHAVIOR_SCOPES:
            resolved_policy = "information_gain"
        elif scope == "full_site":
            resolved_policy = "site_map"
    return resolved_policy, url_prefix


def _investigation_goal(investigation: Investigation) -> InvestigationGoal | None:
    if investigation.goal_spec is not None:
        return investigation.goal_spec
    scope = (investigation.feature_scope or "").strip()
    if scope and scope.lower() not in _POLICY_SCOPES:
        return InvestigationGoal(
            type=InvestigationGoalType.DISCOVER_BUSINESS_LOGIC,
            target=investigation.target_url,
            scope=scope,
            description=investigation.goal,
        )
    return None


def _page_field_keys(page: Page, investigation_id: UUID) -> set[str]:
    return {
        element.stable_key or element.name or element.selector.lstrip("#")
        for element in capture_observation(page, investigation_id, with_screenshot=False).elements
    }


def _locate_rule_context(
    page: Page,
    investigation_id: UUID,
    rule: BusinessRule,
    *,
    target_url: str,
    routes_seen: list[str],
    use_spa: bool,
) -> str | None:
    """Navigate until condition field is present; return SPA baseline route when applicable."""
    needed = rule.condition.field

    def _baseline() -> str | None:
        if use_spa and "#" in page.url:
            return "#" + page.url.split("#", 1)[1]
        return None

    if rule.condition.operator == "clicked" or needed in _page_field_keys(page, investigation_id):
        return _baseline()

    candidates: list[str] = []
    if use_spa:
        candidates.extend(["#/a", "#/b", "#/c", "#/form", "#/"])
        candidates.extend(routes_seen)
    else:
        candidates.extend(reversed([r for r in routes_seen if str(r).startswith("http")]))
        candidates.append(target_url)

    seen: set[str] = set()
    for route in candidates:
        if not route or route in seen:
            continue
        seen.add(route)
        try:
            if use_spa and (str(route).startswith("#") or "/#" in str(route)):
                hash_route = str(route)
                if "/#" in hash_route:
                    hash_route = "#" + hash_route.split("#", 1)[1]
                soft_return_to_route(page, hash_route)
            elif str(route).startswith("http"):
                goto_resilient(page, str(route))
                dismiss_consent_banners(page)
            else:
                continue
        except Exception:
            continue
        if needed in _page_field_keys(page, investigation_id):
            return _baseline()
    return _baseline()


def _set_field(page: Page, field: str, value: str) -> None:
    from browser.observer.settle import settle_after_action

    locator = page.locator(
        f'[data-testid="{field}"], #{field}, [name="{field}"], [aria-label="{field}"]'
    )
    if value == "__click__":
        locator.first.click()
        settle_after_action(page)
        return
    if locator.count() == 0:
        raise RuntimeError(f"Field not found: {field}")
    tag = locator.first.evaluate("(el) => el.tagName.toLowerCase()")
    if tag == "select":
        locator.first.select_option(value)
    elif tag == "button" or (tag == "input" and locator.first.get_attribute("type") in {"button", "submit"}):
        locator.first.click()
    else:
        locator.first.fill(value)
    settle_after_action(page)


def _transition(
    client: ApiClient,
    investigation_id: UUID,
    event: TransitionEvent,
    reason: str | None = None,
    auth_pause=None,
) -> None:
    client.transition(investigation_id, event, reason, auth_pause)


def _begin_exploration_if_needed(client: ApiClient, investigation_id: UUID) -> InvestigationStatus:
    investigation = client.get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTHENTICATED:
        _transition(client, investigation_id, TransitionEvent.BEGIN_EXPLORATION)
    elif investigation.status == InvestigationStatus.OBSERVING:
        _transition(client, investigation_id, TransitionEvent.BEGIN_EXPLORATION)
    return client.get_investigation(investigation_id).status


def _capture_observation_if_exploring(client: ApiClient, investigation_id: UUID) -> None:
    if client.get_investigation(investigation_id).status == InvestigationStatus.EXPLORING:
        _transition(client, investigation_id, TransitionEvent.CAPTURE_OBSERVATION)


def _start_verification_if_needed(client: ApiClient, investigation_id: UUID) -> None:
    status = client.get_investigation(investigation_id).status
    if status in {
        InvestigationStatus.GENERATING_RULE,
        InvestigationStatus.EXPLORING,
    }:
        _transition(client, investigation_id, TransitionEvent.START_VERIFICATION)


def _complete_verification_if_needed(client: ApiClient, investigation_id: UUID) -> None:
    if client.get_investigation(investigation_id).status == InvestigationStatus.VERIFYING:
        _transition(client, investigation_id, TransitionEvent.VERIFICATION_COMPLETE)


def _run_verification_phase(
    page: Page,
    client: ApiClient,
    investigation_id: UUID,
    *,
    candidate_rules: list[BusinessRule],
    controller: ExplorationController,
    target_url: str,
    use_spa: bool,
    network=None,
) -> tuple[list[BusinessRule], int]:
    verified_rules: list[BusinessRule] = []
    actions_taken = 0

    if use_spa:
        soft_return_to_route(page, "#/")
    else:
        goto_resilient(page, target_url)
        dismiss_consent_banners(page)

    for rule in candidate_rules:
        if rule.status.value in {"verified", "contradicted"}:
            verified_rules.append(rule)
            continue
        baseline = _locate_rule_context(
            page,
            investigation_id,
            rule,
            target_url=target_url,
            routes_seen=list(controller.state.routes_seen) + list(controller.state.pages_seen_urls),
            use_spa=use_spa,
        )
        _start_verification_if_needed(client, investigation_id)
        updated = verify_rule_on_page(
            page,
            client,
            investigation_id,
            rule,
            spa_mode=use_spa,
            baseline_route=baseline if use_spa else None,
            budget=controller.budget,
            network=network,
        )
        verified_rules.append(updated)
        actions_taken += 2
        _complete_verification_if_needed(client, investigation_id)
        print(
            f"[WebTwin] Verified rule {updated.name!r} → {updated.status.value} "
            f"(confidence={updated.confidence})"
        )
    return verified_rules, actions_taken


def _handle_auth(
    page: Page,
    context,
    client: ApiClient,
    investigation_id: UUID,
    session_manager: SessionManager,
    session_store: SessionStore,
) -> None:
    from webtwin_core.auth.form_schema import extract_auth_form_schema

    investigation = client.get_investigation(investigation_id)
    has_password = SessionManager.password_field_visible(page)
    has_otp = SessionManager.otp_field_visible(page)
    has_sso = SessionManager.sso_button_visible(page)
    pause_metadata = session_manager.detect_pause(page.url, has_password or has_sso, has_otp)
    if pause_metadata is not None:
        try:
            observation = capture_observation(page, investigation_id, with_screenshot=False)
            client.record_observation(observation)
            schema = extract_auth_form_schema(observation)
            if schema is not None:
                pause_metadata.form = schema
                client.upsert_auth_form(investigation_id, schema)
                print(
                    f"[WebTwin] Auth form detected ({schema.page_kind}): "
                    f"{len(schema.fields)} field(s) — fill from dashboard or Chrome"
                )
        except Exception as error:
            print(f"[WebTwin] Auth form capture skipped: {error}")
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
    elif investigation.status == InvestigationStatus.AUTH_REQUIRED:
        session_store.save(context, investigation_id)
        ref = str(session_store.path_for(investigation_id))
        client.upsert_session(
            investigation_id,
            auth_state=AuthState.AUTHENTICATED,
            storage_state_ref=ref,
        )
        _transition(client, investigation_id, TransitionEvent.AUTH_COMPLETED)
    elif investigation.status == InvestigationStatus.AUTH_CHECK:
        _transition(client, investigation_id, TransitionEvent.AUTH_OK)
        client.upsert_session(investigation_id, auth_state=AuthState.AUTHENTICATED)
    else:
        client.upsert_session(investigation_id, auth_state=AuthState.AUTHENTICATED)


def _fetch_rules(client: ApiClient, investigation_id: UUID) -> list[BusinessRule]:
    return [
        BusinessRule.model_validate(rule)
        for rule in httpx.get(f"{client.base_url}/investigations/{investigation_id}/rules").json()
    ]


def _hydrate_controller_from_checkpoint(
    client: ApiClient,
    investigation: Investigation,
    controller: ExplorationController,
    *,
    policy: str,
) -> str | None:
    """Restore lean crawl cursor; return last_url to open (or None)."""
    from webtwin_core.exploration.progress import (
        ExplorationProgress,
        apply_progress,
        progress_from_checkpoint,
        rebuild_frontier_from_links,
    )

    progress = progress_from_checkpoint(investigation.checkpoint)
    if progress is None:
        raw = client.get_exploration_progress(investigation.id)
        if raw:
            try:
                progress = ExplorationProgress.model_validate(raw)
            except Exception:
                progress = None
    if progress is None:
        return None

    apply_progress(controller.state, controller.budget, progress)
    links = client.list_discovered_links(investigation.id)
    origin = progress.last_url or investigation.target_url
    added = rebuild_frontier_from_links(controller.state, links, origin_url=origin)
    print(
        f"[WebTwin] Resumed crawl progress: pages={len(controller.state.pages_seen_urls)} "
        f"frontier={len(controller.state.frontier)} (+{added} from links) "
        f"actions={controller.state.actions_taken} last={progress.last_url}"
    )
    return progress.last_url


def _exploration_loop(
    page: Page,
    client: ApiClient,
    investigation_id: UUID,
    controller: ExplorationController,
    timeline: TimelineRecorder,
    network=None,
    progress_sync: ExplorationProgressSync | None = None,
) -> int:
    """Observe → plan → act → diff → rules until budget or coverage exhausted."""
    from urllib.parse import urlparse

    investigation = client.get_investigation(investigation_id)
    if investigation.status in _POST_EXPLORATION_STATUSES:
        return 0

    _begin_exploration_if_needed(client, investigation_id)
    _capture_observation_if_exploring(client, investigation_id)

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
                state_after_id=before_state.id,
            )
        )
    )
    if network is not None:
        route = before_observation.route
        network.set_context(
            route_path=route.path if route else urlparse(page.url).path,
            timeline_event_id=timeline.events[-1].id if timeline.events else None,
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

        settle = controller.apply_plan(page, plan)
        actions_taken += 1
        if plan.action.type.value in {"navigate", "route"}:
            dismiss_consent_banners(page)

        if client.get_investigation(investigation_id).status == InvestigationStatus.EXPLORING:
            _transition(client, investigation_id, TransitionEvent.CAPTURE_OBSERVATION)
        after_observation = capture_observation(page, investigation_id)
        controller.record_state_signature(after_observation)
        client.record_observation(after_observation)
        after_state = client.record_state(after_observation.to_application_state(sequence=sequence))

        event_type = TimelineEventType.SELECT
        if plan.action.type.value == "scroll":
            event_type = TimelineEventType.SCROLL
        elif settle.ok and plan.action.type.value == "route":
            event_type = TimelineEventType.ROUTE
        elif settle.ok and plan.action.type.value == "navigate":
            event_type = TimelineEventType.NAVIGATE
        action_href = None
        if settle.ok and plan.action.type.value in {"navigate", "route"}:
            action_href = plan.action.metadata.get("href") or plan.value
        timeline.record(
            client.record_event(
                TimelineEvent(
                    investigation_id=investigation_id,
                    type=event_type,
                    description=(
                        f"{plan.action.target}={plan.value} ({plan.reason})"
                        + (f" href={action_href}" if action_href else "")
                        + ("" if settle.ok else f" [failed: {settle.reason}]")
                    ),
                    state_before_id=before_state.id if settle.ok else None,
                    state_after_id=after_state.id if settle.ok else None,
                )
            )
        )
        if not settle.ok:
            timeline.record(
                client.record_event(
                    TimelineEvent(
                        investigation_id=investigation_id,
                        type=TimelineEventType.SETTLE,
                        description=f"settle ok={settle.ok} {settle.reason} ({settle.elapsed_ms:.0f}ms)",
                    )
                )
            )
            continue

        timeline.record(
            client.record_event(
                TimelineEvent(
                    investigation_id=investigation_id,
                    type=TimelineEventType.SETTLE,
                    description=f"settle ok={settle.ok} {settle.reason} ({settle.elapsed_ms:.0f}ms)",
                )
            )
        )
        diff = client.diff_states(investigation_id, before_state.id, after_state.id)
        controller.state.record_diff_result(len(diff.changes or []))

        if network is not None:
            route = after_observation.route
            network.set_context(
                route_path=route.path if route else urlparse(page.url).path,
                timeline_event_id=timeline.events[-1].id if timeline.events else None,
            )

        before_observation = after_observation
        before_state = after_state
        sequence += 1

        if progress_sync is not None:
            progress_sync.mark_dirty()
            force = plan.action.type.value in {"navigate", "route"}
            progress_sync.maybe_save(
                controller.state,
                controller.budget,
                last_url=page.url,
                force=force,
                reason="page" if force else "actions",
            )

    if progress_sync is not None:
        progress_sync.maybe_save(
            controller.state,
            controller.budget,
            last_url=page.url,
            force=True,
            reason="exploration_end",
        )

    if network is not None:
        nearest = timeline.events[-1].id if timeline.events else None
        for evidence in network.to_evidence(timeline_event_id=nearest):
            client.record_evidence(evidence)

    if client.get_investigation(investigation_id).status == InvestigationStatus.OBSERVING:
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
    spa_mode: bool | None = None,
) -> tuple[UUID, list[BusinessRule], list[BusinessRule], int, ExplorationMetrics]:
    from browser.observer.network import NetworkCollector
    from urllib.parse import urlparse
    from webtwin_core.spa import spa_mode_enabled

    client = ApiClient(api_base_url or os.environ.get("WEBTWIN_API_URL") or DEFAULT_API_URL)
    session_manager = SessionManager()
    session_store = SessionStore()
    timeline = TimelineRecorder()
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
        policy, url_prefix = _resolve_exploration_config(investigation, policy)
        resumable = _RESUMABLE_STATUSES
        if investigation.status == InvestigationStatus.CREATED:
            investigation = client.claim_investigation(investigation_id)
        elif investigation.status in resumable or investigation.status == InvestigationStatus.AUTH_REQUIRED:
            investigation = client.claim_investigation(investigation_id)
        resume_phase = investigation.status
        if investigation.status == InvestigationStatus.INITIALIZING:
            _transition(client, investigation.id, TransitionEvent.INIT_COMPLETE)
            resume_phase = client.get_investigation(investigation.id).status
    else:
        url_prefix = os.environ.get("WEBTWIN_URL_PREFIX")
        resume_phase = InvestigationStatus.CREATED
        use_spa = spa_mode if spa_mode is not None else (
            spa_mode_enabled(None)
            or "spa" in target_scope.lower()
            or os.environ.get("WEBTWIN_SPA_MODE", "").lower() in {"1", "true", "yes"}
        )
        investigation = client.create_investigation(
            Investigation(
                goal=f"Explore business logic in {target_name}",
                target_url=target_url,
                feature_scope=target_scope,
                application_version=os.environ.get("WEBTWIN_APP_VERSION", "synthetic-1"),
                environment=os.environ.get("WEBTWIN_ENVIRONMENT", "eval"),
                role_scope=os.environ.get("WEBTWIN_ROLE_SCOPE"),
                spa_mode=use_spa,
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

    use_spa = spa_mode if spa_mode is not None else spa_mode_enabled(investigation)
    resolved_budget = budget or budget_for_policy(policy)
    if budget is None and os.environ.get("WEBTWIN_MAX_ACTIONS"):
        resolved_budget = ExplorationBudget(
            max_actions=int(os.environ["WEBTWIN_MAX_ACTIONS"]),
            max_pages=resolved_budget.max_pages,
        )
    controller = ExplorationController(
        policy=policy,
        budget=resolved_budget,
        seed=seed,
        spa_mode=use_spa,
        goal=_investigation_goal(investigation),
        url_prefix=getattr(investigation, "url_prefix", None) or url_prefix,
    )

    resume_url: str | None = None
    should_hydrate = (
        investigation_id is not None
        and resume_phase not in {
            InvestigationStatus.CREATED,
            InvestigationStatus.INITIALIZING,
            InvestigationStatus.AUTH_CHECK,
            *_POST_EXPLORATION_STATUSES,
        }
    )
    if should_hydrate:
        investigation = client.get_investigation(investigation.id)
        resume_url = _hydrate_controller_from_checkpoint(
            client, investigation, controller, policy=policy
        )

    progress_sync = ExplorationProgressSync(
        client, investigation.id, policy=policy, every_actions=5
    )

    # Preserve saved auth/session when resuming mid-investigation.
    if resume_phase in {
        InvestigationStatus.CREATED,
        InvestigationStatus.INITIALIZING,
        InvestigationStatus.AUTH_CHECK,
    } and investigation.status != InvestigationStatus.AUTH_REQUIRED:
        client.upsert_session(investigation.id, auth_state=AuthState.UNKNOWN)

    skip_exploration = resume_phase in _POST_EXPLORATION_STATUSES
    entry_url = resume_url or getattr(investigation, "start_url", None) or target_url

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = session_store.new_context(browser, investigation.id)
        page = context.new_page()
        network = NetworkCollector(investigation.id)
        network.attach(page)

        try:
            goto_resilient(page, entry_url)
            dismiss_consent_banners(page)
            _handle_auth(page, context, client, investigation.id, session_manager, session_store)
            if skip_exploration:
                actions_taken = 0
            else:
                actions_taken = _exploration_loop(
                    page,
                    client,
                    investigation.id,
                    controller,
                    timeline,
                    network=network,
                    progress_sync=progress_sync,
                )

            candidate_rules = _fetch_rules(client, investigation.id)
            controller.state.register_rules(candidate_rules)
            controller.known_rules = candidate_rules

            verified_rules, verify_actions = _run_verification_phase(
                page,
                client,
                investigation.id,
                candidate_rules=candidate_rules,
                controller=controller,
                target_url=target_url,
                use_spa=use_spa,
                network=network,
            )
            actions_taken += verify_actions

            session_store.save(context, investigation.id)
            _transition(client, investigation.id, TransitionEvent.COMPLETE)
        except Exception as error:
            try:
                progress_sync.maybe_save(
                    controller.state,
                    controller.budget,
                    last_url=page.url if not page.is_closed() else entry_url,
                    force=True,
                    reason="failure",
                )
            except Exception:
                pass
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

    soft_total = controller.state.soft_nav_successes + controller.state.soft_nav_failures
    soft_rate = (
        controller.state.soft_nav_successes / soft_total if soft_total else (1.0 if use_spa else None)
    )
    metrics_run = EvaluationRun.from_exploration_metrics(investigation.id, exploration_metrics)
    metrics_run.settle_timeouts = controller.state.settle_timeouts
    metrics_run.soft_nav_success_rate = soft_rate
    metrics_run.routes_seen = len(controller.state.routes_seen)
    client.record_metrics(investigation.id, metrics_run)
    return investigation.id, candidate_rules, verified_rules, actions_taken, exploration_metrics


def run_discovery_and_verification(
    target: Path,
    discovery_actions: list[dict[str, str]],
    api_base_url: str | None = None,
    headless: bool = True,
    *,
    spa_mode: bool | None = None,
) -> tuple[UUID, list[BusinessRule], list[BusinessRule], int]:
    """Fixed-action discovery path (M1/M2 benchmark compatibility)."""
    from browser.observer.network import NetworkCollector
    from webtwin_core.spa import spa_mode_enabled

    client = ApiClient(api_base_url or os.environ.get("WEBTWIN_API_URL") or DEFAULT_API_URL)
    session_manager = SessionManager()
    session_store = SessionStore()
    timeline = TimelineRecorder()
    actions_taken = 0
    candidate_rules: list[BusinessRule] = []
    verified_rules: list[BusinessRule] = []

    use_spa = spa_mode if spa_mode is not None else (
        "spa" in target.parent.name.lower()
        or spa_mode_enabled(None)
        or os.environ.get("WEBTWIN_SPA_MODE", "").lower() in {"1", "true", "yes"}
    )

    investigation = client.create_investigation(
        Investigation(
            goal=f"Discover business logic in {target.name}",
            target_url=target.as_uri(),
            feature_scope=target.parent.name,
            application_version=os.environ.get("WEBTWIN_APP_VERSION", "synthetic-1"),
            environment=os.environ.get("WEBTWIN_ENVIRONMENT", "eval"),
            role_scope=os.environ.get("WEBTWIN_ROLE_SCOPE"),
            spa_mode=use_spa,
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
            goto_resilient(page, target.as_uri())
            dismiss_consent_banners(page)
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
            network.set_context(
                route_path=before_observation.route.path if before_observation.route else "/",
                timeline_event_id=timeline.events[-1].id if timeline.events else None,
            )

            _transition(client, investigation.id, TransitionEvent.BEGIN_EXPLORATION)
            for action in discovery_actions:
                if action.get("type") == "route":
                    href = action.get("href") or action["value"]
                    link = page.locator(
                        f'a[href="{href}"], [data-testid="{action["field"]}"]'
                    )
                    if link.count() > 0:
                        link.first.click()
                    else:
                        page.evaluate("(h) => { location.hash = h }", href if href.startswith("#") else f"#{href}")
                    from browser.observer.settle import settle_after_action

                    settle_after_action(page, expect_url_contains=href if href.startswith("#") else href)
                else:
                    _set_field(page, action["field"], action["value"])
                actions_taken += 1
                timeline.record(
                    client.record_event(
                        TimelineEvent(
                            investigation_id=investigation.id,
                            type=TimelineEventType.SELECT,
                            description=f"Set {action.get('field')}={action.get('value')}",
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
                updated = verify_rule_on_page(
                    page, client, investigation.id, rule, spa_mode=use_spa,
                    budget=ExplorationBudget(max_actions=100),
                    network=network,
                )
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
