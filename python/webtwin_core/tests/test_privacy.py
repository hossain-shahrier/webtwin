from webtwin_core.privacy import is_sensitive_field_name, redact_mapping, redact_value


def test_redact_sensitive_field_names() -> None:
    assert is_sensitive_field_name("user_password")
    assert redact_value("api_key", "supersecret") == "su…[REDACTED]"
    assert "[REDACTED_EMAIL]" in (redact_value("notes", "mail me at a@b.co") or "")
    mapping = redact_mapping({"email": "a@b.co", "country": "IT"})
    assert mapping["country"] == "IT"
    assert "[REDACTED" in mapping["email"]
