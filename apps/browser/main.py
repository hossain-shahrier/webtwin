import os
import time
from pathlib import Path
from uuid import UUID

from webtwin_core.defaults import DEFAULT_API_URL
from webtwin_core.exploration import ExplorationBudget
from webtwin_core.models import InvestigationStatus

from browser.client.api import ApiClient
from browser.investigation.runner import (
    run_discovery_and_verification,
    run_exploration_and_verification,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = ROOT / "tests/evaluation/synthetic_ats"


def _run_one(
    *,
    target: str | Path,
    api_url: str,
    headless: bool,
    mode: str,
    investigation_id: UUID | None = None,
) -> None:
    if mode == "discovery" and investigation_id is None:
        investigation_id, _candidates, verified_rules, _actions = run_discovery_and_verification(
            Path(target) if not str(target).startswith("http") else Path(
                os.environ.get(
                    "WEBTWIN_FIXTURE",
                    str(BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html"),
                )
            ),
            discovery_actions=[{"field": "condition", "value": "no"}],
            api_base_url=api_url,
            headless=headless,
        )
    else:
        policy = os.environ.get("WEBTWIN_POLICY", "information_gain")
        # Prefer policy encoded in feature_scope from dashboard create
        investigation_id, _candidates, verified_rules, _actions, metrics = (
            run_exploration_and_verification(
                target,
                policy=policy,
                api_base_url=api_url,
                headless=headless,
                budget=ExplorationBudget(max_actions=int(os.environ.get("WEBTWIN_MAX_ACTIONS", "12"))),
                investigation_id=investigation_id,
            )
        )
        print(
            f"Exploration: coverage={metrics.exploration_coverage} "
            f"rules/action={metrics.rules_per_action} pages={metrics.pages_seen}"
        )

    print(f"Investigation: {investigation_id}")
    for rule in verified_rules:
        print(f"{rule.status}: {rule.name} (confidence={rule.confidence})")


def run_worker(api_url: str, headless: bool) -> None:
    """Poll API for dashboard-created investigations and execute them."""
    client = ApiClient(api_url)
    poll_seconds = float(os.environ.get("WEBTWIN_WORKER_POLL_SECONDS", "3"))
    print(f"Worker polling {api_url}/investigations/pending every {poll_seconds}s")
    while True:
        pending = client.list_pending()
        if not pending:
            time.sleep(poll_seconds)
            continue
        # Prefer brand-new jobs over orphaned auth pauses.
        pending.sort(key=lambda job: 0 if job.status == InvestigationStatus.CREATED else 1)
        job = pending[0]
        policy = job.feature_scope or os.environ.get("WEBTWIN_POLICY", "information_gain")
        os.environ["WEBTWIN_POLICY"] = policy
        if job.spa_mode or (job.environment or "").lower().find("spa") >= 0:
            os.environ["WEBTWIN_SPA_MODE"] = "1"
        print(f"Claiming {job.id} → {job.target_url} (policy={policy} spa={job.spa_mode})")
        try:
            _run_one(
                target=job.target_url,
                api_url=api_url,
                headless=headless,
                mode="exploration",
                investigation_id=job.id,
            )
        except Exception as error:
            print(f"[WebTwin] Job {job.id} failed: {error}")
            continue


def main() -> None:
    api_url = os.environ.get("WEBTWIN_API_URL", DEFAULT_API_URL)
    headless = os.environ.get("WEBTWIN_HEADLESS", "true").lower() == "true"
    mode = os.environ.get("WEBTWIN_INVESTIGATE_MODE", "exploration")

    if os.environ.get("WEBTWIN_WORKER", "").lower() in {"1", "true", "yes"}:
        run_worker(api_url, headless)
        return

    investigation_id_env = os.environ.get("WEBTWIN_INVESTIGATION_ID")
    investigation_id = UUID(investigation_id_env) if investigation_id_env else None
    target_url = os.environ.get("WEBTWIN_TARGET_URL")
    if investigation_id is not None:
        target: str | Path = ApiClient(api_url).get_investigation(investigation_id).target_url
    elif target_url:
        target = target_url
    else:
        target = Path(
            os.environ.get(
                "WEBTWIN_FIXTURE",
                str(BENCHMARK_ROOT / "fixtures/level_01/conditional_visibility.html"),
            )
        )

    _run_one(
        target=target,
        api_url=api_url,
        headless=headless,
        mode=mode,
        investigation_id=investigation_id,
    )


if __name__ == "__main__":
    main()
