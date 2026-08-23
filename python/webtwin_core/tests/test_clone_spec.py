"""Clone spec export tests."""

from uuid import uuid4

from webtwin_core.models import (
    BusinessRule,
    Investigation,
    InvestigationStatus,
    Observation,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.models.spa import RouteSnapshot
from webtwin_core.models import ElementSnapshot
from webtwin_core.reference_system.clone_spec import build_clone_spec
from webtwin_core.reference_system import build_reference_system_context


def test_build_clone_spec_includes_verified_tiers() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="test",
        target_url="https://example.com/form",
        status=InvestigationStatus.COMPLETED,
    )
    observation = Observation(
        investigation_id=inv_id,
        url="https://example.com/form",
        title="Form",
        route=RouteSnapshot(url="https://example.com/form", path="/form", title="Form"),
        elements=[
            ElementSnapshot(
                selector="#country",
                tag="select",
                name="country",
                stable_key="country",
                label="Country",
            ),
        ],
    )
    verified = BusinessRule(
        investigation_id=inv_id,
        name="country shows province",
        condition=RuleCondition(field="country", operator="equals", value="IT"),
        effect=RuleEffect(field="province", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
    )
    reference = build_reference_system_context(
        investigation,
        observations=[observation],
        events=[],
        rules=[verified],
    )
    spec = build_clone_spec(investigation, reference, [verified])
    assert spec.behavior["verified"]
    assert spec.screens[0].fields[0].name == "country"
    assert spec.implementation_rules
    assert spec.site_graph is not None
    assert spec.site_graph.coverage_pct >= 0
