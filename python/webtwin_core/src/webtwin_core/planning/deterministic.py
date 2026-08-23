from __future__ import annotations

from webtwin_core.exploration.actions import ActionInventory
from webtwin_core.exploration.policy import (
    PlannedAction,
    PolicyName,
    choose_next_action,
)
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.models.rules import BusinessRule
from webtwin_core.planning.protocol import ProposedExperiment


class DeterministicPlanner:
    """Wraps existing exploration policies — no LLM."""

    def __init__(self, policy: PolicyName | str = "information_gain") -> None:
        self.policy = policy
        self.name = f"deterministic:{policy}"

    def choose_next_action(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        *,
        known_rules: list[BusinessRule] | None = None,
    ) -> PlannedAction | None:
        _ = known_rules
        return choose_next_action(self.policy, state, inventory)

    def propose_experiments(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        known_rules: list[BusinessRule],
    ) -> list[ProposedExperiment]:
        plan = self.choose_next_action(state, inventory, known_rules=known_rules)
        if plan is None or plan.value is None:
            return []
        return [
            ProposedExperiment(
                description=plan.reason,
                set_fields={plan.action.target: plan.value},
                expected_effect_field=None,
                confidence=min(0.7, 0.3 + plan.expected_information_gain / 10),
                source=self.name,
            )
        ]
