from webtwin_core.models import Investigation, InvestigationStatus

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
