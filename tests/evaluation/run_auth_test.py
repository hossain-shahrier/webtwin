"""Run auth lifecycle integration test (requires API on port 8060)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import httpx
from webtwin_core.defaults import DEFAULT_API_URL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "browser"))

from browser.investigation.runner import run_discovery_and_verification  # noqa: E402

AUTH_FIXTURE = ROOT / "tests/evaluation/synthetic_ats/fixtures/auth/login_required.html"
API_URL = os.environ.get("WEBTWIN_API_URL", DEFAULT_API_URL)


def _dashboard_auth_flow(investigation_id: str) -> None:
    httpx.post(f"{API_URL}/investigations/{investigation_id}/auth/begin", timeout=5)
    for _ in range(120):
        investigation = httpx.get(f"{API_URL}/investigations/{investigation_id}", timeout=5).json()
        if investigation["status"] == "authenticated":
            return
        if investigation["status"] != "auth_required":
            raise RuntimeError(f"Unexpected investigation status: {investigation['status']}")

        session_response = httpx.get(f"{API_URL}/investigations/{investigation_id}/session", timeout=5)
        session = session_response.json()
        if (
            session_response.status_code == 200
            and session.get("auth_state") == "authenticated"
            and session.get("has_persisted_storage")
        ):
            if not session.get("human_ready"):
                httpx.post(f"{API_URL}/investigations/{investigation_id}/auth/mark-ready", timeout=5).raise_for_status()
            resume = httpx.post(f"{API_URL}/investigations/{investigation_id}/auth/resume", timeout=5)
            if resume.status_code == 200:
                return
            if resume.status_code != 409:
                resume.raise_for_status()
        time.sleep(0.25)

    raise RuntimeError("Browser never verified authentication")


def main() -> None:
    os.environ.setdefault("WEBTWIN_AUTH_TIMEOUT", "120")
    os.environ.setdefault("WEBTWIN_AUTO_LOGIN", "1")
    os.environ.setdefault("WEBTWIN_API_URL", API_URL)

    if not AUTH_FIXTURE.exists():
        raise SystemExit("auth fixture missing")

    httpx.get(f"{API_URL}/health", timeout=2)
    existing_ids = {item["id"] for item in httpx.get(f"{API_URL}/investigations", timeout=5).json()}
    errors: list[Exception] = []

    def watch_for_pause() -> None:
        try:
            for _ in range(120):
                investigations = httpx.get(f"{API_URL}/investigations", timeout=5).json()
                for investigation in investigations:
                    if investigation["id"] in existing_ids:
                        continue
                    if investigation["status"] == "auth_required":
                        _dashboard_auth_flow(investigation["id"])
                        return
                time.sleep(0.25)
            raise RuntimeError("Investigation never reached auth_required")
        except Exception as error:
            errors.append(error)

    watcher = threading.Thread(target=watch_for_pause, daemon=True)
    watcher.start()

    investigation_id, _candidates, _verified, _actions = run_discovery_and_verification(
        AUTH_FIXTURE,
        discovery_actions=[{"field": "condition", "value": "no"}],
        api_base_url=API_URL,
        headless=True,
    )

    watcher.join(timeout=30)
    if errors:
        raise errors[0]

    transitions = httpx.get(f"{API_URL}/investigations/{investigation_id}/transitions", timeout=5).json()
    statuses = [item["to_status"] for item in transitions]
    investigation = httpx.get(f"{API_URL}/investigations/{investigation_id}", timeout=5).json()
    session = httpx.get(f"{API_URL}/investigations/{investigation_id}/session", timeout=5).json()

    assert "auth_required" in statuses, statuses
    assert "authenticated" in statuses, statuses
    assert investigation["status"] == "completed", investigation["status"]
    assert session["has_persisted_storage"] is True
    print(f"Auth lifecycle passed for investigation {investigation_id}")


if __name__ == "__main__":
    main()
