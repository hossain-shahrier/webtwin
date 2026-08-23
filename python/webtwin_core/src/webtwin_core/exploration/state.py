from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field

from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction
from webtwin_core.models.rules import BusinessRule


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

    def sync_inventory(self, inventory: ActionInventory) -> None:
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
