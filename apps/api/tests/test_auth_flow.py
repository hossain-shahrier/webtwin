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
        json=Investigation(goal="auth", target_url="https://example.com/login").model_dump(mode="json"),
    )
    return response.json()["id"]


def _to_auth_required(client: TestClient, investigation_id: str) -> None:
    for event in (TransitionEvent.START, TransitionEvent.INIT_COMPLETE):
        client.post(f"/investigations/{investigation_id}/transition", json={"event": event.value})
    client.post(
        f"/investigations/{investigation_id}/transition",
        json={
            "event": TransitionEvent.AUTH_REQUIRED.value,
            "auth_pause": {"reason": "login_required", "resume_allowed": True},
        },
    )


def test_auth_dashboard_flow(client: TestClient) -> None:
    investigation_id = _create(client)
    _to_auth_required(client, investigation_id)

    begin = client.post(f"/investigations/{investigation_id}/auth/begin")
    assert begin.status_code == 200
    assert begin.json()["session_status"] == "authenticating"

    denied = client.post(f"/investigations/{investigation_id}/auth/resume")
    assert denied.status_code == 409

    ready = client.post(f"/investigations/{investigation_id}/auth/mark-ready")
    assert ready.status_code == 200
    assert ready.json()["human_ready"] is True

    still_denied = client.post(f"/investigations/{investigation_id}/auth/resume")
    assert still_denied.status_code == 409

    client.post(
        f"/investigations/{investigation_id}/session",
        json={"auth_state": "authenticated", "storage_state_ref": "/tmp/session.json"},
    )
    resumed = client.post(f"/investigations/{investigation_id}/auth/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == InvestigationStatus.AUTHENTICATED.value


def test_auth_resume_rejected_for_non_auth_required(client: TestClient) -> None:
    investigation_id = _create(client)
    client.post(f"/investigations/{investigation_id}/transition", json={"event": "start"})
    response = client.post(f"/investigations/{investigation_id}/auth/resume")
    assert response.status_code == 409


def test_investigation_detail_includes_session(client: TestClient) -> None:
    investigation_id = _create(client)
    _to_auth_required(client, investigation_id)
    detail = client.get(f"/investigations/{investigation_id}/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["session"]["session_status"] == "auth_required"


def test_dynamic_auth_form_submit_and_pending_fill(client: TestClient) -> None:
    investigation_id = _create(client)
    _to_auth_required(client, investigation_id)

    schema = {
        "page_kind": "login",
        "url": "https://example.com/login",
        "title": "Sign in",
        "fields": [
            {
                "key": "email",
                "label": "Email",
                "input_type": "email",
                "required": True,
                "selector": 'input[name="email"]',
                "is_secret": False,
            },
            {
                "key": "password",
                "label": "Password",
                "input_type": "password",
                "required": True,
                "selector": 'input[name="password"]',
                "is_secret": True,
            },
        ],
        "submit_label": "Sign in",
        "supports_dummy": True,
    }
    put = client.put(f"/investigations/{investigation_id}/auth/form", json=schema)
    assert put.status_code == 200
    assert put.json()["page_kind"] == "login"

    got = client.get(f"/investigations/{investigation_id}/auth/form")
    assert got.status_code == 200
    assert len(got.json()["form"]["fields"]) == 2

    submitted = client.post(
        f"/investigations/{investigation_id}/auth/submit-form",
        json={"use_dummy": True},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending"
    assert "email" in submitted.json()["values"]

    pending = client.get(f"/investigations/{investigation_id}/auth/pending-fill")
    assert pending.status_code == 200
    assert pending.json()["submission"]["status"] == "pending"

    applied = client.post(
        f"/investigations/{investigation_id}/auth/fill-applied",
        json={"status": "applied"},
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"

    cleared = client.get(f"/investigations/{investigation_id}/auth/pending-fill")
    assert cleared.json()["submission"] is None
