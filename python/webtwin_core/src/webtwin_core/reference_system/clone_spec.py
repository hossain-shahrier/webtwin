"""Clone-grade structured export for downstream implementation (Cursor, codegen, tests)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule, Investigation
from webtwin_core.reference_system import ReferenceSystemContext, build_reference_system_context


class CloneFieldSpec(BaseModel):
    name: str
    label: str | None = None
    input_type: str | None = None
    selector: str | None = None
    stable_key: str | None = None
    entity: str | None = None
    required: bool = False
    visible: bool = True


class CloneScreenSpec(BaseModel):
    id: str
    name: str
    path: str
    url: str
    role_scope: str | None = None
    fields: list[CloneFieldSpec] = Field(default_factory=list)


class CloneNavigationSpec(BaseModel):
    from_screen_id: str
    to_screen_id: str
    trigger: str
    href: str | None = None
    visited: bool = True


class CloneSiteGraphEdge(BaseModel):
    from_screen_id: str
    to_screen_id: str | None = None
    href: str
    visited: bool = False
    link_type: str = "navigate"


class CloneSiteGraphSpec(BaseModel):
    nodes: list[CloneScreenSpec] = Field(default_factory=list)
    edges: list[CloneSiteGraphEdge] = Field(default_factory=list)
    coverage_pct: float = 0.0
    unvisited_sample: list[str] = Field(default_factory=list)


class CloneFlowSpec(BaseModel):
    name: str
    role_scope: str | None = None
    entity_names: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class CloneRuleSpec(BaseModel):
    id: str
    name: str
    status: str
    confidence: float
    condition_field: str
    condition_operator: str
    condition_value: str | bool | int | float | None = None
    effect_field: str
    effect_visible: bool | None = None
    effect_required: bool | None = None
    effect_enabled: bool | None = None
    condition_selector: str | None = None
    effect_selector: str | None = None
    setup_fields: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    test_scenario: str = ""


class CloneUnknownSpec(BaseModel):
    screen_id: str | None = None
    field: str | None = None
    reason: str


class CloneApiHint(BaseModel):
    method: str | None = None
    url: str | None = None
    trigger_field: str | None = None
    body_shape: dict[str, Any] = Field(default_factory=dict)


class CloneApplicationSpec(BaseModel):
    key: str | None = None
    name: str | None = None
    target_url: str
    roles: list[str] = Field(default_factory=list)


class CloneSpec(BaseModel):
    investigation_id: str
    application: CloneApplicationSpec
    screens: list[CloneScreenSpec] = Field(default_factory=list)
    navigation: list[CloneNavigationSpec] = Field(default_factory=list)
    flows: list[CloneFlowSpec] = Field(default_factory=list)
    behavior: dict[str, list[CloneRuleSpec]] = Field(default_factory=dict)
    unknowns: list[CloneUnknownSpec] = Field(default_factory=list)
    api_hints: list[CloneApiHint] = Field(default_factory=list)
    site_graph: CloneSiteGraphSpec | None = None
    exploration_coverage: float = 0.0
    implementation_rules: list[str] = Field(default_factory=list)


def _selector_for_field(reference: ReferenceSystemContext, field_name: str) -> str | None:
    for screen in reference.screens:
        for field in screen.fields:
            if field.name == field_name and field.selector:
                return field.selector
    return None


def _rule_to_spec(rule: BusinessRule, reference: ReferenceSystemContext) -> CloneRuleSpec:
    from webtwin_core.privacy import redact_mapping

    condition_selector = rule.condition_selector or _selector_for_field(
        reference, rule.condition.field
    )
    effect_selector = rule.effect_selector or _selector_for_field(reference, rule.effect.field)
    setup = redact_mapping(rule.setup_fields)
    setup_bits = ""
    if setup:
        setup_bits = (
            " after setting "
            + ", ".join(f"{key}={value!r}" for key, value in setup.items())
        )
    scenario = (
        f"Given {rule.condition.field} {rule.condition.operator} {rule.condition.value!r}"
        f"{setup_bits}, "
        f"expect {rule.effect.field} "
        f"visible={rule.effect.visible} required={rule.effect.required} enabled={rule.effect.enabled}"
    )
    return CloneRuleSpec(
        id=str(rule.id),
        name=rule.name,
        status=rule.status.value,
        confidence=rule.confidence,
        condition_field=rule.condition.field,
        condition_operator=rule.condition.operator,
        condition_value=rule.condition.value,
        effect_field=rule.effect.field,
        effect_visible=rule.effect.visible,
        effect_required=rule.effect.required,
        effect_enabled=rule.effect.enabled,
        condition_selector=condition_selector,
        effect_selector=effect_selector,
        setup_fields=setup,
        evidence_ids=[str(eid) for eid in rule.evidence_ids],
        test_scenario=scenario,
    )


def build_clone_spec(
    investigation: Investigation,
    reference: ReferenceSystemContext,
    rules: list[BusinessRule],
    *,
    network_events: list[dict] | None = None,
    exploration_coverage: float = 0.0,
    unknown_fields: list[tuple[str, str]] | None = None,
) -> CloneSpec:
    verified = [_rule_to_spec(rule, reference) for rule in rules if rule.status.value == "verified"]
    candidates = [
        _rule_to_spec(rule, reference) for rule in rules if rule.status.value == "candidate"
    ]
    contradicted = [
        _rule_to_spec(rule, reference) for rule in rules if rule.status.value == "contradicted"
    ]

    screens = [
        CloneScreenSpec(
            id=screen.id,
            name=screen.name,
            path=screen.path,
            url=screen.url,
            role_scope=screen.role_scope,
            fields=[
                CloneFieldSpec(
                    name=field.name,
                    label=field.label,
                    input_type=field.input_type,
                    selector=field.selector,
                    stable_key=field.name,
                    entity=field.entity,
                    required=field.required,
                    visible=field.visible,
                )
                for field in screen.fields
            ],
        )
        for screen in reference.screens
    ]

    api_hints: list[CloneApiHint] = []
    from webtwin_core.reference_system.network_filter import is_relevant_api_url

    for event in network_events or []:
        url = event.get("url")
        if url and not is_relevant_api_url(str(url)):
            continue
        api_hints.append(
            CloneApiHint(
                method=event.get("method"),
                url=event.get("url"),
                trigger_field=event.get("trigger_field"),
                body_shape=event.get("body_shape") or {},
            )
        )

    unknowns = [
        CloneUnknownSpec(screen_id=screen_id, field=field, reason="not probed during exploration")
        for screen_id, field in (unknown_fields or [])
    ]

    roles = sorted(reference.related_roles or [])
    if reference.role_scope and reference.role_scope not in roles:
        roles.append(reference.role_scope)

    site_graph = CloneSiteGraphSpec(
        nodes=screens,
        edges=[
            CloneSiteGraphEdge(
                from_screen_id=link.from_screen_id,
                to_screen_id=link.to_screen_id,
                href=link.href,
                visited=link.visited,
                link_type=link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type),
            )
            for link in reference.discovered_links
        ],
        coverage_pct=float((reference.site_graph_stats or {}).get("coverage_pct", 0.0)),
        unvisited_sample=list((reference.site_graph_stats or {}).get("unvisited_sample", [])),
    )

    return CloneSpec(
        investigation_id=str(investigation.id),
        application=CloneApplicationSpec(
            key=reference.application_key,
            name=reference.application_name,
            target_url=investigation.target_url,
            roles=roles,
        ),
        screens=screens,
        navigation=[
            CloneNavigationSpec(
                from_screen_id=edge.from_screen_id,
                to_screen_id=edge.to_screen_id,
                trigger=edge.trigger,
                href=edge.href,
                visited=edge.visited,
            )
            for edge in reference.navigation
        ],
        flows=[
            CloneFlowSpec(
                name=flow.name,
                role_scope=flow.role_scope,
                entity_names=flow.entity_names,
                steps=[step.description for step in flow.steps],
            )
            for flow in reference.flows
        ],
        behavior={
            "verified": verified,
            "candidate": candidates,
            "contradicted": contradicted,
        },
        unknowns=unknowns,
        api_hints=api_hints,
        site_graph=site_graph,
        exploration_coverage=exploration_coverage,
        implementation_rules=[
            "Implement verified rules exactly; treat candidates as hypotheses only.",
            "Do not invent API contracts or role permissions not listed in this spec.",
            "Match behavior and field logic, not pixel-perfect visual design.",
            "Refuse or stub behavior marked under unknowns until investigated.",
        ],
    )
