"""Tests for dashboard-mirrored auth form schema extraction."""

from uuid import uuid4

from webtwin_core.auth.form_schema import build_dummy_values, extract_auth_form_schema
from webtwin_core.models.observation import ElementSnapshot, Observation


def test_extract_login_form_schema():
    observation = Observation(
        investigation_id=uuid4(),
        url="https://example.com/login",
        title="Sign in",
        elements=[
            ElementSnapshot(
                selector='input[name="email"]',
                tag="input",
                name="email",
                label="Email",
                input_type="email",
                visible=True,
                enabled=True,
                required=True,
                stable_key="email",
            ),
            ElementSnapshot(
                selector='input[name="password"]',
                tag="input",
                name="password",
                label="Password",
                input_type="password",
                visible=True,
                enabled=True,
                required=True,
                stable_key="password",
            ),
            ElementSnapshot(
                selector='input[type="hidden"]',
                tag="input",
                name="csrf",
                input_type="hidden",
                visible=False,
                enabled=True,
            ),
        ],
    )
    schema = extract_auth_form_schema(observation)
    assert schema is not None
    assert schema.page_kind == "login"
    assert len(schema.fields) == 2
    assert any(field.is_secret for field in schema.fields)
    dummy = build_dummy_values(schema)
    assert "analyst@example.com" in dummy.values()
    assert any("Pass" in value or "pass" in value.lower() for value in dummy.values())


def test_extract_register_form_schema():
    observation = Observation(
        investigation_id=uuid4(),
        url="https://example.com/register",
        title="Create account",
        elements=[
            ElementSnapshot(
                selector="#first_name",
                tag="input",
                name="first_name",
                label="First name",
                input_type="text",
                visible=True,
                enabled=True,
                stable_key="first_name",
            ),
            ElementSnapshot(
                selector="#email",
                tag="input",
                name="email",
                label="Work email",
                input_type="email",
                visible=True,
                enabled=True,
                stable_key="email",
            ),
            ElementSnapshot(
                selector="#company",
                tag="input",
                name="company",
                label="Company",
                input_type="text",
                visible=True,
                enabled=True,
                stable_key="company",
            ),
            ElementSnapshot(
                selector="#password",
                tag="input",
                name="password",
                label="Password",
                input_type="password",
                visible=True,
                enabled=True,
                stable_key="password",
            ),
        ],
    )
    schema = extract_auth_form_schema(observation)
    assert schema is not None
    assert schema.page_kind == "register"
    assert len(schema.fields) >= 3
