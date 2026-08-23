"""Pluggable LLM planner — emits structured JSON only; never upgrades RuleStatus."""

from __future__ import annotations

import json
import os
from typing import Any

from webtwin_core.exploration.actions import ActionInventory, ActionType
from webtwin_core.exploration.policy import PlannedAction, choose_max_information_gain
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.models.rules import BusinessRule
from webtwin_core.planning.protocol import ProposedExperiment


class LLMPlanner:
    """
    Uses WEBTWIN_LLM_PROVIDER when set (openai|anthropic|heuristic).
    Default heuristic mimics an LLM proposal over the inventory without network calls.
    """

    def __init__(self, provider: str | None = None) -> None:
        self.provider = (provider or os.environ.get("WEBTWIN_LLM_PROVIDER") or "heuristic").lower()
        self.name = f"llm:{self.provider}"

    def choose_next_action(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        *,
        known_rules: list[BusinessRule] | None = None,
    ) -> PlannedAction | None:
        proposal = self._propose_action_payload(state, inventory, known_rules or [])
        if proposal is None:
            return choose_max_information_gain(state, inventory)

        target = proposal.get("target")
        value = proposal.get("value")
        reason = proposal.get("reason") or "llm proposal"
        if not target:
            return choose_max_information_gain(state, inventory)

        for action in inventory.actions:
            if action.target == target or action.key == target:
                return PlannedAction(
                    action=action,
                    value=value if value is not None else (action.values[0] if action.values else None),
                    reason=f"llm:{reason}",
                    expected_information_gain=float(proposal.get("expected_information_gain", 1.5)),
                )
        return choose_max_information_gain(state, inventory)

    def propose_experiments(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        known_rules: list[BusinessRule],
    ) -> list[ProposedExperiment]:
        payload = self._propose_experiments_payload(state, inventory, known_rules)
        experiments: list[ProposedExperiment] = []
        for item in payload:
            experiments.append(
                ProposedExperiment(
                    description=str(item.get("description", "llm experiment")),
                    set_fields=dict(item.get("set_fields") or {}),
                    expected_effect_field=item.get("expected_effect_field"),
                    expected_visible=item.get("expected_visible"),
                    confidence=float(item.get("confidence", 0.45)),
                    source=self.name,
                )
            )
        return experiments

    def _propose_action_payload(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        known_rules: list[BusinessRule],
    ) -> dict[str, Any] | None:
        if self.provider in {"openai", "anthropic"}:
            remote = self._call_remote_json(
                system=(
                    "You are a web investigation planner. Reply with JSON only: "
                    '{"target": str, "value": str|null, "reason": str, "expected_information_gain": number}. '
                    "Never invent page facts; choose from the provided inventory."
                ),
                user=json.dumps(
                    {
                        "inventory": [
                            {
                                "target": a.target,
                                "type": a.type.value,
                                "values": a.values,
                                "safety": a.safety.value,
                            }
                            for a in inventory.actions
                        ],
                        "tested": list(state.tested_action_keys),
                        "known_rules": [r.name for r in known_rules[:20]],
                    }
                ),
            )
            if remote:
                return remote

        # Heuristic "LLM" — prefer selects that unlock new visibility; bias away from tested keys
        plan = choose_max_information_gain(state, inventory)
        if plan is not None:
            return {
                "target": plan.action.target,
                "value": plan.value,
                "reason": plan.reason,
                "expected_information_gain": plan.expected_information_gain + 0.25,
            }

        for action in inventory.actions:
            if action.type == ActionType.NAVIGATE and action.key not in state.tested_action_keys:
                return {
                    "target": action.target,
                    "value": action.values[0] if action.values else None,
                    "reason": "unexplored page",
                    "expected_information_gain": 2.0,
                }
        return None

    def _propose_experiments_payload(
        self,
        state: ExplorationState,
        inventory: ActionInventory,
        known_rules: list[BusinessRule],
    ) -> list[dict[str, Any]]:
        action = self._propose_action_payload(state, inventory, known_rules)
        if not action or not action.get("target"):
            return []
        return [
            {
                "description": action.get("reason", "llm experiment"),
                "set_fields": {action["target"]: action.get("value") or ""},
                "expected_effect_field": None,
                "expected_visible": True,
                "confidence": 0.45,
            }
        ]

    def _call_remote_json(self, system: str, user: str) -> dict[str, Any] | None:
        """Optional provider hook — structured JSON only; falls back when unavailable."""
        api_key = os.environ.get("WEBTWIN_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key or self.provider == "heuristic":
            return None
        try:
            import httpx
        except ImportError:
            return None

        try:
            if self.provider == "openai":
                response = httpx.post(
                    os.environ.get("WEBTWIN_LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"),
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": os.environ.get("WEBTWIN_LLM_MODEL", "gpt-4o-mini"),
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return json.loads(content)
            if self.provider == "anthropic":
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": os.environ.get("WEBTWIN_LLM_MODEL", "claude-3-5-haiku-latest"),
                        "max_tokens": 512,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                content = response.json()["content"][0]["text"]
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    return json.loads(content[start : end + 1])
        except Exception:
            return None
        return None
