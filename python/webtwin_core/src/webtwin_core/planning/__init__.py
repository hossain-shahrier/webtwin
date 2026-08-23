"""Investigation planners — AI may propose; only verified experiments change RuleStatus."""

from __future__ import annotations

from webtwin_core.exploration.policy import PolicyName
from webtwin_core.planning.protocol import Planner, ProposedExperiment


def resolve_planner(policy: PolicyName | str) -> Planner:
    from webtwin_core.planning.deterministic import DeterministicPlanner
    from webtwin_core.planning.llm import LLMPlanner

    if policy in {"llm", "ai"}:
        return LLMPlanner()
    return DeterministicPlanner(policy=policy)


__all__ = [
    "Planner",
    "ProposedExperiment",
    "resolve_planner",
]
