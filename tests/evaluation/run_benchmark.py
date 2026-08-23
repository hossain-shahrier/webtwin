import json
import os
from pathlib import Path

from webtwin_core.evaluation.metrics import ExpectedRule, compute_metrics
from webtwin_core.models.rule_status import RuleStatus

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "browser"))

from browser.investigation.runner import run_discovery_and_verification  # noqa: E402

BENCHMARK_ROOT = ROOT / "tests/evaluation/synthetic_ats"
LEVELS = {
    "level_01": {
        "fixture": BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_01.json",
        "actions": [{"field": "condition", "value": "no"}],
    },
    "level_02": {
        "fixture": BENCHMARK_ROOT / "fixtures/level_02/multi_condition.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_02.json",
        "actions": [{"field": "employment_type", "value": "contract"}],
    },
}


def _to_expected_rules(path: Path) -> list[ExpectedRule]:
    return [ExpectedRule.model_validate(item) for item in json.loads(path.read_text())]


def _to_expected_from_discovered(rules) -> list[ExpectedRule]:
    return [
        ExpectedRule(
            id=str(rule.id),
            condition=rule.condition,
            effect=rule.effect,
        )
        for rule in rules
    ]


def run_level(level: str, api_url: str, headless: bool) -> None:
    config = LEVELS[level]
    expected = _to_expected_rules(config["expected"])

    _investigation_id, candidates, verified_rules, actions = run_discovery_and_verification(
        config["fixture"],
        discovery_actions=config["actions"],
        api_base_url=api_url,
        headless=headless,
    )

    discovered = _to_expected_from_discovered(candidates)
    verified = _to_expected_from_discovered(
        [rule for rule in verified_rules if rule.status == RuleStatus.VERIFIED]
    )
    contradicted = sum(1 for rule in verified_rules if rule.status == RuleStatus.CONTRADICTED)

    metrics = compute_metrics(level, expected, discovered, verified, contradicted, actions)
    print(f"\n=== {level} ===")
    print(
        f"discovery: precision={metrics.discovery.precision} "
        f"recall={metrics.discovery.recall} f1={metrics.discovery.f1_score}"
    )
    print(
        f"verification: accuracy={metrics.verification.verification_accuracy} "
        f"candidates={metrics.verification.candidate_rules} "
        f"verified={metrics.verification.verified_rules}"
    )
    print(f"actions={metrics.actions_taken} rules/action={metrics.rules_per_action}")


def main() -> None:
    from webtwin_core.defaults import DEFAULT_API_URL

    api_url = os.environ.get("WEBTWIN_API_URL", DEFAULT_API_URL)
    headless = os.environ.get("WEBTWIN_HEADLESS", "true").lower() == "true"
    levels = os.environ.get("WEBTWIN_BENCHMARK_LEVELS", "level_01,level_02").split(",")

    for level in levels:
        run_level(level.strip(), api_url, headless)


if __name__ == "__main__":
    main()
