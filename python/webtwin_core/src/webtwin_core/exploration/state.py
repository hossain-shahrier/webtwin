from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction
from webtwin_core.models.rules import BusinessRule

if TYPE_CHECKING:
    from webtwin_core.reference_system.site_graph import DiscoveredLink, LinkType


def route_key(url_or_href: str) -> str:
    """Stable route identity including hash fragments for SPAs."""
    if not url_or_href:
        return ""
    if url_or_href.startswith("#"):
        return url_or_href
    parsed = urlparse(url_or_href)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"
    return path


class TargetCoverage(BaseModel):
    target: str
    possible_values: list[str] = Field(default_factory=list)
    tested_values: list[str] = Field(default_factory=list)

    @property
    def untested_values(self) -> list[str]:
        tested = set(self.tested_values)
        return [value for value in self.possible_values if value not in tested]

    @property
    def fully_tested(self) -> bool:
        return not self.untested_values and bool(self.possible_values)


class FrontierLink(BaseModel):
    from_screen_id: str
    to_screen_id: str
    href: str


class ExplorationState(BaseModel):
    """What the investigator knows about explored vs unknown behavior."""

    url: str | None = None
    coverage: dict[str, TargetCoverage] = Field(default_factory=dict)
    known_rule_ids: list[str] = Field(default_factory=list)
    tested_action_keys: list[str] = Field(default_factory=list)
    states_seen: list[str] = Field(default_factory=list)
    pages_seen_urls: list[str] = Field(default_factory=list)
    routes_seen: list[str] = Field(default_factory=list)
    settle_timeouts: int = 0
    soft_nav_successes: int = 0
    soft_nav_failures: int = 0
    scrolls_used: int = 0
    actions_taken: int = 0
    consecutive_no_diff: int = 0
    visible_field_targets: list[str] = Field(default_factory=list)
    explored_field_targets: list[str] = Field(default_factory=list)
    frontier: list[str] = Field(default_factory=list)
    link_targets: dict[str, FrontierLink] = Field(default_factory=dict)
    url_prefix: str | None = None

    def sync_visible_fields(self, inventory: ActionInventory) -> None:
        for action in inventory.actions:
            if action.type not in {ActionType.SELECT, ActionType.INPUT}:
                continue
            if action.target not in self.visible_field_targets:
                self.visible_field_targets.append(action.target)

    def mark_field_explored(self, target: str) -> None:
        if target not in self.explored_field_targets:
            self.explored_field_targets.append(target)

    def record_diff_result(self, change_count: int) -> None:
        if change_count > 0:
            self.consecutive_no_diff = 0
        else:
            self.consecutive_no_diff += 1

    def unexplored_form_fields(self) -> list[str]:
        explored = set(self.explored_field_targets)
        return [target for target in self.visible_field_targets if target not in explored]

    def sync_inventory(self, inventory: ActionInventory) -> None:
        self.sync_visible_fields(inventory)
        self.url = inventory.url
        if inventory.url and inventory.url not in self.pages_seen_urls:
            self.pages_seen_urls.append(inventory.url)
        if inventory.url:
            key = route_key(inventory.url)
            if key and key not in self.routes_seen:
                self.routes_seen.append(key)
        for action in inventory.actions:
            if action.type != ActionType.SELECT:
                continue
            existing = self.coverage.get(action.target)
            if existing is None:
                self.coverage[action.target] = TargetCoverage(
                    target=action.target,
                    possible_values=list(action.values),
                )
            else:
                merged = list(dict.fromkeys([*existing.possible_values, *action.values]))
                existing.possible_values = merged

    def mark_tested(self, action: ExploratoryAction, value: str | None = None) -> None:
        self.actions_taken += 1
        if action.key not in self.tested_action_keys:
            self.tested_action_keys.append(action.key)
        if action.type == ActionType.NAVIGATE and value and value not in self.pages_seen_urls:
            self.pages_seen_urls.append(value)
        if action.type == ActionType.ROUTE and value:
            key = route_key(value)
            if key and key not in self.routes_seen:
                self.routes_seen.append(key)
            self.soft_nav_successes += 1
        if action.type == ActionType.SCROLL:
            self.scrolls_used += 1
        if action.type == ActionType.SELECT and value is not None:
            coverage = self.coverage.setdefault(
                action.target,
                TargetCoverage(target=action.target, possible_values=list(action.values)),
            )
            if value not in coverage.tested_values:
                coverage.tested_values.append(value)
            if value not in coverage.possible_values:
                coverage.possible_values.append(value)
        if action.type in {ActionType.SELECT, ActionType.INPUT}:
            self.mark_field_explored(action.target)

    def register_rules(self, rules: list[BusinessRule]) -> None:
        for rule in rules:
            rule_id = str(rule.id)
            if rule_id not in self.known_rule_ids:
                self.known_rule_ids.append(rule_id)

    def unexplored_select_actions(self, inventory: ActionInventory) -> list[tuple[ExploratoryAction, str]]:
        candidates: list[tuple[ExploratoryAction, str]] = []
        for action in inventory.actions:
            if action.type != ActionType.SELECT:
                continue
            coverage = self.coverage.get(action.target)
            if coverage is None:
                for value in action.values:
                    candidates.append((action, value))
                continue
            for value in coverage.untested_values:
                candidates.append((action, value))
        return candidates

    def unexplored_input_actions(self, inventory: ActionInventory) -> list[tuple[ExploratoryAction, str]]:
        """Probe text inputs once with a safe non-destructive value."""
        candidates: list[tuple[ExploratoryAction, str]] = []
        for action in inventory.actions:
            if action.type != ActionType.INPUT:
                continue
            if action.key in self.tested_action_keys:
                continue
            input_type = (action.metadata.get("input_type") or "text").lower()
            if input_type in {"email"}:
                value = "probe@example.com"
            elif input_type in {"number", "tel"}:
                value = "1"
            else:
                value = "engineering"
            # Skip global site-search chrome — probing it rarely yields business rules
            if action.target.lower() in {"q", "query", "search", "s", "grouped-demo"}:
                continue
            candidates.append((action, value))
        return candidates

    def unexplored_navigate_actions(self, inventory: ActionInventory) -> list[tuple[ExploratoryAction, str]]:
        candidates: list[tuple[ExploratoryAction, str]] = []
        for action in inventory.actions:
            if action.type not in {ActionType.NAVIGATE, ActionType.ROUTE} or not action.values:
                continue
            value = action.values[0]
            key = route_key(value)
            seen = value in self.pages_seen_urls or (key in self.routes_seen if key else False)
            if not seen and action.key not in self.tested_action_keys:
                candidates.append((action, value))
        return candidates

    def unexplored_route_actions(self, inventory: ActionInventory) -> list[tuple[ExploratoryAction, str]]:
        return [
            (action, value)
            for action, value in self.unexplored_navigate_actions(inventory)
            if action.type == ActionType.ROUTE
        ]

    def exploration_coverage(self) -> float:
        if not self.coverage:
            return 0.0
        tested = sum(len(target.tested_values) for target in self.coverage.values())
        possible = sum(len(target.possible_values) for target in self.coverage.values())
        return round(tested / possible, 3) if possible else 0.0

    def state_coverage(self) -> int:
        return len(self.states_seen)

    def _screen_visited(self, screen_id: str) -> bool:
        from webtwin_core.reference_system.site_graph import (
            normalize_screen_id,
            route_pattern_key,
        )

        normalized = normalize_screen_id(screen_id)
        for url in self.pages_seen_urls:
            if normalize_screen_id(route_key(url)) == normalized:
                return True
        if any(normalize_screen_id(route) == normalized for route in self.routes_seen):
            return True
        pattern = route_pattern_key(normalized)
        if pattern is None:
            return False
        for url in self.pages_seen_urls:
            if route_pattern_key(route_key(url)) == pattern:
                return True
        return any(route_pattern_key(route) == pattern for route in self.routes_seen)

    def _matches_url_prefix(self, screen_id: str) -> bool:
        if not self.url_prefix:
            return True
        prefix = self.url_prefix if self.url_prefix.startswith("/") else f"/{self.url_prefix}"
        from webtwin_core.reference_system.site_graph import normalize_screen_id

        normalized = normalize_screen_id(screen_id)
        normalized_prefix = normalize_screen_id(prefix)
        return normalized == normalized_prefix or normalized.startswith(f"{normalized_prefix}/")

    def remove_from_frontier(self, screen_id: str) -> None:
        from webtwin_core.reference_system.site_graph import normalize_screen_id

        normalized = normalize_screen_id(screen_id)
        self.frontier = [
            item for item in self.frontier if normalize_screen_id(item) != normalized
        ]
        self.link_targets.pop(normalized, None)

    def rotate_frontier(self) -> None:
        if len(self.frontier) > 1:
            self.frontier.append(self.frontier.pop(0))

    def enqueue_frontier_from_links(
        self,
        links: list["DiscoveredLink"],
        *,
        origin_url: str,
    ) -> None:
        from webtwin_core.reference_system.site_graph import LinkType, navigate_priority, normalize_screen_id

        candidates: list[tuple[str, int]] = []
        for link in links:
            if link.link_type == LinkType.EXTERNAL or not link.to_screen_id or link.visited:
                continue
            if not self._matches_url_prefix(link.to_screen_id):
                continue
            if self._screen_visited(link.to_screen_id):
                continue
            if link.to_screen_id in self.frontier:
                continue
            normalized_to = normalize_screen_id(link.to_screen_id)
            existing = self.link_targets.get(normalized_to)
            candidate = FrontierLink(
                from_screen_id=link.from_screen_id,
                to_screen_id=link.to_screen_id,
                href=link.href,
            )
            if existing is None or navigate_priority(origin_url, link.href) < navigate_priority(
                origin_url, existing.href
            ):
                self.link_targets[normalized_to] = candidate
            candidates.append((link.to_screen_id, navigate_priority(origin_url, link.href)))
        candidates.sort(key=lambda item: item[1])
        for screen_id, _ in candidates:
            if screen_id not in self.frontier:
                self.frontier.append(screen_id)

    def pop_frontier(self) -> str | None:
        if not self.frontier:
            return None
        return self.frontier.pop(0)
