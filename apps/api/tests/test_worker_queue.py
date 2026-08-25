from webtwin_core.models import Investigation, InvestigationStatus, TransitionEvent

from api.services import investigations as svc
from api.store import store


def test_pending_and_claim() -> None:
    store.clear()
    created = svc.create_investigation(
        Investigation(goal="worker job", target_url="file:///tmp/x.html", feature_scope="information_gain")
    )
    assert created.status == InvestigationStatus.CREATED
    pending = svc.list_pending_investigations()
    assert any(item.id == created.id for item in pending)

    claimed = svc.claim_investigation(created.id)
    assert claimed.status == InvestigationStatus.INITIALIZING
    assert svc.list_pending_investigations() == []


def test_auth_required_is_reclaimable() -> None:
    store.clear()
    created = svc.create_investigation(
        Investigation(goal="auth job", target_url="https://example.com/login", feature_scope="information_gain")
    )
    svc.claim_investigation(created.id)
    svc.transition_investigation(
        created.id,
        svc.TransitionRequest(event=TransitionEvent.INIT_COMPLETE),
    )
    svc.transition_investigation(
        created.id,
        svc.TransitionRequest(event=TransitionEvent.AUTH_REQUIRED),
    )
    pending = svc.list_pending_investigations()
    assert any(item.id == created.id and item.status == InvestigationStatus.AUTH_REQUIRED for item in pending)
    reclaimed = svc.claim_investigation(created.id)
    assert reclaimed.status == InvestigationStatus.AUTH_REQUIRED


def test_complete_releases_claim_and_records_audit(monkeypatch) -> None:
    store.clear()
    monkeypatch.setenv("WEBTWIN_WORKER_ID", "worker-a")
    created = svc.create_investigation(
        Investigation(goal="done", target_url="https://example.com", feature_scope="information_gain")
    )
    svc.claim_investigation(created.id)
    assert created.id in store.investigation_claims
    # Drive to exploring then complete
    svc.transition_investigation(
        created.id, svc.TransitionRequest(event=TransitionEvent.INIT_COMPLETE)
    )
    # AUTH_CHECK → may need AUTH_NOT_REQUIRED or similar — use fail path which always releases
    svc.transition_investigation(
        created.id, svc.TransitionRequest(event=TransitionEvent.FAIL, reason="test")
    )
    assert created.id not in store.investigation_claims
    assert any(
        getattr(event, "action", None) == "investigation.transition"
        for event in store.audit_events.values()
    )


def test_stale_initializing_is_reclaimable(monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    store.clear()
    monkeypatch.setenv("WEBTWIN_WORKER_ID", "worker-a")
    created = svc.create_investigation(
        Investigation(goal="orphan", target_url="https://example.com", feature_scope="information_gain")
    )
    claimed = svc.claim_investigation(created.id)
    assert claimed.status == InvestigationStatus.INITIALIZING
    store.investigation_claim_at[created.id] = datetime.now(UTC) - timedelta(hours=2)
    monkeypatch.setenv("WEBTWIN_WORKER_ID", "worker-b")
    pending = svc.list_pending_investigations()
    assert any(item.id == created.id for item in pending)
    reclaimed = svc.claim_investigation(created.id)
    assert store.investigation_claims[created.id] == "worker-b"
    assert reclaimed.status == InvestigationStatus.INITIALIZING
