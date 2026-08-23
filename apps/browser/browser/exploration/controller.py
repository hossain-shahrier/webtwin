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
from browser.observer.snapshot import capture_observation


def execute_planned_action(page: Page, plan: PlannedAction) -> None:
    locator = page.locator(plan.action.selector)
    if plan.action.type.value == "select" and plan.value is not None:
        locator.select_option(plan.value)
    elif plan.action.type.value == "input" and plan.value is not None:
        locator.fill(plan.value)
    elif plan.action.type.value == "navigate" and plan.value is not None:
        page.goto(plan.value)
    elif plan.action.type.value == "click":
        locator.click()
    page.wait_for_timeout(150)


class ExplorationController:
    def __init__(
        self,
        *,
        policy: PolicyName = "first_unexplored",
        budget: ExplorationBudget | None = None,
        seed: int | None = None,
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

    @property
    def blocked_unsafe_actions(self) -> int:
        return len(self._blocked_action_ids)

    def observe(self, page: Page, investigation_id: UUID) -> Observation:
        return capture_observation(page, investigation_id)

    def plan_from_observation(self, observation: Observation) -> PlannedAction | None:
        inventory = inventory_from_observation(observation)
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

    def apply_plan(self, page: Page, plan: PlannedAction) -> None:
        safety = classify_action_safety(plan.action)
        if safety != SafetyClass.SAFE:
            self.safety_violations += 1
            raise RuntimeError(f"Refusing to execute {safety.value} action: {plan.action.target}")
        execute_planned_action(page, plan)
        self.state.mark_tested(plan.action, plan.value)
        self.budget.consume_action()
        self.plans.append(plan)

    def record_state_signature(self, observation: Observation) -> None:
        signature = "|".join(
            f"{element.name or element.selector}:{element.value}:{element.visible}"
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
