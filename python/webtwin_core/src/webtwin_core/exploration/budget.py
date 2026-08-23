from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.exploration.actions import ActionInventory, ExploratoryAction, SafetyClass
from webtwin_core.exploration.state import ExplorationState


class ExplorationBudget(BaseModel):
    max_actions: int = 100
    max_duration_seconds: int = 600
    max_pages: int = 20
    max_experiments: int = 50
    max_scrolls: int = 10
    actions_used: int = 0
    pages_seen: int = 0
    experiments_used: int = 0
    scrolls_used: int = 0
    started_at_monotonic: float | None = None

    def remaining_actions(self) -> int:
        return max(0, self.max_actions - self.actions_used)

    def exhausted(self, elapsed_seconds: float = 0.0) -> bool:
        if self.actions_used >= self.max_actions:
            return True
        if self.experiments_used >= self.max_experiments:
            return True
        if self.pages_seen >= self.max_pages:
            return True
        if self.scrolls_used >= self.max_scrolls:
            # scrolls alone don't exhaust — only when combined with action budget
            pass
        if self.max_duration_seconds > 0 and elapsed_seconds >= self.max_duration_seconds:
            return True
        return False

    def consume_action(self) -> None:
        self.actions_used += 1

    def consume_experiment(self) -> None:
        self.experiments_used += 1

    def can_run_experiment(self) -> bool:
        return self.experiments_used < self.max_experiments

    def consume_page(self) -> None:
        self.pages_seen += 1

    def consume_scroll(self) -> None:
        self.scrolls_used += 1


def budget_for_policy(policy: str) -> ExplorationBudget:
    # max_duration_seconds=0 → no wall-clock limit (action/page caps still apply).
    if policy == "site_map":
        return ExplorationBudget(max_pages=80, max_actions=300, max_duration_seconds=0)
    if policy == "information_gain":
        return ExplorationBudget(max_pages=20, max_actions=100, max_duration_seconds=0)
    return ExplorationBudget(max_pages=20, max_actions=100, max_duration_seconds=0)
