from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.store import store
from webtwin_core.models import Investigation, InvestigationStatus, TransitionEvent


@pytest.fixture(autouse=True)
def reset_store() -> None:
    store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _create(client: TestClient) -> str:
    response = client.post(
        "/investigations",
        json=Investigation(goal="test", target_url="https://example.com/app").model_dump(mode="json"),
    )
    assert response.status_code == 201
    return response.json()["id"]


def _transition(client: TestClient, investigation_id: str, event: TransitionEvent, **payload: object) -> dict:
    response = client.post(
        f"/investigations/{investigation_id}/transition",
        json={"event": event.value, **payload},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _advance_to_exploring(client: TestClient, investigation_id: str) -> None:
    _transition(client, investigation_id, TransitionEvent.START)
    _transition(client, investigation_id, TransitionEvent.INIT_COMPLETE)
    _transition(client, investigation_id, TransitionEvent.AUTH_OK)
    _transition(client, investigation_id, TransitionEvent.BEGIN_EXPLORATION)


def test_invalid_transition_returns_409(client: TestClient) -> None:
    investigation_id = _create(client)
    response = client.post(
        f"/investigations/{investigation_id}/transition",
        json={"event": TransitionEvent.COMPLETE.value},
    )
    assert response.status_code == 409


def test_browser_crash_marks_failed(client: TestClient) -> None:
    investigation_id = _create(client)
    _advance_to_exploring(client, investigation_id)
    result = _transition(
        client,
        investigation_id,
        TransitionEvent.BROWSER_CRASH,
        reason="browser disconnected",
    )
    assert result["status"] == InvestigationStatus.FAILED.value
    assert result["failure_reason"] == "browser disconnected"


def test_auth_timeout_from_auth_required(client: TestClient) -> None:
    investigation_id = _create(client)
    _transition(client, investigation_id, TransitionEvent.START)
    _transition(client, investigation_id, TransitionEvent.INIT_COMPLETE)
    _transition(
        client,
        investigation_id,
        TransitionEvent.AUTH_REQUIRED,
        auth_pause={"reason": "login_required", "resume_allowed": True},
    )
    result = _transition(client, investigation_id, TransitionEvent.AUTH_TIMEOUT, reason="timeout")
    assert result["status"] == InvestigationStatus.FAILED.value
    assert result["auth_pause"] is not None


def test_cancel_from_verifying(client: TestClient) -> None:
    investigation_id = _create(client)
    _advance_to_exploring(client, investigation_id)
    _transition(client, investigation_id, TransitionEvent.CAPTURE_OBSERVATION)
    _transition(client, investigation_id, TransitionEvent.GENERATE_RULES)
    _transition(client, investigation_id, TransitionEvent.START_VERIFICATION)
    result = _transition(client, investigation_id, TransitionEvent.CANCEL, reason="user cancelled")
    assert result["status"] == InvestigationStatus.CANCELLED.value


def test_resume_from_failed_restores_checkpoint(client: TestClient) -> None:
    investigation_id = _create(client)
    _advance_to_exploring(client, investigation_id)
    _transition(client, investigation_id, TransitionEvent.BROWSER_CRASH, reason="crash")
    response = client.post(f"/investigations/{investigation_id}/resume")
    assert response.status_code == 200
    assert response.json()["status"] == InvestigationStatus.EXPLORING.value


def test_resume_clears_worker_claim(client: TestClient) -> None:
    investigation_id = _create(client)
    _advance_to_exploring(client, investigation_id)
    inv_uuid = UUID(investigation_id)
    store.investigation_claims[inv_uuid] = "dead-worker"
    _transition(client, investigation_id, TransitionEvent.BROWSER_CRASH, reason="crash")
    response = client.post(f"/investigations/{investigation_id}/resume")
    assert response.status_code == 200
    assert inv_uuid not in store.investigation_claims
    pending = client.get("/investigations/pending").json()
    assert any(item["id"] == investigation_id for item in pending)


def test_auth_required_from_exploring(client: TestClient) -> None:
    investigation_id = _create(client)
    _advance_to_exploring(client, investigation_id)
    result = _transition(
        client,
        investigation_id,
        TransitionEvent.AUTH_REQUIRED,
        auth_pause={"reason": "login_required", "resume_allowed": True},
    )
    assert result["status"] == InvestigationStatus.AUTH_REQUIRED.value


def test_resume_without_checkpoint_returns_409(client: TestClient) -> None:
    investigation_id = _create(client)
    _transition(client, investigation_id, TransitionEvent.START)
    _transition(client, investigation_id, TransitionEvent.BROWSER_CRASH, reason="early fail")
    response = client.post(f"/investigations/{investigation_id}/resume")
    assert response.status_code == 409
    assert "No checkpoint" in response.json()["detail"]


def test_restart_failed_without_checkpoint(client: TestClient) -> None:
    investigation_id = _create(client)
    _transition(client, investigation_id, TransitionEvent.START)
    _transition(client, investigation_id, TransitionEvent.BROWSER_CRASH, reason="early fail")
    response = client.post(f"/investigations/{investigation_id}/restart")
    assert response.status_code == 200
    assert response.json()["status"] == InvestigationStatus.CREATED.value
    assert response.json()["failure_reason"] is None


def test_idempotent_transition_retry(client: TestClient) -> None:
    investigation_id = _create(client)
    _transition(client, investigation_id, TransitionEvent.START)
    first = _transition(client, investigation_id, TransitionEvent.INIT_COMPLETE)
    second = _transition(client, investigation_id, TransitionEvent.INIT_COMPLETE)
    assert second["status"] == first["status"]
    transitions = client.get(f"/investigations/{investigation_id}/transitions").json()
    assert len(transitions) == 2


def test_session_endpoint_redacts_storage_path(client: TestClient) -> None:
    investigation_id = _create(client)
    response = client.post(
        f"/investigations/{investigation_id}/session",
        json={"auth_state": "authenticated", "storage_state_ref": "/secret/path/session.json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_persisted_storage"] is True
    assert "storage_state_ref" not in body
    assert "secret" not in str(body)


def test_auth_required_sets_pause_metadata(client: TestClient) -> None:
    investigation_id = _create(client)
    _transition(client, investigation_id, TransitionEvent.START)
    _transition(client, investigation_id, TransitionEvent.INIT_COMPLETE)
    result = _transition(
        client,
        investigation_id,
        TransitionEvent.AUTH_REQUIRED,
        auth_pause={"reason": "login_required", "resume_allowed": True, "url": "https://example.com/login"},
    )
    assert result["status"] == InvestigationStatus.AUTH_REQUIRED.value
    assert result["auth_pause"]["reason"] == "login_required"
    assert result["auth_pause"]["resume_allowed"] is True
