import os
import re
import time
from uuid import UUID

import httpx
from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError
from webtwin_core.models import AuthState, InvestigationStatus, TransitionEvent

from browser.client.api import ApiClient
from browser.session.auth_form_fill import apply_auth_form_fill
from browser.session.manager import SessionManager
from browser.session.store import SessionStore

# Path/query patterns that indicate an auth wall (avoid bare "auth"/"spid" substrings).
_AUTH_URL_RE = re.compile(
    r"(?:^|[/?#.&_=-])(?:login|signin|sign-in|sign_in|apply\.login|sso)(?:$|[/?#.&_=-])",
    re.IGNORECASE,
)


def _maybe_auto_login(page: Page, api_base_url: str, investigation_id: UUID) -> None:
    if os.environ.get("WEBTWIN_AUTO_LOGIN", "").lower() not in {"1", "true", "yes"}:
        return
    try:
        if page.locator("#login-form").count() == 0:
            return
    except PlaywrightError:
        return

    session = httpx.get(f"{api_base_url}/investigations/{investigation_id}/session", timeout=5)
    if session.status_code != 200 or session.json().get("session_status") != "authenticating":
        return

    page.locator('input[name="email"]').fill("analyst@example.com", force=True)
    page.locator('input[name="password"]').fill("test-password", force=True)
    page.locator("#login-form button[type='submit']").click(force=True)
    page.wait_for_timeout(500)


def _session_snapshot(api_base_url: str, investigation_id: UUID) -> dict:
    response = httpx.get(f"{api_base_url}/investigations/{investigation_id}/session", timeout=5)
    if response.status_code != 200:
        return {}
    return response.json()


def _url_looks_like_auth_wall(url: str) -> bool:
    return bool(_AUTH_URL_RE.search(url))


def _still_on_auth_wall(page: Page) -> bool:
    """True if the Playwright page still looks like a login / SSO / MFA wall."""
    has_password = SessionManager.password_field_visible(page)
    has_otp = SessionManager.otp_field_visible(page)
    has_sso = SessionManager.sso_button_visible(page)
    if has_password or has_otp:
        return True
    # SSO alone is only a wall when the URL still looks like login (post-login pages
    # may keep a "Sign in" footer link).
    if has_sso and _url_looks_like_auth_wall(page.url):
        return True
    if not has_sso and _url_looks_like_auth_wall(page.url):
        return True
    return False


def _persist_authenticated(
    client: ApiClient,
    context: BrowserContext,
    session_store: SessionStore,
    investigation_id: UUID,
) -> None:
    storage_path = session_store.save(context, investigation_id)
    client.upsert_session(
        investigation_id,
        auth_state=AuthState.AUTHENTICATED,
        storage_state_ref=str(storage_path),
    )
    print(f"[WebTwin] Auth verified — storage saved ({storage_path})")


def _try_auto_resume(client: ApiClient, investigation_id: UUID) -> bool:
    """Resume via API when human_ready + verified storage are both present."""
    response = httpx.post(
        f"{client.base_url}/investigations/{investigation_id}/auth/resume",
        timeout=10,
    )
    if response.status_code == 200:
        print("[WebTwin] Auto-resumed investigation after verified login")
        return True
    print(f"[WebTwin] Resume not ready yet: {response.status_code} {response.text[:160]}")
    return False


def _auth_wait_timeout_seconds() -> float | None:
    """Return wall-clock auth wait budget, or None to wait indefinitely."""
    raw = os.environ.get("WEBTWIN_AUTH_TIMEOUT", "0").strip()
    if not raw or raw.lower() in {"0", "none", "off", "false", "unlimited"}:
        return None
    return float(raw)


def wait_for_dashboard_auth_resume(
    client: ApiClient,
    investigation_id: UUID,
    page: Page,
    context: BrowserContext,
    session_store: SessionStore,
    session_manager: SessionManager,
    poll_interval: float = 0.5,
    timeout: float | None = None,
) -> None:
    """Wait for human auth via dashboard; browser verifies login before API resumes."""
    investigation = client.get_investigation(investigation_id)
    target_url = investigation.target_url
    wait_budget = _auth_wait_timeout_seconds() if timeout is None else timeout
    deadline = float("inf") if not wait_budget or wait_budget <= 0 else time.time() + wait_budget
    last_log = 0.0
    did_human_ready_nav = False
    storage_saved = False

    print("[WebTwin] Waiting for login in this Chromium window (not a separate Chrome tab).")
    print("[WebTwin] Prefer the dashboard form when fields appear, or sign in manually here.")
    print("[WebTwin] After login, click “I've completed authentication” in the dashboard if needed.")
    if deadline == float("inf"):
        print("[WebTwin] Auth wait: no timeout — take as long as you need.")

    fill_attempted = False

    while time.time() < deadline:
        investigation = client.get_investigation(investigation_id)
        if investigation.status == InvestigationStatus.AUTHENTICATED:
            session_manager.mark_authenticated()
            return

        session = _session_snapshot(client.base_url, investigation_id)
        human_ready = bool(session.get("human_ready"))

        try:
            if page.is_closed():
                raise TimeoutError("Browser closed while waiting for authentication — keep Chrome for Testing open")

            _maybe_auto_login(page, client.base_url, investigation_id)

            if not fill_attempted:
                pending = client.get_pending_auth_fill(investigation_id)
                if pending and pending.get("values"):
                    form = client.get_auth_form(investigation_id) or {}
                    print("[WebTwin] Applying dashboard auth form values into the browser…")
                    ok, details = apply_auth_form_fill(page, form, pending.get("values") or {})
                    fill_attempted = True
                    try:
                        client.mark_auth_fill_applied(
                            investigation_id,
                            status="applied" if ok else "failed",
                            error=None if ok else details,
                        )
                    except Exception as error:
                        print(f"[WebTwin] Could not mark fill applied: {error}")
                    print(f"[WebTwin] Dashboard form fill: {details}")
                    page.wait_for_timeout(1200)

            # When the human confirms, force-navigate to the app URL so SPID/popup
            # redirects that left the main page on login still get a chance to apply cookies.
            if human_ready and not did_human_ready_nav:
                print(f"[WebTwin] Human marked ready — opening target {target_url}")
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1500)
                except PlaywrightError as error:
                    print(f"[WebTwin] Target navigation after login: {error}")
                did_human_ready_nav = True

            on_wall = _still_on_auth_wall(page)
            now = time.time()
            if now - last_log >= 8:
                print(
                    f"[WebTwin] Auth check: url={page.url[:120]} "
                    f"wall={on_wall} human_ready={human_ready} storage_saved={storage_saved}"
                )
                last_log = now

            if not on_wall and not storage_saved:
                _persist_authenticated(client, context, session_store, investigation_id)
                storage_saved = True

            if storage_saved and human_ready:
                if _try_auto_resume(client, investigation_id):
                    session_manager.mark_authenticated()
                    return

        except PlaywrightError as error:
            if "closed" in str(error).lower():
                raise TimeoutError(
                    "Browser closed while waiting for authentication — keep Chrome for Testing open"
                ) from error
            raise

        time.sleep(poll_interval)

    investigation = client.get_investigation(investigation_id)
    if investigation.status == InvestigationStatus.AUTHENTICATED:
        session_manager.mark_authenticated()
        return
    if deadline != float("inf") and investigation.status == InvestigationStatus.AUTH_REQUIRED:
        client.transition(investigation_id, TransitionEvent.AUTH_TIMEOUT, reason="timeout")
        raise TimeoutError("Authentication timed out waiting for dashboard resume")
