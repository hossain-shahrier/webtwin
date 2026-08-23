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
