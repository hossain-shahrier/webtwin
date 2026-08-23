from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuthState(StrEnum):
    UNKNOWN = "unknown"
    REQUIRED = "required"
    AUTHENTICATED = "authenticated"
    BLOCKED = "blocked"


class SessionStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
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


class AuthFormField(BaseModel):
    """A single field observed on a login/register wall — safe to render in the dashboard."""

    key: str
    label: str
    input_type: str = "text"
    required: bool = False
    selector: str
    selector_candidates: list[str] = Field(default_factory=list)
    name: str | None = None
    placeholder: str | None = None
    options: list[str] = Field(default_factory=list)
    autocomplete: str | None = None
    is_secret: bool = False


class AuthFormSchema(BaseModel):
    """Dynamic mirror of the reference site's auth form (no secrets)."""

    page_kind: str = "login"  # login | register | mfa | unknown
    url: str | None = None
    title: str | None = None
    form_selector: str | None = None
    fields: list[AuthFormField] = Field(default_factory=list)
    submit_label: str | None = None
    supports_dummy: bool = True
    notes: list[str] = Field(default_factory=list)


class AuthFormSubmission(BaseModel):
    """User-provided (or dummy) values for the worker to fill into the live page."""

    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    values: dict[str, str] = Field(default_factory=dict)
    use_dummy: bool = False
    status: str = "pending"  # pending | applied | failed | cancelled
    error: str | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    applied_at: datetime | None = None


class AuthPauseMetadata(BaseModel):
    reason: AuthPauseReason
    resume_allowed: bool = True
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None
    message: str | None = None
    form: AuthFormSchema | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
