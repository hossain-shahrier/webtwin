from datetime import UTC, datetime
from uuid import uuid4

from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    ElementSnapshot,
    FieldState,
    Investigation,
    InvestigationStatus,
    Observation,
    RuleCondition,
    RuleEffect,
    RuleStatus,
    TimelineEvent,
    TimelineEventType,
)
from webtwin_core.models.spa import RouteSnapshot
from webtwin_core.reference_system import (
    build_reference_system_context,
    format_reference_system_markdown,
    screen_key_from_observation,
)
from webtwin_core.reference_system.entities import match_entity_name


def test_match_entity_name_from_address_fields() -> None:
    assert match_entity_name("country", "Country of residence") == "Address"
    assert match_entity_name("employment_type") == "Employment"
    assert match_entity_name("random_widget") is None


def test_screen_key_prefers_route_path() -> None:
    observation = Observation(
        investigation_id=uuid4(),
        url="https://app.example.com/apply?tab=1",
        title="Apply",
        route=RouteSnapshot(url="https://app.example.com/apply?tab=1", path="/apply", title="Apply form"),
    )
    assert screen_key_from_observation(observation) == "/apply"


def test_build_reference_system_infers_entities_and_names_flows() -> None:
    investigation_id = uuid4()
    investigation = Investigation(
        id=investigation_id,
        goal="Explore apply flow",
        target_url="https://app.example.com/apply",
        status=InvestigationStatus.COMPLETED,
        application_name="Example ATS",
        role_scope="applicant",
    )
    observation = Observation(
        investigation_id=investigation_id,
        url="https://app.example.com/apply",
        title="Apply",
        route=RouteSnapshot(url="https://app.example.com/apply", path="/apply", title="Apply"),
        elements=[
            ElementSnapshot(
                selector="#country",
                tag="select",
                name="country",
                label="Country",
                stable_key="country",
            ),
            ElementSnapshot(
                selector="#province",
                tag="select",
                name="province",
                label="Province",
                stable_key="province",
            ),
            ElementSnapshot(
                selector="#email",
                tag="input",
                name="email",
                label="Email",
                stable_key="email",
                input_type="email",
            ),
        ],
    )
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        url="https://app.example.com/apply",
        fields=[FieldState(name="country", value="IT")],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        url="https://app.example.com/apply",
        fields=[FieldState(name="country", value="IT"), FieldState(name="province", visible=True)],
    )
    event = TimelineEvent(
        investigation_id=investigation_id,
        type=TimelineEventType.SELECT,
        description="Selected country IT",
        state_before_id=before.id,
        state_after_id=after.id,
        occurred_at=datetime.now(UTC),
    )
    event2 = TimelineEvent(
        investigation_id=investigation_id,
        type=TimelineEventType.INPUT,
        description="Filled email",
        state_before_id=before.id,
        state_after_id=after.id,
        occurred_at=datetime.now(UTC),
    )
    rule = BusinessRule(
        investigation_id=investigation_id,
        name="country reveals province",
        condition=RuleCondition(field="country", operator="equals", value="IT"),
        effect=RuleEffect(field="province", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.9,
    )

    context = build_reference_system_context(
        investigation,
        observations=[observation],
        events=[event, event2],
        rules=[rule],
        states=[before, after],
    )

    entity_names = {entity.name for entity in context.entities}
    assert "Address" in entity_names
    assert "Contact" in entity_names
    assert context.screens[0].primary_entity in {"Address", "Contact"}
    assert any(group.screen_id == "/apply" and group.verified for group in context.rules_by_screen)
    assert any("Address" in flow.name or flow.entity_names for flow in context.flows)
    assert any("country reveals province" in entity.rule_names for entity in context.entities if entity.name == "Address")
    markdown = format_reference_system_markdown(context)
    assert "Domain entities" in markdown
    assert "Address" in markdown
