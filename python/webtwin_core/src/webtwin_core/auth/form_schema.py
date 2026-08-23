"""Build and fill auth form schemas from observations — no secrets stored in the schema."""

from __future__ import annotations

from webtwin_core.models.auth import AuthFormField, AuthFormSchema
from webtwin_core.models.observation import ElementSnapshot, Observation

_SKIP_TYPES = {"hidden", "submit", "button", "image", "reset", "file", "checkbox", "radio"}
_SECRET_TYPES = {"password"}
_EMAIL_HINTS = ("email", "e-mail", "mail", "user", "login", "account")
_PASSWORD_HINTS = ("password", "passwd", "pass", "pwd")
_NAME_HINTS = ("name", "first", "last", "full")
_PHONE_HINTS = ("phone", "tel", "mobile")
_COMPANY_HINTS = ("company", "organization", "org", "employer")


def _field_blob(element: ElementSnapshot) -> str:
    parts = [
        element.name or "",
        element.label or "",
        element.testid or "",
        element.stable_key or "",
        element.selector or "",
        element.input_type or "",
    ]
    return " ".join(parts).lower()


def _guess_label(element: ElementSnapshot) -> str:
    if element.label and element.label.strip():
        return element.label.strip()
    if element.name and element.name.strip():
        return element.name.replace("_", " ").replace("-", " ").strip().title()
    if element.testid:
        return element.testid.replace("_", " ").replace("-", " ").strip().title()
    input_type = (element.input_type or "text").lower()
    if input_type == "password":
        return "Password"
    if input_type == "email":
        return "Email"
    return "Field"


def _is_secret(element: ElementSnapshot) -> bool:
    input_type = (element.input_type or "").lower()
    if input_type in _SECRET_TYPES:
        return True
    blob = _field_blob(element)
    return any(hint in blob for hint in _PASSWORD_HINTS)


def _normalize_input_type(element: ElementSnapshot) -> str:
    raw = (element.input_type or "").lower() or "text"
    if raw in _SECRET_TYPES:
        return "password"
    if raw == "email":
        return "email"
    if raw in {"tel", "phone"}:
        return "tel"
    if raw == "number":
        return "number"
    if element.tag == "select":
        return "select"
    if element.tag == "textarea":
        return "textarea"
    blob = _field_blob(element)
    if any(hint in blob for hint in _EMAIL_HINTS) and "password" not in blob:
        return "email"
    if any(hint in blob for hint in _PASSWORD_HINTS):
        return "password"
    if any(hint in blob for hint in _PHONE_HINTS):
        return "tel"
    return "text"


def _page_kind(observation: Observation, fields: list[AuthFormField]) -> str:
    url = (observation.url or "").lower()
    title = (observation.title or "").lower()
    haystack = f"{url} {title}"
    if any(token in haystack for token in ("register", "signup", "sign-up", "sign_up", "create-account")):
        return "register"
    if any(token in haystack for token in ("otp", "mfa", "2fa", "verify")):
        return "mfa"
    labels = " ".join(f.label.lower() for f in fields)
    if "confirm" in labels and any(f.is_secret for f in fields):
        return "register"
    non_secret = [f for f in fields if not f.is_secret]
    if len(non_secret) >= 3:
        return "register"
    if any(f.is_secret for f in fields):
        return "login"
    return "unknown"


def _dummy_for_field(field: AuthFormField) -> str:
    key = f"{field.key} {field.label} {field.input_type}".lower()
    if field.input_type == "password" or field.is_secret:
        return "WebTwin-Test-Pass1!"
    if field.input_type == "email" or any(hint in key for hint in _EMAIL_HINTS):
        return "analyst@example.com"
    if field.input_type == "tel" or any(hint in key for hint in _PHONE_HINTS):
        return "+15550100"
    if any(hint in key for hint in _COMPANY_HINTS):
        return "WebTwin Demo Co"
    if any(hint in key for hint in _NAME_HINTS):
        if "first" in key:
            return "Alex"
        if "last" in key or "family" in key:
            return "Analyst"
        return "Alex Analyst"
    if field.input_type == "select" and field.options:
        return field.options[0]
    if field.input_type == "number":
        return "1"
    return "engineering"


def build_dummy_values(schema: AuthFormSchema) -> dict[str, str]:
    return {field.key: _dummy_for_field(field) for field in schema.fields}


def extract_auth_form_schema(observation: Observation) -> AuthFormSchema | None:
    """Derive a dashboard-safe form schema from a live observation on an auth wall."""
    candidates: list[ElementSnapshot] = []
    for element in observation.elements:
        if not element.visible or not element.enabled:
            continue
        tag = (element.tag or "").lower()
        if tag not in {"input", "select", "textarea"}:
            continue
        input_type = (element.input_type or "text").lower()
        if input_type in _SKIP_TYPES:
            continue
        # Prefer named/labelled interactive fields; skip bare chrome.
        blob = _field_blob(element)
        if tag == "input" and input_type in {"search"} and "q" in blob:
            continue
        candidates.append(element)

    if not candidates:
        return None

    # Prefer fields near password/email; otherwise keep first interactive cluster.
    prioritized = sorted(
        candidates,
        key=lambda el: (
            0 if _is_secret(el) else 1,
            0 if "email" in _field_blob(el) else 1,
            0 if el.required else 1,
        ),
    )
    # Cap to keep the dashboard usable.
    selected = prioritized[:12]

    fields: list[AuthFormField] = []
    seen_keys: set[str] = set()
    for element in selected:
        key = element.stable_key or element.name or element.testid or element.selector
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        input_type = _normalize_input_type(element)
        fields.append(
            AuthFormField(
                key=key,
                label=_guess_label(element),
                input_type=input_type,
                required=bool(element.required) or input_type in {"password", "email"},
                selector=element.selector,
                selector_candidates=list(element.selector_candidates or []),
                name=element.name,
                options=list(element.options or []),
                is_secret=_is_secret(element) or input_type == "password",
            )
        )

    if not fields:
        return None

    kind = _page_kind(observation, fields)
    notes: list[str] = []
    if kind == "login":
        notes.append("Mirrors the site login form. Values are filled into the headed browser.")
    elif kind == "register":
        notes.append("Mirrors the site registration form. Prefer test/dummy accounts on live systems.")
    notes.append("SSO / CAPTCHA / MFA may still require completing steps in Chrome for Testing.")

    return AuthFormSchema(
        page_kind=kind,
        url=observation.url,
        title=observation.title,
        fields=fields,
        submit_label="Create account" if kind == "register" else "Sign in",
        supports_dummy=True,
        notes=notes,
    )
