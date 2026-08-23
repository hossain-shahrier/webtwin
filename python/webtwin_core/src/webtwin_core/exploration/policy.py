from __future__ import annotations

import random
from pydantic import BaseModel

from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction
from webtwin_core.exploration.safety import filter_automatable
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.models.rules import BusinessRule

PolicyName = str  # "first_unexplored" | "information_gain" | "site_map" | "random"


class PlannedAction(BaseModel):
    action: ExploratoryAction
    value: str | None = None
    reason: str
    expected_information_gain: float = 0.0
    frontier_target: str | None = None


def information_gain(state: ExplorationState, action: ExploratoryAction, value: str | None) -> float:
    """Deterministic heuristic: prefer unexplored select values with many siblings still unknown."""
    goal_bonus = 1.5 if action.metadata.get("goal_relevant") == "True" else 0.0
    entity_bonus = 0.4 if action.metadata.get("entity") else 0.0
    if action.type != ActionType.SELECT or value is None:
        base = 0.1 if action.key not in state.tested_action_keys else 0.0
        return base + goal_bonus + entity_bonus

    coverage = state.coverage.get(action.target)
    if coverage is None:
        return float(max(len(action.values), 1)) + goal_bonus + entity_bonus
    if value in coverage.tested_values:
        return 0.0
    untested = len(coverage.untested_values)
    return float(untested) + goal_bonus + entity_bonus


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
    known_rules: list[BusinessRule] | None = None,
) -> PlannedAction | None:
    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    prioritized = _prioritize_form_actions(state, inventory, known_rules)
    if prioritized:
        action, value = prioritized[0]
        if action.type in {ActionType.NAVIGATE, ActionType.ROUTE} and value is None:
            value = action.values[0] if action.values else None
        return PlannedAction(
            action=action,
            value=value,
            reason=f"form-first explore {action.target}" + (f"={value}" if value else ""),
            expected_information_gain=information_gain(state, action, value),
        )
    # Prefer fields on the current route, then unexplored soft routes
    candidates = state.unexplored_select_actions(inventory)
    if candidates:
        action, value = candidates[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"first unexplored value for {action.target}",
            expected_information_gain=information_gain(state, action, value),
        )
    inputs = state.unexplored_input_actions(inventory)
    if inputs:
        action, value = inputs[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"probe input {action.target}",
            expected_information_gain=0.8,
        )
    routes = state.unexplored_route_actions(inventory)
    if routes:
        action, value = routes[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"first unexplored route {action.target}",
            expected_information_gain=2.5,
        )
    nav = state.unexplored_navigate_actions(inventory)
    if nav:
        action, value = nav[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"first unexplored page {action.target}",
            expected_information_gain=1.0,
        )
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


def _prioritize_form_actions(
    state: ExplorationState,
    inventory: ActionInventory,
    known_rules: list[BusinessRule] | None = None,
) -> list[tuple[ExploratoryAction, str | None]]:
    """Form-first ordering: unverified rule fields, entity/goal fields, then rest."""
    rule_fields: set[str] = set()
    for rule in known_rules or []:
        if rule.status.value in {"verified", "contradicted"}:
            continue
        rule_fields.add(rule.condition.field)
        rule_fields.add(rule.effect.field)

    def score(action: ExploratoryAction, value: str | None) -> float:
        blob = f"{action.target} {action.label or ''}".lower()
        s = information_gain(state, action, value)
        if action.target in rule_fields:
            s += 3.0
        if action.metadata.get("goal_relevant") == "True":
            s += 2.0
        if action.metadata.get("entity"):
            s += 1.0
        if action.type == ActionType.SELECT:
            s += 0.5
        if state.consecutive_no_diff >= 3 and action.type in {ActionType.NAVIGATE, ActionType.ROUTE}:
            s += 1.5
        elif state.consecutive_no_diff < 3 and action.type in {ActionType.NAVIGATE, ActionType.ROUTE}:
            s -= 2.0
        _ = blob
        return s

    candidates: list[tuple[ExploratoryAction, str | None, float]] = []
    for action, value in state.unexplored_select_actions(inventory):
        candidates.append((action, value, score(action, value)))
    for action, value in state.unexplored_input_actions(inventory):
        candidates.append((action, value, score(action, value)))
    for action, value in state.unexplored_route_actions(inventory):
        candidates.append((action, value, score(action, value)))
    for action, value in state.unexplored_navigate_actions(inventory):
        candidates.append((action, value, score(action, value)))
    candidates.sort(key=lambda item: item[2], reverse=True)
    return [(action, value) for action, value, _ in candidates]


def choose_max_information_gain(
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
    known_rules: list[BusinessRule] | None = None,
) -> PlannedAction | None:
    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    prioritized = _prioritize_form_actions(state, inventory, known_rules)
    if prioritized:
        action, value = prioritized[0]
        if action.type in {ActionType.NAVIGATE, ActionType.ROUTE} and value is None:
            value = action.values[0] if action.values else None
        return PlannedAction(
            action=action,
            value=value,
            reason=f"form-first explore {action.target}" + (f"={value}" if value else ""),
            expected_information_gain=information_gain(state, action, value),
        )
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
    nav = state.unexplored_navigate_actions(inventory)
    if nav:
        action, value = nav[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"information_gain nav {action.target}",
            expected_information_gain=1.0,
        )
    routes = state.unexplored_route_actions(inventory)
    if routes:
        action, value = routes[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"information_gain route {action.target}",
            expected_information_gain=1.5,
        )
    return None


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


def _screen_id_for_action(base_url: str, href: str) -> str:
    from webtwin_core.reference_system.site_graph import _screen_id_from_href

    return _screen_id_from_href(base_url, href) or href


def choose_site_map_action(
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
    known_rules: list[BusinessRule] | None = None,
) -> PlannedAction | None:
    """Deep BFS: frontier pages first, form-sweep on current page when frontier is empty."""
    from webtwin_core.reference_system.site_graph import navigate_priority, normalize_screen_id

    from webtwin_core.exploration.state import route_key

    inventory = _automatable_inventory(inventory, allow_caution=allow_caution)
    nav_candidates = state.unexplored_navigate_actions(inventory)

    matched_index: int | None = None
    matched: tuple[ExploratoryAction, str] | None = None
    for index, target_id in enumerate(state.frontier):
        normalized_target = normalize_screen_id(target_id)
        best_priority = 10_000
        candidate: tuple[ExploratoryAction, str] | None = None
        for action, value in nav_candidates:
            screen_id = normalize_screen_id(_screen_id_for_action(inventory.url, value))
            if screen_id != normalized_target:
                continue
            priority = navigate_priority(inventory.url, value)
            if priority < best_priority:
                best_priority = priority
                candidate = (action, value)
        if candidate:
            matched = candidate
            matched_index = index
            break

    if matched and matched_index is not None:
        action, value = matched
        target_id = normalize_screen_id(state.frontier[matched_index])
        return PlannedAction(
            action=action,
            value=value,
            reason=f"site_map frontier → {action.target}",
            expected_information_gain=2.0,
            frontier_target=target_id,
        )

    if state.frontier:
        from urllib.parse import urljoin

        current = normalize_screen_id(route_key(inventory.url))
        target_id = normalize_screen_id(state.frontier[0])
        link = state.link_targets.get(target_id)
        if link and link.from_screen_id:
            from_screen = normalize_screen_id(link.from_screen_id)
            if from_screen != current:
                back_href = link.from_screen_id
                back_url = urljoin(inventory.url, back_href)
                for action, value in nav_candidates:
                    screen_id = normalize_screen_id(_screen_id_for_action(inventory.url, value))
                    if screen_id == from_screen:
                        return PlannedAction(
                            action=action,
                            value=value,
                            reason=f"site_map backtrack → {from_screen}",
                            expected_information_gain=1.5,
                            frontier_target=target_id,
                        )
                for action, value in nav_candidates:
                    if action.type == ActionType.NAVIGATE:
                        return PlannedAction(
                            action=action,
                            value=back_url,
                            reason=f"site_map backtrack goto {from_screen}",
                            expected_information_gain=1.5,
                            frontier_target=target_id,
                        )
                for action in inventory.actions:
                    if action.type == ActionType.NAVIGATE:
                        return PlannedAction(
                            action=action,
                            value=back_url,
                            reason=f"site_map backtrack goto {from_screen}",
                            expected_information_gain=1.5,
                            frontier_target=target_id,
                        )
        state.rotate_frontier()

    prioritized = _prioritize_form_actions(state, inventory, known_rules)
    if prioritized:
        action, value = prioritized[0]
        if action.type in {ActionType.NAVIGATE, ActionType.ROUTE} and value is None:
            value = action.values[0] if action.values else None
        return PlannedAction(
            action=action,
            value=value,
            reason=f"site_map form-sweep {action.target}" + (f"={value}" if value else ""),
            expected_information_gain=information_gain(state, action, value),
        )
    if nav_candidates:
        action, value = nav_candidates[0]
        return PlannedAction(
            action=action,
            value=value,
            reason=f"site_map fallback nav {action.target}",
            expected_information_gain=1.0,
        )
    return None


def choose_next_action(
    policy: PolicyName,
    state: ExplorationState,
    inventory: ActionInventory,
    *,
    allow_caution: bool = False,
    rng: random.Random | None = None,
    known_rules: list[BusinessRule] | None = None,
) -> PlannedAction | None:
    if policy == "site_map":
        return choose_site_map_action(
            state, inventory, allow_caution=allow_caution, known_rules=known_rules
        )
    if policy == "information_gain":
        return choose_max_information_gain(
            state, inventory, allow_caution=allow_caution, known_rules=known_rules
        )
    if policy == "random":
        return choose_random_unexplored(state, inventory, allow_caution=allow_caution, rng=rng)
    return choose_first_unexplored(
        state, inventory, allow_caution=allow_caution, known_rules=known_rules
    )

