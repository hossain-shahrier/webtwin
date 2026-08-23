from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AuthState(StrEnum):
    UNKNOWN = "unknown"
    REQUIRED = "required"
    AUTHENTICATED = "authenticated"
    BLOCKED = "blocked"


class SessionStatus(StrEnum):
    NOT_STARTED = "not_started"
    AUTH_REQUIRED = "auth_required"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    FAILED = "failed"


class AuthPauseReason(StrEnum):
    LOGIN_REQUIRED = "login_required"
    MFA_REQUIRED = "mfa_required"
    CAPTCHA = "captcha"
    CLOUDFLARE = "cloudflare"
    SESSION_EXPIRED = "session_expired"


class AuthPauseMetadata(BaseModel):
    reason: AuthPauseReason
    resume_allowed: bool = True
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None
    message: str | None = None
