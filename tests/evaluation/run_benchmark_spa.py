"""SPA synthetic benchmark S1–S7 — soft nav, settle, deep observe gate."""

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

from browser.investigation.runner import (  # noqa: E402
    run_discovery_and_verification,
    run_exploration_and_verification,
)
from browser.observer.settle import settle_after_action  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SPA_ROOT = ROOT / "tests/evaluation/synthetic_spa"
LEVELS = {
    "s1": {
        "mode": "soft_nav",
        "fixture": SPA_ROOT / "fixtures/s1_soft_route/index.html",
        "expected": SPA_ROOT / "expected_rules/s1.json",
    },
    "s2": {
        "mode": "discovery",
        "fixture": SPA_ROOT / "fixtures/s2_async_validation/index.html",
        "expected": SPA_ROOT / "expected_rules/s2.json",
        "actions": [
            {"field": "employee_id", "value": "BAD"},
            {"field": "validate", "value": "__click__"},
        ],
    },
    "s3": {
        "mode": "discovery",
        "fixture": SPA_ROOT / "fixtures/s3_portal_dialog/index.html",
        "expected": SPA_ROOT / "expected_rules/s3.json",
        "actions": [
            {"field": "open_dialog", "value": "__click__"},
            {"field": "bonus_code", "value": "exec"},
        ],
    },
    "s4": {
        "mode": "discovery",
        "fixture": SPA_ROOT / "fixtures/s4_virtualized_list/index.html",
        "expected": SPA_ROOT / "expected_rules/s4.json",
        "actions": [
            {"field": "open_row", "value": "__click__"},
            {"field": "remote_ok", "value": "no"},
        ],
    },
    "s5": {
        "mode": "discovery",
        "fixture": SPA_ROOT / "fixtures/s5_shadow_dom/index.html",
        "expected": SPA_ROOT / "expected_rules/s5.json",
        "actions": [{"field": "secret_code", "value": "secret"}],
    },
    "s6": {
        "mode": "discovery",
        "fixture": SPA_ROOT / "fixtures/s6_auth_wall/index.html",
        "expected": SPA_ROOT / "expected_rules/s6.json",
        "actions": [{"field": "unlock_sensitive", "value": "__click__"}],
    },
    "s7": {
        "mode": "exploration",
        "fixture": SPA_ROOT / "fixtures/s7_budget/index.html",
        "expected": SPA_ROOT / "expected_rules/s7.json",
        "policy": "information_gain",
        "max_actions": 8,
    },
}


def _to_expected_rules(path: Path) -> list[ExpectedRule]:
    return [ExpectedRule.model_validate(item) for item in json.loads(path.read_text())]


def _to_expected_from_discovered(rules) -> list[ExpectedRule]:
    return [
        ExpectedRule(id=str(rule.id), condition=rule.condition, effect=rule.effect)
        for rule in rules
    ]


def run_soft_nav_s1(fixture: Path) -> dict:
    """Assert draft survives soft route round-trip (SPA state retained)."""
    soft_ok = 0
    soft_fail = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=os.environ.get("WEBTWIN_HEADLESS", "true") != "false")
        page = browser.new_page()
        page.goto(fixture.as_uri())
        settle_after_action(page)
        page.locator('[data-testid="notes"]').fill("kept-draft")
        page.locator('[data-testid="nav-about"]').click()
        settle = settle_after_action(page, expect_url_contains="#/about")
        if settle.ok:
            soft_ok += 1
        else:
            soft_fail += 1
        page.locator('[data-testid="nav-form"]').click()
        settle2 = settle_after_action(page, expect_url_contains="#/form")
        if settle2.ok:
            soft_ok += 1
        else:
            soft_fail += 1
        value = page.locator('[data-testid="notes"]').input_value()
        browser.close()
    rate = soft_ok / (soft_ok + soft_fail) if (soft_ok + soft_fail) else 0.0
    retained = value == "kept-draft"
    return {
        "draft_retained": retained,
        "soft_nav_success_rate": rate,
        "soft_nav_successes": soft_ok,
        "soft_nav_failures": soft_fail,
    }


def run_level(level: str, api_url: str, headless: bool) -> dict:
    os.environ["WEBTWIN_SPA_MODE"] = "1"
    os.environ.setdefault("WEBTWIN_SETTLE_TIMEOUT_MS", "5000")
    config = LEVELS[level]
    expected = _to_expected_rules(config["expected"])
    result: dict = {"level": level}

    if config["mode"] == "soft_nav":
        soft = run_soft_nav_s1(config["fixture"])
        result.update(soft)
        result["discovery_f1"] = 1.0 if soft["draft_retained"] else 0.0
        result["verification_accuracy"] = 1.0 if soft["draft_retained"] else 0.0
        result["actions_taken"] = 2
        print(
            f"{level}: draft_retained={soft['draft_retained']} "
            f"soft_nav_success_rate={soft['soft_nav_success_rate']:.3f}"
        )
        if not soft["draft_retained"]:
            raise SystemExit(f"S1 failed: draft not retained after soft nav")
        if soft["soft_nav_success_rate"] < 0.95:
            raise SystemExit(f"S1 soft_nav_success_rate {soft['soft_nav_success_rate']} < 0.95")
        return result

    if config["mode"] == "exploration":
        _id, candidates, verified_rules, actions, _metrics = run_exploration_and_verification(
            config["fixture"],
            policy=config.get("policy", "information_gain"),
            api_base_url=api_url,
            headless=headless,
            budget=ExplorationBudget(max_actions=int(config.get("max_actions", 8))),
            spa_mode=True,
        )
    else:
        _id, candidates, verified_rules, actions = run_discovery_and_verification(
            config["fixture"],
            discovery_actions=config["actions"],
            api_base_url=api_url,
            headless=headless,
            spa_mode=True,
        )

    discovered = _to_expected_from_discovered(candidates)
    verified = [
        ExpectedRule(id=str(r.id), condition=r.condition, effect=r.effect)
        for r in verified_rules
        if r.status == RuleStatus.VERIFIED
    ]
    contradicted = sum(1 for r in verified_rules if r.status == RuleStatus.CONTRADICTED)
    metrics = compute_metrics(
        level=level,
        expected=expected,
        discovered=discovered,
        verified=verified,
        contradicted=contradicted,
        actions_taken=actions,
    )
    result["discovery_f1"] = metrics.discovery.f1_score
    result["verification_accuracy"] = metrics.verification.verification_accuracy
    result["actions_taken"] = actions
    print(
        f"{level}: discovery_f1={metrics.discovery.f1_score} "
        f"verification_accuracy={metrics.verification.verification_accuracy} "
        f"actions={actions}"
    )
    return result


def main() -> None:
    api_url = os.environ.get("WEBTWIN_API_URL", "http://127.0.0.1:8060")
    headless = os.environ.get("WEBTWIN_HEADLESS", "true").lower() != "false"
    levels = sys.argv[1:] or list(LEVELS.keys())
    results = []
    soft_rates = []
    for level in levels:
        if level not in LEVELS:
            raise SystemExit(f"Unknown SPA level: {level}")
        row = run_level(level, api_url, headless)
        results.append(row)
        if "soft_nav_success_rate" in row:
            soft_rates.append(row["soft_nav_success_rate"])

    if soft_rates and (sum(soft_rates) / len(soft_rates)) < 0.95:
        raise SystemExit("soft_nav_success_rate gate failed (< 0.95)")
    print(json.dumps({"levels": results, "ok": True}, indent=2))


if __name__ == "__main__":
    main()
