"""Token-budgeted export for AI coding assistants (Cursor, codegen agents)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule, Investigation
from webtwin_core.reference_system import ReferenceSystemContext, Screen, ScreenField
from webtwin_core.reference_system.clone_spec import (
    CloneAbsenceSpec,
    CloneApiHint,
    CloneApplicationSpec,
    CloneFlowSpec,
    CloneRuleSpec,
    CloneUnknownSpec,
    _rule_to_spec,
)
from webtwin_core.reference_system.entities import DomainEntity
from webtwin_core.reference_system.site_graph import export_path_pattern
from webtwin_core.reference_system.network_filter import is_relevant_api_url
from webtwin_core.reference_system.site_graph import DiscoveredLink

_INTERACTION_INPUT_TYPES = frozenset(
    {
        "text",
        "password",
        "email",
        "search",
        "tel",
        "url",
        "number",
        "date",
        "datetime-local",
        "time",
        "checkbox",
        "radio",
        "select",
        "textarea",
        "submit",
        "button",
        "hidden",
    }
)
_INTERACTIVE_SELECTOR_PREFIXES = ("input", "select", "textarea", "button", "[role=", "form", "#")
_NOISE_FIELD_NAMES = frozenset(
    {
        "g-recaptcha-response",
        "testcookie",
        "redirect_to",
        "_wp_http_referer",
        "wps_wpr_verify_cart_nonce",
        "wfls-email-verification",
        "variation_id",
        "product_id",
        "add-to-cart",
        "paged",
    }
)
_NOISE_FIELD_PREFIXES = ("wc_order_attribution_",)
_GLOBAL_CHROME_MIN_SCREENS = 3
_GLOBAL_CHROME_RATIO = 0.5
_ROUTE_GROUP_LABELS = {
    "static": "Marketing & info",
    "form": "Forms & workflows",
    "auth": "Authentication & account",
    "cart": "Cart & checkout",
    "category": "Product categories",
    "product": "Product detail",
    "other": "Other",
}
_ROUTE_GROUP_ORDER = ("static", "form", "auth", "cart", "category", "product", "other")


def is_interaction_field(field: ScreenField) -> bool:
    """True for form controls and labeled inputs — not bare navigation anchors."""
    selector = (field.selector or field.name or "").strip().lower()
    if selector == "a" or selector.startswith("a[href"):
        return False
    if field.entity and not selector.startswith("a"):
        return True
    input_type = (field.input_type or "").lower()
    if input_type in _INTERACTION_INPUT_TYPES:
        return True
    if field.required or field.label:
        return True
    return any(selector.startswith(prefix) for prefix in _INTERACTIVE_SELECTOR_PREFIXES)


def is_export_noise(field: ScreenField) -> bool:
    """Drop tracking, security tokens, and WooCommerce hidden internals."""
    name = (field.name or "").lower()
    if any(name.startswith(prefix) for prefix in _NOISE_FIELD_PREFIXES):
        return True
    if name in _NOISE_FIELD_NAMES:
        return True
    if name.endswith("-nonce") or name.endswith("_nonce"):
        return True
    if (field.input_type or "").lower() == "hidden" and not field.label and not field.entity:
        return True
    return False


def filter_interaction_fields(fields: list[ScreenField]) -> list[ScreenField]:
    return [
        field
        for field in fields
        if is_interaction_field(field) and not is_export_noise(field)
    ]


def classify_route_path(path: str) -> str:
    normalized = (path or "/").lower()
    if "/forms/" in normalized:
        return "form"
    if "login" in normalized or "my-account" in normalized or normalized.endswith("/account"):
        return "auth"
    if "cart" in normalized or "checkout" in normalized:
        return "cart"
    if "/product-category/" in normalized:
        return "category"
    if "/product/" in normalized:
        return "product"
    if normalized in {"/store/", "/404", "/not-found"}:
        return "other"
    return "static"


class AiRouteSpec(BaseModel):
    id: str
    name: str
    path: str
    url: str
    role_scope: str | None = None
    primary_entity: str | None = None
    kind: str = "static"


class AiRouteGroup(BaseModel):
    kind: str
    label: str
    routes: list[AiRouteSpec] = Field(default_factory=list)


class AiInteractionField(BaseModel):
    name: str
    label: str | None = None
    input_type: str | None = None
    selector: str | None = None
    entity: str | None = None
    required: bool = False
    visible: bool = True


class AiScreenInteractions(BaseModel):
    screen_id: str
    path: str
    name: str
    kind: str = "static"
    fields: list[AiInteractionField] = Field(default_factory=list)


class AiCollapsedInteractions(BaseModel):
    pattern: str
    name: str
    kind: str = "static"
    fields: list[AiInteractionField] = Field(default_factory=list)
    instance_count: int = 1
    examples: list[str] = Field(default_factory=list)


class AiCollapsedRoute(BaseModel):
    pattern: str
    name: str
    primary_entity: str | None = None
    kind: str = "static"
    instance_count: int = 1
    examples: list[str] = Field(default_factory=list)


class AiNavEdge(BaseModel):
    from_screen_id: str
    to_screen_id: str | None = None
    href: str
    visited: bool = False


class AiSpecSummary(BaseModel):
    screen_count: int = 0
    layout_field_count: int = 0
    interaction_field_count: int = 0
    unique_interaction_field_count: int = 0
    navigation_edge_count: int = 0
    verified_rule_count: int = 0
    candidate_rule_count: int = 0
    absence_count: int = 0
    link_coverage_pct: float = 0.0
    exploration_coverage: float = 0.0


class AiSpec(BaseModel):
    investigation_id: str
    application: CloneApplicationSpec
    summary: AiSpecSummary
    markdown: str
    layout: list[AiInteractionField] = Field(default_factory=list)
    routes: list[AiRouteSpec] = Field(default_factory=list)
    route_groups: list[AiRouteGroup] = Field(default_factory=list)
    interactions: list[AiScreenInteractions] = Field(default_factory=list)
    navigation: list[AiNavEdge] = Field(default_factory=list)
    verified_rules: list[CloneRuleSpec] = Field(default_factory=list)
    candidate_rules: list[CloneRuleSpec] = Field(default_factory=list)
    absences: list[CloneAbsenceSpec] = Field(default_factory=list)
    flows: list[CloneFlowSpec] = Field(default_factory=list)
    api_hints: list[CloneApiHint] = Field(default_factory=list)
    unknowns: list[CloneUnknownSpec] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


def _compact_navigation(
    links: list[DiscoveredLink],
    *,
    max_edges: int = 150,
) -> list[AiNavEdge]:
    deduped: dict[tuple[str, str], AiNavEdge] = {}
    for link in links:
        target = link.to_screen_id or link.href
        key = (link.from_screen_id, target)
        edge = AiNavEdge(
            from_screen_id=link.from_screen_id,
            to_screen_id=link.to_screen_id,
            href=link.href,
            visited=link.visited,
        )
        existing = deduped.get(key)
        if existing is None or (edge.visited and not existing.visited):
            deduped[key] = edge
    ordered = sorted(
        deduped.values(),
        key=lambda item: (not item.visited, item.from_screen_id, item.to_screen_id or item.href),
    )
    return ordered[:max_edges]


def _field_signature(fields: list[AiInteractionField]) -> tuple[tuple[str, str | None, str | None, str | None], ...]:
    return tuple((field.name, field.input_type, field.label, field.entity) for field in fields)


def _collapse_interactions(
    interactions: list[AiScreenInteractions],
) -> list[AiCollapsedInteractions]:
    grouped: dict[tuple[str, str, str, tuple], AiCollapsedInteractions] = {}
    for screen in interactions:
        pattern = export_path_pattern(screen.path)
        signature = _field_signature(screen.fields)
        key = (pattern, screen.name, screen.kind, signature)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = AiCollapsedInteractions(
                pattern=pattern,
                name=screen.name,
                kind=screen.kind,
                fields=screen.fields,
                instance_count=1,
                examples=[screen.path],
            )
            continue
        existing.instance_count += 1
        if len(existing.examples) < 3 and screen.path not in existing.examples:
            existing.examples.append(screen.path)
    return sorted(grouped.values(), key=lambda item: (item.kind, item.pattern))


def _collapse_routes(routes: list[AiRouteSpec]) -> list[AiCollapsedRoute]:
    grouped: dict[tuple[str, str, str | None, str], AiCollapsedRoute] = {}
    for route in routes:
        pattern = export_path_pattern(route.path)
        key = (pattern, route.name, route.primary_entity, route.kind)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = AiCollapsedRoute(
                pattern=pattern,
                name=route.name,
                primary_entity=route.primary_entity,
                kind=route.kind,
                instance_count=1,
                examples=[route.path],
            )
            continue
        existing.instance_count += 1
        if len(existing.examples) < 3 and route.path not in existing.examples:
            existing.examples.append(route.path)
    return sorted(grouped.values(), key=lambda item: (item.kind, item.pattern))


def _format_screen_patterns(screen_ids: list[str], *, limit: int = 4) -> str:
    if not screen_ids:
        return "—"
    patterns: dict[str, list[str]] = {}
    for screen_id in screen_ids:
        pattern = export_path_pattern(screen_id)
        patterns.setdefault(pattern, []).append(screen_id)
    parts: list[str] = []
    for pattern, instances in sorted(patterns.items()):
        if len(instances) > 1:
            parts.append(f"`{pattern}` (×{len(instances)})")
        else:
            parts.append(f"`{instances[0]}`")
        if len(parts) >= limit:
            break
    if len(patterns) > limit:
        parts.append("…")
    return ", ".join(parts)


def _field_to_ai(field: ScreenField) -> AiInteractionField:
    return AiInteractionField(
        name=field.name,
        label=field.label,
        input_type=field.input_type,
        selector=field.selector,
        entity=field.entity,
        required=field.required,
        visible=field.visible,
    )


def _format_field_line(field: AiInteractionField) -> str:
    label = f" ({field.label})" if field.label else ""
    req = " required" if field.required else ""
    entity = f" · {field.entity}" if field.entity else ""
    return f"- `{field.name}`{label}: {field.input_type or 'control'}{req}{entity}"


def _group_routes(routes: list[AiRouteSpec]) -> list[AiRouteGroup]:
    buckets: dict[str, list[AiRouteSpec]] = {kind: [] for kind in _ROUTE_GROUP_ORDER}
    for route in routes:
        buckets.setdefault(route.kind, []).append(route)
    groups: list[AiRouteGroup] = []
    for kind in _ROUTE_GROUP_ORDER:
        items = buckets.get(kind) or []
        if not items:
            continue
        groups.append(
            AiRouteGroup(
                kind=kind,
                label=_ROUTE_GROUP_LABELS[kind],
                routes=sorted(items, key=lambda route: route.path),
            )
        )
    return groups


def _extract_layout_and_interactions(
    screens: list[Screen],
) -> tuple[list[AiInteractionField], list[AiScreenInteractions], int]:
    per_screen: list[tuple[Screen, list[ScreenField]]] = []
    field_screen_count: Counter[str] = Counter()

    for screen in screens:
        fields = filter_interaction_fields(screen.fields)
        if fields:
            per_screen.append((screen, fields))
            for field in fields:
                field_screen_count[field.name] += 1

    screen_count = len(per_screen)
    threshold = max(
        _GLOBAL_CHROME_MIN_SCREENS,
        int(screen_count * _GLOBAL_CHROME_RATIO),
    )
    layout_names = {
        name for name, count in field_screen_count.items() if count >= threshold
    }

    layout_fields: list[AiInteractionField] = []
    layout_seen: set[str] = set()
    for _screen, fields in per_screen:
        for field in fields:
            if field.name in layout_names and field.name not in layout_seen:
                layout_fields.append(_field_to_ai(field))
                layout_seen.add(field.name)
    layout_fields.sort(key=lambda field: field.name)

    interactions: list[AiScreenInteractions] = []
    unique_names: set[str] = set()
    interaction_count = 0
    for screen, fields in per_screen:
        page_fields = [_field_to_ai(field) for field in fields if field.name not in layout_names]
        if not page_fields:
            continue
        kind = classify_route_path(screen.path)
        interactions.append(
            AiScreenInteractions(
                screen_id=screen.id,
                path=screen.path,
                name=screen.name,
                kind=kind,
                fields=page_fields,
            )
        )
        interaction_count += len(page_fields)
        unique_names.update(field.name for field in page_fields)
    unique_names.update(field.name for field in layout_fields)

    return layout_fields, interactions, len(unique_names)


def _normalize_flow_step(step: str) -> str:
    opened = step.strip()
    if opened.lower().startswith("opened "):
        url = opened[7:].strip()
        path = urlparse(url).path or "/"
        return f"Open `{path}`"

    href_match = re.search(r"href=(https?://[^\s)]+)", step)
    if href_match:
        path = urlparse(href_match.group(1)).path or "/"
        return f"Navigate to `{path}`"

    url_match = re.search(r"=(https?://[^\s)]+)", step)
    if url_match:
        path = urlparse(url_match.group(1)).path or "/"
        return f"Navigate to `{path}`"

    screen_match = re.search(r"^\[(/[^\]]*)\]", step)
    if screen_match:
        return f"On `{screen_match.group(1)}`"

    if len(step) > 120:
        return step[:117] + "..."
    return step


def _entity_fields_for_ai(entity: DomainEntity) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for ref in entity.fields:
        if ref.field in seen:
            continue
        if ref.field == "a" or ref.field.startswith("a[href"):
            continue
        if is_export_noise(ScreenField(name=ref.field, label=ref.label)):
            continue
        seen.add(ref.field)
        label = f" ({ref.label})" if ref.label else ""
        lines.append(f"  - `{ref.field}`{label}")
    for rule_name in entity.rule_names[:5]:
        if rule_name.startswith("login shows a"):
            continue
        lines.append(f"  - rule: {rule_name}")
    return lines


def format_ai_spec_markdown(
    spec: AiSpec,
    *,
    goal: str | None = None,
    status: str | None = None,
    entities: list[DomainEntity] | None = None,
) -> str:
    lines = [
        "# WebTwin AI context",
        "",
        f"- Investigation: `{spec.investigation_id}`",
    ]
    if goal:
        lines.append(f"- Goal: {goal}")
    if status:
        lines.append(f"- Status: {status}")
    lines.extend(
        [
            f"- Target: {spec.application.target_url}",
            f"- Application: `{spec.application.key or 'unknown'}`",
            f"- Screens: {spec.summary.screen_count}",
            f"- Global layout fields: {spec.summary.layout_field_count}",
            f"- Page-specific fields: {spec.summary.interaction_field_count}",
            f"- Unique fields total: {spec.summary.unique_interaction_field_count}",
            f"- Link coverage: {round(spec.summary.link_coverage_pct * 100)}%",
            f"- Verified rules: {spec.summary.verified_rule_count}",
            f"- Candidate rules: {spec.summary.candidate_rule_count} (sample below if any)",
            f"- Absences (assert_never): {spec.summary.absence_count}",
        ]
    )
    if spec.summary.candidate_rule_count > 0 and spec.summary.verified_rule_count == 0:
        lines.append(
            "- _E-commerce/catalog site: ignore navigation-noise candidates; "
            "use routes + interactions._"
        )
    lines.append("")

    if entities:
        lines.extend(["## Domain entities"])
        for entity in entities:
            screens = _format_screen_patterns(entity.screen_ids)
            field_lines = _entity_fields_for_ai(entity)
            lines.append(
                f"- **{entity.name}** (confidence={entity.confidence:.2f}) — screens: {screens}"
            )
            if field_lines:
                lines.extend(field_lines)
            else:
                lines.append("  - _No form controls mapped yet._")
        lines.append("")

    if spec.layout:
        lines.extend(["## Global layout (shared chrome)"])
        for field in spec.layout:
            lines.append(_format_field_line(field))
        lines.append("")

    lines.append("## Routes")
    collapsed_routes = _collapse_routes([route for group in spec.route_groups for route in group.routes])
    current_kind: str | None = None
    for route in collapsed_routes:
        if route.kind != current_kind:
            current_kind = route.kind
            lines.append(f"### {_ROUTE_GROUP_LABELS.get(current_kind, current_kind)}")
        entity = f" · entity `{route.primary_entity}`" if route.primary_entity else ""
        count = f" (×{route.instance_count})" if route.instance_count > 1 else ""
        lines.append(f"- `{route.pattern}` — {route.name}{entity}{count}")
        if route.instance_count > 1 and route.examples:
            examples = ", ".join(f"`{path}`" for path in route.examples)
            lines.append(f"  - _Examples: {examples}_")
    lines.append("")

    lines.extend(["## Page-specific interactions"])
    if not spec.interactions:
        lines.append("_No page-specific form controls beyond global layout._")
    collapsed = _collapse_interactions(spec.interactions)
    current_kind = None
    for screen in collapsed:
        if screen.kind != current_kind:
            current_kind = screen.kind
            lines.append(f"### {_ROUTE_GROUP_LABELS.get(current_kind, current_kind)}")
        count = f" (×{screen.instance_count})" if screen.instance_count > 1 else ""
        lines.append(f"#### `{screen.pattern}` — {screen.name}{count}")
        if screen.instance_count > 1 and screen.examples:
            examples = ", ".join(f"`{path}`" for path in screen.examples)
            lines.append(f"_Examples: {examples}_")
        for field in screen.fields:
            lines.append(_format_field_line(field))

    lines.extend(["", "## Navigation (compact)"])
    if not spec.navigation:
        lines.append("_No internal links mapped yet._")
    else:
        for edge in spec.navigation[:40]:
            visit = "visited" if edge.visited else "unvisited"
            target = edge.to_screen_id or edge.href
            lines.append(f"- `{edge.from_screen_id}` → `{target}` ({visit})")
        if len(spec.navigation) > 40:
            lines.append(f"- … and {len(spec.navigation) - 40} more edges in JSON")

    lines.extend(["", "## Verified behavior"])
    if not spec.verified_rules:
        lines.append("_None verified — prefer routes and interactions for now._")
    for rule in spec.verified_rules:
        lines.append(
            f"- **{rule.name}**: IF `{rule.condition_field}` {rule.condition_operator} "
            f"`{rule.condition_value}` THEN `{rule.effect_field}` "
            f"visible={rule.effect_visible} required={rule.effect_required}"
        )

    lines.extend(["", "## Negative space (assert_never)"])
    if not spec.absences:
        lines.append("_No proven absences yet._")
    for absence in spec.absences:
        lines.append(
            f"- when `{absence.condition_field}` {absence.condition_operator} "
            f"`{absence.condition_value}` → never `{absence.effect_field}."
            f"{absence.assert_attribute}={not absence.assert_value}`"
        )

    if spec.candidate_rules:
        lines.extend(["", "## Candidate behavior (unverified — hypotheses only)"])
        for rule in spec.candidate_rules[:15]:
            lines.append(
                f"- {rule.name} (confidence={rule.confidence}): "
                f"IF `{rule.condition_field}` {rule.condition_operator} `{rule.condition_value}` "
                f"THEN `{rule.effect_field}`"
            )
        if len(spec.candidate_rules) > 15:
            lines.append(f"- … {len(spec.candidate_rules) - 15} more in JSON")

    if spec.flows:
        lines.extend(["", "## Observed flows"])
        for flow in spec.flows:
            lines.append(f"- **{flow.name}**")
            for step in flow.steps[:8]:
                lines.append(f"  - {_normalize_flow_step(step)}")

    if spec.api_hints:
        lines.extend(["", "## API hints"])
        for hint in spec.api_hints[:10]:
            lines.append(f"- {hint.method or 'GET'} {hint.url or '—'}")

    lines.extend(["", "## Guidance"])
    for item in spec.guidance:
        lines.append(f"- {item}")

    return "\n".join(lines)


def build_ai_spec(
    investigation: Investigation,
    reference: ReferenceSystemContext,
    rules: list[BusinessRule],
    *,
    network_events: list[dict[str, Any]] | None = None,
    unknown_fields: list[tuple[str | None, str]] | None = None,
    max_candidate_rules: int = 20,
    max_unknowns: int = 30,
    max_nav_edges: int = 150,
) -> AiSpec:
    verified = [_rule_to_spec(rule, reference) for rule in rules if rule.status.value == "verified"]
    candidates = sorted(
        [_rule_to_spec(rule, reference) for rule in rules if rule.status.value == "candidate"],
        key=lambda rule: (-rule.confidence, rule.name),
    )[:max_candidate_rules]

    from webtwin_core.negative_space import derive_absences_from_rules
    from webtwin_core.privacy import redact_mapping

    absences = [
        CloneAbsenceSpec(
            id=item.id,
            condition_field=item.condition_field,
            condition_operator=item.condition_operator,
            condition_value=item.condition_value,
            effect_field=item.effect_field,
            assert_attribute=item.assert_attribute,
            assert_value=item.assert_value,
            source_rule_id=item.source_rule_id,
            confidence=item.confidence,
            evidence_ids=item.evidence_ids,
            rationale=item.rationale,
            test_scenario=item.test_scenario,
            setup_fields=redact_mapping(item.setup_fields),
        )
        for item in derive_absences_from_rules(rules)
    ]

    routes = [
        AiRouteSpec(
            id=screen.id,
            name=screen.name,
            path=screen.path,
            url=screen.url,
            role_scope=screen.role_scope,
            primary_entity=screen.primary_entity,
            kind=classify_route_path(screen.path),
        )
        for screen in reference.screens
    ]
    route_groups = _group_routes(routes)

    layout, interactions, unique_count = _extract_layout_and_interactions(reference.screens)
    page_field_count = sum(len(screen.fields) for screen in interactions)

    navigation = _compact_navigation(reference.discovered_links, max_edges=max_nav_edges)

    api_hints: list[CloneApiHint] = []
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
        for screen_id, field in (unknown_fields or [])[:max_unknowns]
    ]

    roles = sorted(reference.related_roles or [])
    if reference.role_scope and reference.role_scope not in roles:
        roles.append(reference.role_scope)

    stats = reference.site_graph_stats or {}
    summary = AiSpecSummary(
        screen_count=len(routes),
        layout_field_count=len(layout),
        interaction_field_count=page_field_count,
        unique_interaction_field_count=unique_count,
        navigation_edge_count=len(navigation),
        verified_rule_count=len(verified),
        candidate_rule_count=sum(1 for rule in rules if rule.status.value == "candidate"),
        absence_count=len(absences),
        link_coverage_pct=float(stats.get("coverage_pct", 0.0)),
        exploration_coverage=float(reference.exploration_coverage or 0.0),
    )

    guidance = [
        "Implement verified rules exactly; treat candidates as hypotheses only.",
        "Honor negative-space absences (assert_never) — do not invent excluded UI.",
        "Global layout fields appear once — reuse across all pages.",
        "Use route groups for site structure; page-specific interactions for unique forms.",
        "Domain entity names are inferred from form tokens — validate against your OpenAPI/models.",
        "API hints exclude Vite/webpack dev assets; real backend routes may need deeper crawl or OpenAPI.",
        "Do not invent API contracts or role permissions not listed here.",
        "Match behavior and field logic, not pixel-perfect visual design.",
    ]

    spec = AiSpec(
        investigation_id=str(investigation.id),
        application=CloneApplicationSpec(
            key=reference.application_key,
            name=reference.application_name,
            target_url=investigation.target_url,
            roles=roles,
        ),
        summary=summary,
        markdown="",
        layout=layout,
        routes=routes,
        route_groups=route_groups,
        interactions=interactions,
        navigation=navigation,
        verified_rules=verified,
        candidate_rules=candidates,
        absences=absences,
        flows=[
            CloneFlowSpec(
                name=flow.name,
                role_scope=flow.role_scope,
                entity_names=flow.entity_names,
                steps=[_normalize_flow_step(step.description) for step in flow.steps],
            )
            for flow in reference.flows
        ],
        api_hints=api_hints,
        unknowns=unknowns,
        guidance=guidance,
    )
    spec.markdown = format_ai_spec_markdown(
        spec,
        goal=investigation.goal,
        status=investigation.status.value,
        entities=reference.entities,
    )
    return spec
