from __future__ import annotations

import random
import time
from uuid import UUID

from playwright.sync_api import Page
from webtwin_core.exploration import (
    ExplorationBudget,
    ExplorationState,
    PlannedAction,
    PolicyName,
    SafetyClass,
    apply_safety,
    classify_action_safety,
    filter_automatable,
)
from webtwin_core.models import Observation
from webtwin_core.planning import resolve_planner

from browser.exploration.action_space import inventory_from_observation
from browser.observer.settle import SettleResult, settle_after_action
from browser.observer.snapshot import capture_observation


def execute_planned_action(page: Page, plan: PlannedAction) -> SettleResult:
    action = plan.action
    locator = page.locator(action.selector)
    expect_url = None

    if action.type.value == "select" and plan.value is not None:
        locator.first.select_option(plan.value)
    elif action.type.value == "input" and plan.value is not None:
        locator.first.fill(plan.value)
    elif action.type.value == "navigate" and plan.value is not None:
        page.goto(plan.value)
    elif action.type.value == "route":
        # Soft nav: click in-app control (History / hash) — never hard goto
        if locator.count() == 0 and plan.value and str(plan.value).startswith("#"):
            page.evaluate("(hash) => { location.hash = hash }", plan.value)
        else:
            locator.first.click()
        href = action.metadata.get("href") or plan.value
        if href:
            expect_url = href.lstrip("#") if href.startswith("#") else href
            # For hash routes, wait for hash fragment
            if href.startswith("#"):
                expect_url = href
    elif action.type.value == "scroll":
        direction = (plan.value or "down").lower()
        delta = 600 if direction == "down" else -600
        page.mouse.wheel(0, delta)
        page.evaluate(
            """(dy) => {
              const el = document.scrollingElement || document.documentElement;
              el.scrollBy(0, dy);
              document.querySelectorAll('[data-scroll-container]').forEach((node) => {
                node.scrollBy(0, dy);
              });
            }""",
            delta,
        )
    elif action.type.value == "click":
        locator.first.click()

    return settle_after_action(page, expect_url_contains=expect_url)


class ExplorationController:
    def __init__(
        self,
        *,
        policy: PolicyName = "first_unexplored",
        budget: ExplorationBudget | None = None,
        seed: int | None = None,
        spa_mode: bool = False,
    ) -> None:
        self.policy = policy
        self.budget = budget or ExplorationBudget(max_actions=20)
        self.state = ExplorationState()
        self._started = time.monotonic()
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self.plans: list[PlannedAction] = []
        self.safety_violations = 0
        self._blocked_action_ids: set[str] = set()
        self.planner = resolve_planner(policy)
        self.known_rules: list = []
        self.spa_mode = spa_mode
        self.last_settle: SettleResult | None = None

    @property
    def blocked_unsafe_actions(self) -> int:
        return len(self._blocked_action_ids)

    def observe(self, page: Page, investigation_id: UUID) -> Observation:
        return capture_observation(page, investigation_id)

    def plan_from_observation(self, observation: Observation) -> PlannedAction | None:
        inventory = inventory_from_observation(observation, spa_mode=self.spa_mode)
        self.state.sync_inventory(inventory)
        self._count_blocked_unsafe(inventory)
        return self.planner.choose_next_action(
            self.state,
            inventory,
            known_rules=self.known_rules,
        )

    def plan_next(self, page: Page, investigation_id: UUID) -> PlannedAction | None:
        elapsed = time.monotonic() - self._started
        if self.budget.exhausted(elapsed):
            return None
        observation = self.observe(page, investigation_id)
        return self.plan_from_observation(observation)

    def apply_plan(self, page: Page, plan: PlannedAction) -> SettleResult:
        safety = classify_action_safety(plan.action)
        if safety != SafetyClass.SAFE:
            self.safety_violations += 1
            raise RuntimeError(f"Refusing to execute {safety.value} action: {plan.action.target}")
        settle = execute_planned_action(page, plan)
        self.last_settle = settle
        if not settle.ok:
            self.state.settle_timeouts += 1
            if plan.action.type.value == "route":
                self.state.soft_nav_failures += 1
            raise RuntimeError(f"Settle failed: {settle.reason}")
        self.state.mark_tested(plan.action, plan.value)
        self.budget.consume_action()
        if plan.action.type.value == "scroll":
            self.budget.consume_scroll()
        self.plans.append(plan)
        return settle

    def record_state_signature(self, observation: Observation) -> None:
        signature = "|".join(
            f"{element.stable_key or element.name or element.selector}:{element.value}:{element.visible}"
            for element in sorted(observation.elements, key=lambda item: item.selector)
        )
        if signature and signature not in self.state.states_seen:
            self.state.states_seen.append(signature)

    def step(self, page: Page, investigation_id: UUID) -> PlannedAction | None:
        plan = self.plan_next(page, investigation_id)
        if plan is None:
            return None
        self.apply_plan(page, plan)
        return plan

    def run_until_exhausted(
        self,
        page: Page,
        investigation_id: UUID,
        max_steps: int | None = None,
    ) -> list[PlannedAction]:
        limit = max_steps if max_steps is not None else self.budget.remaining_actions()
        executed: list[PlannedAction] = []
        for _ in range(limit):
            plan = self.step(page, investigation_id)
            if plan is None:
                break
            executed.append(plan)
        return executed

    def _count_blocked_unsafe(self, inventory) -> None:
        classified = [apply_safety(action) for action in inventory.actions]
        automatable_ids = {action.id for action in filter_automatable(inventory.actions)}
        for action in classified:
            if action.id not in automatable_ids and action.safety != SafetyClass.SAFE:
                self._blocked_action_ids.add(action.key)
