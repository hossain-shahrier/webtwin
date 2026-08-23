"""Compare exploration policies on synthetic fixtures (includes llm ablation)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from webtwin_core.evaluation.metrics import ExpectedRule, compute_metrics
from webtwin_core.exploration import ExplorationBudget
from webtwin_core.models.rule_status import RuleStatus

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "browser"))

from browser.investigation.runner import run_exploration_and_verification  # noqa: E402

BENCHMARK_ROOT = ROOT / "tests/evaluation/synthetic_ats"
POLICIES = ("random", "first_unexplored", "information_gain", "llm")
LEVELS = {
    "exploration": {
        "fixture": BENCHMARK_ROOT / "fixtures/exploration/employment_options.html",
        "expected": None,
    },
    "level_01": {
        "fixture": BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_01.json",
    },
    "level_09": {
        "fixture": BENCHMARK_ROOT / "fixtures/level_09/budget_efficiency.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_09.json",
    },
}


def _to_expected_rules(path: Path | None) -> list[ExpectedRule]:
    if path is None or not path.exists():
        return []
    return [ExpectedRule.model_validate(item) for item in json.loads(path.read_text())]


def _to_expected_from_discovered(rules) -> list[ExpectedRule]:
    return [
        ExpectedRule(id=str(rule.id), condition=rule.condition, effect=rule.effect)
        for rule in rules
    ]


def run_policy(level: str, policy: str, api_url: str, headless: bool, seed: int) -> None:
    config = LEVELS[level]
    expected = _to_expected_rules(config.get("expected"))

    _investigation_id, candidates, verified_rules, actions, exploration = run_exploration_and_verification(
        config["fixture"],
        policy=policy,
        api_base_url=api_url,
        headless=headless,
        budget=ExplorationBudget(max_actions=int(os.environ.get("WEBTWIN_MAX_ACTIONS", "10"))),
        seed=seed,
    )

    discovered = _to_expected_from_discovered(candidates)
    verified = _to_expected_from_discovered(
        [rule for rule in verified_rules if rule.status == RuleStatus.VERIFIED]
    )
    contradicted = sum(1 for rule in verified_rules if rule.status == RuleStatus.CONTRADICTED)
    metrics = compute_metrics(level, expected, discovered, verified, contradicted, actions, exploration)

    print(f"\n=== {level} / {policy} ===")
    print(
        f"discovery: precision={metrics.discovery.precision} "
        f"recall={metrics.discovery.recall} f1={metrics.discovery.f1_score}"
    )
    print(
        f"verification: accuracy={metrics.verification.verification_accuracy} "
        f"candidates={metrics.verification.candidate_rules} "
        f"verified={metrics.verification.verified_rules}"
    )
    if metrics.exploration:
        print(
            f"exploration: coverage={metrics.exploration.exploration_coverage} "
            f"states={metrics.exploration.state_coverage} "
            f"actions={metrics.exploration.actions_taken} "
            f"rules/action={metrics.exploration.rules_per_action} "
            f"safety_violations={metrics.exploration.safety_violations} "
            f"blocked_unsafe={metrics.exploration.blocked_unsafe_actions}"
        )


def main() -> None:
    from webtwin_core.defaults import DEFAULT_API_URL

    api_url = os.environ.get("WEBTWIN_API_URL", DEFAULT_API_URL)
    headless = os.environ.get("WEBTWIN_HEADLESS", "true").lower() == "true"
    seed = int(os.environ.get("WEBTWIN_EXPLORATION_SEED", "42"))
    level = os.environ.get("WEBTWIN_EXPLORATION_LEVEL", "exploration")
    policies = os.environ.get("WEBTWIN_EXPLORATION_POLICIES", ",".join(POLICIES)).split(",")

    for policy in policies:
        run_policy(level.strip(), policy.strip(), api_url, headless, seed)


if __name__ == "__main__":
    main()
