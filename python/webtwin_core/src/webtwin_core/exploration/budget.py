from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.exploration.actions import ActionInventory, ExploratoryAction, SafetyClass
from webtwin_core.exploration.state import ExplorationState


class ExplorationBudget(BaseModel):
    max_actions: int = 100
    max_duration_seconds: int = 600
    max_pages: int = 20
    max_experiments: int = 50
    actions_used: int = 0
    pages_seen: int = 0
    experiments_used: int = 0
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
        if elapsed_seconds >= self.max_duration_seconds:
            return True
        return False

    def consume_action(self) -> None:
        self.actions_used += 1
