"""PII / secrets redaction for exports and evidence payloads."""

from __future__ import annotations

import re

_SENSITIVE_NAME = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|ssn|social|"
    r"credit|card|cvv|cvc|iban|account[_-]?number|dob|date[_-]?of[_-]?birth|"
    r"phone|email|national[_-]?id)",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def is_sensitive_field_name(name: str | None) -> bool:
    if not name:
        return False
    return bool(_SENSITIVE_NAME.search(name))


def redact_value(field_name: str | None, value: str | None) -> str | None:
    """Mask sensitive field values; leave non-sensitive values unchanged."""
    if value is None:
        return None
    if is_sensitive_field_name(field_name):
        if len(value) <= 4:
            return "[REDACTED]"
        return f"{value[:2]}…[REDACTED]"
    # Opportunistic pattern scrub even when field name is benign
    scrubbed = _EMAIL.sub("[REDACTED_EMAIL]", value)
    scrubbed = _PHONE.sub("[REDACTED_PHONE]", scrubbed)
    return scrubbed


def redact_mapping(values: dict[str, str] | None) -> dict[str, str]:
    if not values:
        return {}
    return {
        key: (redact_value(key, str(val)) or "")
        for key, val in values.items()
    }
