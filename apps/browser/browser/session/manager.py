from collections.abc import Callable

from webtwin_core.models import AuthPauseMetadata, AuthPauseReason, AuthState, TransitionEvent


class SessionManager:
    """Human-in-the-loop auth: detect walls, pause, and resume safely."""

    # Prefer path-ish tokens; avoid bare "auth"/"spid" which match many post-login URLs.
    AUTH_HINTS = (
        "/login",
        "login?",
        "signin",
        "sign-in",
        "sign_in",
        "apply.login",
        "/sso",
        "sso?",
    )
    BLOCK_HINTS = ("captcha", "cloudflare", "challenge")

    def __init__(self, resume_callback: Callable[[], None] | None = None) -> None:
        self.paused = False
        self.pause_reason: str | None = None
        self.auth_state = AuthState.UNKNOWN
        self._resume_callback = resume_callback or self._default_resume_prompt

    def requires_authentication(self, url: str, has_password_field: bool) -> bool:
        if has_password_field:
            return True
        if url.lower().startswith("file:"):
            return False

        lowered = url.lower()
        if any(hint in lowered for hint in self.BLOCK_HINTS):
            return True
        return any(hint in lowered for hint in self.AUTH_HINTS)

    def detect_pause(self, url: str, has_password_field: bool, has_otp_field: bool = False) -> AuthPauseMetadata | None:
        if not has_password_field and not has_otp_field:
            if url.lower().startswith("file:"):
                # SPA fixtures may still show login walls on file://
                if self.sso_button_visible_static(url):
                    return AuthPauseMetadata(reason=AuthPauseReason.LOGIN_REQUIRED, resume_allowed=True, url=url)
                return None
            lowered = url.lower()
            if any(hint in lowered for hint in self.BLOCK_HINTS):
                reason = AuthPauseReason.CLOUDFLARE if "cloudflare" in lowered else AuthPauseReason.CAPTCHA
                return AuthPauseMetadata(reason=reason, resume_allowed=True, url=url)
            if any(hint in lowered for hint in self.AUTH_HINTS):
                return AuthPauseMetadata(reason=AuthPauseReason.LOGIN_REQUIRED, resume_allowed=True, url=url)
            return None

        if has_otp_field:
            return AuthPauseMetadata(reason=AuthPauseReason.MFA_REQUIRED, resume_allowed=True, url=url)
        return AuthPauseMetadata(reason=AuthPauseReason.LOGIN_REQUIRED, resume_allowed=True, url=url)

    @staticmethod
    def sso_button_visible_static(_url: str) -> bool:
        return False

    @staticmethod
    def sso_button_visible(page) -> bool:
        selectors = (
            'button:has-text("SSO")',
            'button:has-text("Sign in with")',
            '[data-testid="sso-login"]',
            'a:has-text("Sign in with")',
            'a:has-text("SPID")',
            'button:has-text("SPID")',
            'a:has-text("Entra con SPID")',
            'button:has-text("Entra con SPID")',
        )
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    return True
            except Exception:
                continue
        try:
            locator = page.get_by_text("Entra con SPID", exact=False)
            return locator.count() > 0 and locator.first.is_visible()
        except Exception:
            return False

    @staticmethod
    def password_field_visible(page) -> bool:
        try:
            locator = page.locator('input[type="password"]')
            return locator.count() > 0 and locator.first.is_visible()
        except Exception:
            return False

    @staticmethod
    def otp_field_visible(page) -> bool:
        try:
            locator = page.locator('input[autocomplete="one-time-code"], input[name*="otp" i]')
            return locator.count() > 0 and locator.first.is_visible()
        except Exception:
            return False

    def pause_for_human(self, metadata: AuthPauseMetadata) -> None:
        self.paused = True
        self.pause_reason = metadata.reason.value
        self.auth_state = AuthState.REQUIRED
        print(f"\n[WebTwin] Investigation paused: {metadata.reason.value}")
        print("[WebTwin] Complete authentication in the browser, then resume.")
        self._resume_callback()

    def mark_authenticated(self) -> None:
        self.paused = False
        self.pause_reason = None
        self.auth_state = AuthState.AUTHENTICATED

    def blocked_transition(self, reason: str) -> TransitionEvent:
        if "captcha" in reason.lower() or "cloudflare" in reason.lower():
            return TransitionEvent.BLOCK
        return TransitionEvent.CANCEL

    @staticmethod
    def _default_resume_prompt() -> None:
        input("[WebTwin] Press Enter when authentication is complete...")
