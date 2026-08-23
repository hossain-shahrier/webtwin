from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from webtwin_core.exploration.actions import ActionInventory
from webtwin_core.exploration.policy import PlannedAction
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.models.rules import BusinessRule


class ProposedExperiment(BaseModel):
    """Structured hypothesis from a planner — never applied without verification."""

    description: str
    set_fields: dict[str, str] = Field(default_factory=dict)
    expected_effect_field: str | None = None
    expected_visible: bool | None = None
    confidence: float = 0.4
    source: str = "deterministic"


class Planner(Protocol):
    name: str

    def choose_next_action(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        *,
        known_rules: list[BusinessRule] | None = None,
    ) -> PlannedAction | None: ...

    def propose_experiments(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        known_rules: list[BusinessRule],
    ) -> list[ProposedExperiment]: ...
