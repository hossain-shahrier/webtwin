from __future__ import annotations

import random
from pydantic import BaseModel

from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction
from webtwin_core.exploration.safety import filter_automatable
from webtwin_core.exploration.state import ExplorationState

PolicyName = str  # "first_unexplored" | "information_gain" | "random"


class PlannedAction(BaseModel):
    action: ExploratoryAction
    value: str | None = None
    reason: str
    expected_information_gain: float = 0.0


def information_gain(state: ExplorationState, action: ExploratoryAction, value: str | None) -> float:
    """Deterministic heuristic: prefer unexplored select values with many siblings still unknown."""
    if action.type != ActionType.SELECT or value is None:
        return 0.1 if action.key not in state.tested_action_keys else 0.0

    coverage = state.coverage.get(action.target)
    if coverage is None:
        return float(max(len(action.values), 1))
    if value in coverage.tested_values:
        return 0.0
    untested = len(coverage.untested_values)
    return float(untested)


def _automatable_inventory(
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
) -> ActionInventory:
    return ActionInventory(
        url=inventory.url,
        actions=filter_automatable(inventory.actions, allow_caution=allow_caution),
    )


def choose_first_unexplored(
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
) -> PlannedAction | None:
    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    # SPA bias: cover unexplored soft routes before fields on current route
    routes = state.unexplored_route_actions(inventory)
    if routes:
        action, value = routes[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"first unexplored route {action.target}",
            expected_information_gain=2.5,
        )
    candidates = state.unexplored_select_actions(inventory)
    if not candidates:
        nav = state.unexplored_navigate_actions(inventory)
        if not nav:
            # Optional scroll when fields may be offscreen
            for action in inventory.actions:
                if action.type == ActionType.SCROLL and action.key not in state.tested_action_keys:
                    if state.scrolls_used >= 3:
                        break
                    return PlannedAction(
                        action=action,
                        value="down",
                        reason="scroll to reveal offscreen fields",
                        expected_information_gain=0.5,
                    )
            return None
        action, value = nav[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"first unexplored page {action.target}",
            expected_information_gain=1.0,
        )
    action, value = candidates[0]
    return PlannedAction(
        action=action,
        value=value,
        reason=f"first unexplored value for {action.target}",
        expected_information_gain=information_gain(state, action, value),
    )


def choose_max_information_gain(
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
) -> PlannedAction | None:
    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    routes = state.unexplored_route_actions(inventory)
    if routes:
        action, value = routes[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"unexplored route {action.target}",
            expected_information_gain=3.0,
        )
    candidates = state.unexplored_select_actions(inventory)
    if not candidates:
        nav = state.unexplored_navigate_actions(inventory)
        if not nav:
            for action in inventory.actions:
                if action.type == ActionType.SCROLL and action.key not in state.tested_action_keys:
                    if state.scrolls_used >= 3:
                        break
                    return PlannedAction(
                        action=action,
                        value="down",
                        reason="scroll for information gain",
                        expected_information_gain=0.5,
                    )
            return None
        action, value = nav[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"unexplored page {action.target}",
            expected_information_gain=2.0,
        )

    best_action, best_value = candidates[0]
    best_score = information_gain(state, best_action, best_value)
    for action, value in candidates[1:]:
        score = information_gain(state, action, value)
        if score > best_score:
            best_action, best_value, best_score = action, value, score

    return PlannedAction(
        action=best_action,
        value=best_value,
        reason=f"max information gain for {best_action.target}={best_value}",
        expected_information_gain=best_score,
    )


def choose_random_unexplored(
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
    rng: random.Random | None = None,
) -> PlannedAction | None:
    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    candidates = state.unexplored_select_actions(inventory)
    if not candidates:
        candidates = state.unexplored_navigate_actions(inventory)
    if not candidates:
        return None
    randomizer = rng or random.Random()
    action, value = randomizer.choice(candidates)
    return PlannedAction(
        action=action,
        value=value,
        reason=f"random unexplored value for {action.target}",
        expected_information_gain=information_gain(state, action, value),
    )


def choose_next_action(
    policy: PolicyName,
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
    rng: random.Random | None = None,
) -> PlannedAction | None:
    if policy == "information_gain":
        return choose_max_information_gain(state, inventory, allow_caution=allow_caution)
    if policy == "random":
        return choose_random_unexplored(state, inventory, allow_caution=allow_caution, rng=rng)
    return choose_first_unexplored(state, inventory, allow_caution=allow_caution)

