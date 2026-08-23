import json
import os
from pathlib import Path

from webtwin_core.evaluation.metrics import ExpectedRule, compute_metrics
from webtwin_core.exploration import ExplorationBudget
from webtwin_core.models.rule_status import RuleStatus

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "browser"))

from browser.investigation.runner import (  # noqa: E402
    run_discovery_and_verification,
    run_exploration_and_verification,
)

BENCHMARK_ROOT = ROOT / "tests/evaluation/synthetic_ats"
LEVELS = {
    "level_01": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_01.json",
        "actions": [{"field": "condition", "value": "no"}],
    },
    "level_02": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_02/multi_condition.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_02.json",
        "actions": [{"field": "employment_type", "value": "contract"}],
    },
    "level_03": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_03/validation_rules.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_03.json",
        "actions": [
            {"field": "start_date", "value": "2024-01-10"},
            {"field": "end_date", "value": "2024-01-05"},
            {"field": "submit", "value": "__click__"},
        ],
    },
    "level_04": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_04/step2.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_04.json",
        "actions": [{"field": "salary_band", "value": "exec"}],
    },
    "level_05": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_05/network_validation.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_05.json",
        "actions": [
            {"field": "employee_id", "value": "BAD"},
            {"field": "validate", "value": "__click__"},
        ],
    },
    "level_06": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_06/hidden_logic.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_06.json",
        "actions": [
            {"field": "tenure_years", "value": "5"},
            {"field": "rating", "value": "exceeds"},
        ],
    },
    "level_07": {
        "mode": "dual_role",
        "expected": BENCHMARK_ROOT / "expected_rules/level_07.json",
        "roles": [
            {
                "role_scope": "admin",
                "fixture": BENCHMARK_ROOT / "fixtures/level_07/admin.html",
                "actions": [{"field": "role_mode", "value": "admin"}],
            },
            {
                "role_scope": "recruiter",
                "fixture": BENCHMARK_ROOT / "fixtures/level_07/recruiter.html",
                "actions": [{"field": "role_mode", "value": "recruiter"}],
            },
        ],
    },
    "level_08": {
        "mode": "discovery",
        "fixture": BENCHMARK_ROOT / "fixtures/level_08/auth_interrupt.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_08.json",
        "actions": [{"field": "unlock_sensitive", "value": "__click__"}],
    },
    "level_09": {
        "mode": "exploration",
        "fixture": BENCHMARK_ROOT / "fixtures/level_09/budget_efficiency.html",
        "expected": BENCHMARK_ROOT / "expected_rules/level_09.json",
        "policy": "information_gain",
        "max_actions": 6,
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
    candidates = []
    verified_rules = []
    actions = 0

    if config.get("mode") == "dual_role":
        for role in config["roles"]:
            os.environ["WEBTWIN_ROLE_SCOPE"] = role["role_scope"]
            _id, role_cands, role_verified, role_actions = run_discovery_and_verification(
                role["fixture"],
                discovery_actions=role["actions"],
                api_base_url=api_url,
                headless=headless,
            )
            candidates.extend(role_cands)
            verified_rules.extend(role_verified)
            actions += role_actions
        os.environ.pop("WEBTWIN_ROLE_SCOPE", None)
    elif config.get("mode") == "exploration":
        _investigation_id, candidates, verified_rules, actions, _metrics = run_exploration_and_verification(
            config["fixture"],
            policy=config.get("policy", "information_gain"),
            api_base_url=api_url,
            headless=headless,
            budget=ExplorationBudget(max_actions=int(config.get("max_actions", 12))),
        )
    else:
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
    default_levels = ",".join(LEVELS.keys())
    levels = os.environ.get("WEBTWIN_BENCHMARK_LEVELS", default_levels).split(",")

    for level in levels:
        run_level(level.strip(), api_url, headless)


if __name__ == "__main__":
    main()
