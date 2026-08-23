"""M5 exit criterion: investigation survives API process restart with Postgres."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from api.db.engine import create_db_engine, create_session_factory, init_db, ping_db
from api.db.schema import EvidenceRow, FieldChangeRow, RuleEvidenceRow, RuleExperimentRow
from webtwin_core.models import (
    ApplicationState,
    Evidence,
    EvidenceType,
    FieldState,
    Investigation,
)
from webtwin_core.models.rule_status import RuleStatus
from webtwin_core.verification.engine import VerificationExperimentResult, VerificationRun

API_ROOT = Path(__file__).resolve().parents[1]


def _postgres_available() -> bool:
    try:
        ping_db(create_db_engine())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="PostgreSQL not available")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(base_url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception as error:  # noqa: BLE001 — poll until ready
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"API did not become healthy: {last_error}")


def _start_api(port: int) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "WEBTWIN_STORE": "postgres",
        "PYTHONPATH": str(API_ROOT),
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(API_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop_api(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="module")
def prepared_db() -> None:
    init_db(create_db_engine())


def test_investigation_survives_api_restart(prepared_db: None) -> None:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    session_factory = create_session_factory(create_db_engine())

    investigation_id: UUID | None = None
    rule_id: UUID | None = None
    evidence_ids: list[UUID] = []
    run_id: UUID | None = None
    diff_id: UUID | None = None
    evidence_id: UUID | None = None
    content_hash: str | None = None
    field_change_count = 0

    process = _start_api(port)
    try:
        _wait_healthy(base_url)

        created = httpx.post(
            f"{base_url}/investigations",
            json=Investigation(goal="restart proof", target_url="https://example.com/app").model_dump(
                mode="json"
            ),
            timeout=5,
        )
        assert created.status_code == 201
        investigation_id = UUID(created.json()["id"])

        for event in ("start", "init_complete", "auth_ok", "begin_exploration", "capture_observation"):
            transition = httpx.post(
                f"{base_url}/investigations/{investigation_id}/transition",
                json={"event": event},
                timeout=5,
            )
            assert transition.status_code == 200, transition.text

        before = ApplicationState(
            investigation_id=investigation_id,
            sequence=1,
            url="https://example.com/app",
            fields=[
                FieldState(name="condition", value="yes", visible=True),
                FieldState(name="reason", value=None, visible=False),
            ],
        )
        after = ApplicationState(
            investigation_id=investigation_id,
            sequence=2,
            url="https://example.com/app",
            fields=[
                FieldState(name="condition", value="no", visible=True),
                FieldState(name="reason", value=None, visible=True),
            ],
        )
        before_resp = httpx.post(
            f"{base_url}/investigations/{investigation_id}/states",
            json=before.model_dump(mode="json"),
            timeout=5,
        )
        after_resp = httpx.post(
            f"{base_url}/investigations/{investigation_id}/states",
            json=after.model_dump(mode="json"),
            timeout=5,
        )
        assert before_resp.status_code == 201
        assert after_resp.status_code == 201

        diff_resp = httpx.post(
            f"{base_url}/investigations/{investigation_id}/diff",
            params={
                "before_state_id": before_resp.json()["id"],
                "after_state_id": after_resp.json()["id"],
            },
            timeout=5,
        )
        assert diff_resp.status_code == 200, diff_resp.text
        diff_id = UUID(diff_resp.json()["id"])

        rules = httpx.get(f"{base_url}/investigations/{investigation_id}/rules", timeout=5).json()
        assert rules, "expected candidate rules from diff"
        rule_id = UUID(rules[0]["id"])
        evidence_ids = [UUID(item) for item in rules[0]["evidence_ids"]]
        assert evidence_ids

        run = VerificationRun(
            rule_id=rule_id,
            investigation_id=investigation_id,
            status=RuleStatus.VERIFIED,
            confidence=0.95,
            results=[
                VerificationExperimentResult(
                    experiment_id=UUID("11111111-1111-1111-1111-111111111111"),
                    passed=True,
                    details="restart-test",
                )
            ],
        )
        run_id = run.id
        verify = httpx.post(
            f"{base_url}/investigations/{investigation_id}/rules/{rule_id}/verify",
            json=run.model_dump(mode="json"),
            timeout=5,
        )
        assert verify.status_code == 200
        assert verify.json()["status"] == "verified"

        extra = Evidence(
            investigation_id=investigation_id,
            type=EvidenceType.DOM,
            payload={"checkpoint": "pre-restart"},
        )
        content_hash = extra.content_hash
        recorded = httpx.post(
            f"{base_url}/investigations/{investigation_id}/evidence",
            json=extra.model_dump(mode="json"),
            timeout=5,
        )
        assert recorded.status_code == 201
        evidence_id = UUID(recorded.json()["id"])
        assert recorded.json()["content_hash"] == content_hash

        with session_factory() as session:
            field_change_count = len(
                list(session.scalars(select(FieldChangeRow).where(FieldChangeRow.state_transition_id == diff_id)))
            )
            assert field_change_count > 0
            assert list(session.scalars(select(RuleEvidenceRow).where(RuleEvidenceRow.rule_id == rule_id)))
            assert list(session.scalars(select(RuleExperimentRow).where(RuleExperimentRow.rule_id == rule_id)))
    finally:
        _stop_api(process)

    assert investigation_id and rule_id and run_id and diff_id and evidence_id and content_hash

    process = _start_api(port)
    try:
        _wait_healthy(base_url)

        investigation = httpx.get(f"{base_url}/investigations/{investigation_id}", timeout=5)
        assert investigation.status_code == 200
        assert investigation.json()["goal"] == "restart proof"

        rules_after = httpx.get(f"{base_url}/investigations/{investigation_id}/rules", timeout=5)
        assert rules_after.status_code == 200
        restored_rule = next(rule for rule in rules_after.json() if UUID(rule["id"]) == rule_id)
        assert UUID(restored_rule["evidence_ids"][0]) in evidence_ids
        assert restored_rule["status"] == "verified"
        assert any(UUID(item) == run_id for item in restored_rule["verification_run_ids"])

        with session_factory() as session:
            field_changes = list(
                session.scalars(select(FieldChangeRow).where(FieldChangeRow.state_transition_id == diff_id))
            )
            evidence_links = list(
                session.scalars(select(RuleEvidenceRow).where(RuleEvidenceRow.rule_id == rule_id))
            )
            experiment_links = list(
                session.scalars(select(RuleExperimentRow).where(RuleExperimentRow.rule_id == rule_id))
            )
            evidence_row = session.get(EvidenceRow, evidence_id)

        assert len(field_changes) == field_change_count
        assert any(change.field == "condition" for change in field_changes)
        assert any(link.relation == "supported_by" for link in evidence_links)
        assert any(link.relation == "verified_by" for link in experiment_links)
        assert evidence_row is not None
        assert evidence_row.content_hash == content_hash
    finally:
        _stop_api(process)
