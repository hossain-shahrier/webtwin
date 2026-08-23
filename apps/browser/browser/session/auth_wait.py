import os
import time
from uuid import UUID

import httpx
from playwright.sync_api import BrowserContext, Page
from webtwin_core.models import AuthState, InvestigationStatus, TransitionEvent

from browser.client.api import ApiClient
from browser.session.manager import SessionManager
from browser.session.store import SessionStore


def _maybe_auto_login(page: Page, api_base_url: str, investigation_id: UUID) -> None:
    if os.environ.get("WEBTWIN_AUTO_LOGIN", "").lower() not in {"1", "true", "yes"}:
        return
    if page.locator("#login-form").count() == 0:
        return

    session = httpx.get(f"{api_base_url}/investigations/{investigation_id}/session", timeout=5)
    if session.status_code != 200 or session.json().get("session_status") != "authenticating":
        return

    page.locator('input[name="email"]').fill("analyst@example.com", force=True)
    page.locator('input[name="password"]').fill("test-password", force=True)
    page.locator("#login-form button[type='submit']").click(force=True)
    page.wait_for_timeout(500)


def wait_for_dashboard_auth_resume(
    client: ApiClient,
    investigation_id: UUID,
    page: Page,
    context: BrowserContext,
    session_store: SessionStore,
    session_manager: SessionManager,
    poll_interval: float = 0.5,
    timeout: float = float(os.environ.get("WEBTWIN_AUTH_TIMEOUT", "300")),
) -> None:
    """Wait for human auth via dashboard; browser verifies login before API resumes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        investigation = client.get_investigation(investigation_id)
        if investigation.status == InvestigationStatus.AUTHENTICATED:
            session_manager.mark_authenticated()
            return

        _maybe_auto_login(page, client.base_url, investigation_id)

        if not session_manager.detect_pause(
            page.url,
            SessionManager.password_field_visible(page),
            SessionManager.otp_field_visible(page),
        ):
            storage_path = session_store.save(context, investigation_id)
            client.upsert_session(
                investigation_id,
                auth_state=AuthState.AUTHENTICATED,
                storage_state_ref=str(storage_path),
            )

        time.sleep(poll_interval)

    investigation = client.get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTHENTICATED:
        session_manager.mark_authenticated()
        return
    if investigation.status == InvestigationStatus.AUTH_REQUIRED:
        client.transition(investigation_id, TransitionEvent.AUTH_TIMEOUT, reason="timeout")
    raise TimeoutError("Authentication timed out waiting for dashboard resume")
