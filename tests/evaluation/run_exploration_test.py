"""Smoke test for deterministic active exploration (no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "browser"))

from browser.exploration.controller import ExplorationController  # noqa: E402
from browser.exploration.action_space import inventory_from_page  # noqa: E402
from webtwin_core.exploration import ExplorationBudget, SafetyClass, classify_action_safety  # noqa: E402

FIXTURE = ROOT / "tests/evaluation/synthetic_ats/fixtures/exploration/employment_options.html"


def main() -> None:
    if not FIXTURE.exists():
        raise SystemExit("exploration fixture missing")

    investigation_id = uuid4()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE.as_uri())

        inventory = inventory_from_page(page, investigation_id)
        assert any(action.target == "employment_type" for action in inventory.actions)
        delete = next(action for action in inventory.actions if "delete" in (action.label or "").lower())
        assert classify_action_safety(delete) == SafetyClass.DESTRUCTIVE

        controller = ExplorationController(
            policy="information_gain",
            budget=ExplorationBudget(max_actions=5),
        )
        plans = controller.run_until_exhausted(page, investigation_id)
        values = [plan.value for plan in plans if plan.value]
        assert "contract" in values or "temporary" in values
        assert "Delete Account" not in [plan.action.label for plan in plans]
        print(f"Exploration smoke passed: {len(plans)} actions -> {values}")
        browser.close()


if __name__ == "__main__":
    main()
