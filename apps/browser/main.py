import os
from pathlib import Path

from webtwin_core.defaults import DEFAULT_API_URL

from browser.investigation.runner import run_discovery_and_verification

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = ROOT / "tests/evaluation/synthetic_ats"


def main() -> None:
    fixture = BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html"
    api_url = os.environ.get("WEBTWIN_API_URL", DEFAULT_API_URL)
    headless = os.environ.get("WEBTWIN_HEADLESS", "true").lower() == "true"

    investigation_id, _candidates, verified_rules, _actions = run_discovery_and_verification(
        fixture,
        discovery_actions=[{"field": "condition", "value": "no"}],
        api_base_url=api_url,
        headless=headless,
    )

    print(f"Investigation: {investigation_id}")
    for rule in verified_rules:
        print(f"{rule.status}: {rule.name} (confidence={rule.confidence})")


if __name__ == "__main__":
    main()
