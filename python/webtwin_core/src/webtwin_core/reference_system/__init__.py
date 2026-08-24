"""Synthesize a reference-system view from investigation artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    Investigation,
    Observation,
    TimelineEvent,
    TimelineEventType,
    Workflow,
)
from webtwin_core.reference_system.catalog import (
    ApplicationCatalog,
    RoleSystemMap,
    role_map_from_context,
)
from webtwin_core.reference_system.entities import (
    DomainEntity,
    EntityFieldRef,
    attach_rules_to_entities,
    match_entity_from_route,
    match_entity_name,
    merge_entity_maps,
)
from webtwin_core.reference_system.identity import application_key_for, normalize_role_scope


class ScreenField(BaseModel):
    name: str
    label: str | None = None
    input_type: str | None = None
    required: bool = False
    visible: bool = True
    selector: str | None = None
    entity: str | None = None


class Screen(BaseModel):
    id: str
    name: str
    url: str
    path: str = "/"
    visit_count: int = 0
    form_count: int = 0
    field_count: int = 0
    fields: list[ScreenField] = Field(default_factory=list)
    observation_ids: list[UUID] = Field(default_factory=list)
    framework_hints: dict[str, Any] = Field(default_factory=dict)
    entity_names: list[str] = Field(default_factory=list)
    primary_entity: str | None = None
    role_scope: str | None = None


class NavigationEdge(BaseModel):
    from_screen_id: str
    to_screen_id: str
    trigger: str
    event_type: str
    occurred_at: datetime | None = None
    role_scope: str | None = None
    href: str | None = None
    selector: str | None = None
    visited: bool = True


class SystemFlowStep(BaseModel):
    order: int
    description: str
    screen_id: str | None = None
    action_id: str | None = None


class SystemFlow(BaseModel):
    name: str
    steps: list[SystemFlowStep] = Field(default_factory=list)
    screen_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    role_scope: str | None = None


class ScreenRules(BaseModel):
    screen_id: str
    verified: list[str] = Field(default_factory=list)
    candidate: list[str] = Field(default_factory=list)
    under_verification: list[str] = Field(default_factory=list)
    contradicted: list[str] = Field(default_factory=list)


class ReferenceSystemContext(BaseModel):
    investigation_id: UUID
    application_name: str | None = None
    application_key: str | None = None
    target_url: str
    role_scope: str | None = None
    environment: str | None = None
    application_version: str | None = None
    feature_scope: str | None = None
    framework_hints: dict[str, Any] = Field(default_factory=dict)
    entities: list[DomainEntity] = Field(default_factory=list)
    screens: list[Screen] = Field(default_factory=list)
    navigation: list[NavigationEdge] = Field(default_factory=list)
    flows: list[SystemFlow] = Field(default_factory=list)
    rules_by_screen: list[ScreenRules] = Field(default_factory=list)
    role_map: RoleSystemMap | None = None
    catalog: ApplicationCatalog | None = None
    related_roles: list[str] = Field(default_factory=list)
    exploration_coverage: float = 0.0
    unexplored_fields: list[str] = Field(default_factory=list)
    discovered_links: list[Any] = Field(default_factory=list)  # DiscoveredLink — lazy import
    site_graph_stats: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


_ACTION_EVENT_TYPES = {
    TimelineEventType.NAVIGATE,
    TimelineEventType.CLICK,
    TimelineEventType.INPUT,
    TimelineEventType.SELECT,
    TimelineEventType.SUBMIT,
    TimelineEventType.ROUTE,
    TimelineEventType.SCROLL,
}


def screen_key_from_observation(observation: Observation) -> str:
    from webtwin_core.reference_system.site_graph import screen_id_from_url

    if observation.route:
        path = observation.route.path or "/"
        fragment = observation.route.hash or ""
        if fragment and not fragment.startswith("#"):
            fragment = f"#{fragment}"
        return f"{path}{fragment}" if fragment else path
    return screen_id_from_url(observation.url)


def screen_name_from_observation(observation: Observation) -> str:
    if observation.route and observation.route.title:
        return observation.route.title
    if observation.title:
        return observation.title
    key = screen_key_from_observation(observation)
    return key if key != "/" else observation.url


def _merge_field(existing: ScreenField, incoming: ScreenField) -> ScreenField:
    return ScreenField(
        name=existing.name,
        label=existing.label or incoming.label,
        input_type=existing.input_type or incoming.input_type,
        required=existing.required or incoming.required,
        visible=incoming.visible if incoming.visible is False else existing.visible,
        selector=existing.selector or incoming.selector,
        entity=existing.entity or incoming.entity,
    )


def _fields_from_observation(observation: Observation) -> list[ScreenField]:
    form_name_by_field: dict[str, str | None] = {}
    for form in observation.forms:
        for element in form.fields:
            key = element.stable_key or element.name or element.selector
            if key:
                form_name_by_field[key] = form.name

    fields: dict[str, ScreenField] = {}
    for element in observation.elements:
        name = element.stable_key or element.name or element.selector
        if not name:
            continue
        form_name = form_name_by_field.get(name)
        route_path = observation.route.path if observation.route else None
        entity = match_entity_name(
            name,
            element.label,
            form_name,
            observation.title,
            route_path=route_path,
        )
        incoming = ScreenField(
            name=name,
            label=element.label,
            input_type=element.input_type,
            required=element.required,
            visible=element.visible,
            selector=element.selector,
            entity=entity,
        )
        if name in fields:
            fields[name] = _merge_field(fields[name], incoming)
        else:
            fields[name] = incoming
    return list(fields.values())


def _enrich_screen_entities(screen: Screen) -> None:
    route_entity = match_entity_from_route(screen.path)
    counts: dict[str, int] = {}
    for field in screen.fields:
        if route_entity:
            field.entity = route_entity
        elif not field.entity:
            field.entity = match_entity_name(field.name, field.label, route_path=screen.path)
        entity = field.entity
        if entity:
            counts[entity] = counts.get(entity, 0) + 1
    path_entity = route_entity or match_entity_name(screen.path, screen.name, screen.url, route_path=screen.path)
    if path_entity:
        counts[path_entity] = counts.get(path_entity, 0) + 2
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    screen.entity_names = [name for name, _ in ranked]
    screen.primary_entity = ranked[0][0] if ranked else None
    if screen.primary_entity and screen.name in {screen.id, screen.path, screen.url}:
        screen.name = f"{screen.primary_entity} — {screen.path}"
    elif screen.primary_entity and screen.primary_entity.lower() not in screen.name.lower():
        # keep human title but annotate when generic
        if len(screen.name) < 4 or screen.name.lower() in {"home", "index", "app", "page"}:
            screen.name = f"{screen.primary_entity} ({screen.name})"


def _state_url_lookup(states: list[ApplicationState]) -> dict[UUID, str]:
    lookup: dict[UUID, str] = {}
    for state in states:
        if state.url:
            lookup[state.id] = state.url
    return lookup


def _screen_id_from_url(url: str) -> str:
    from webtwin_core.reference_system.site_graph import screen_id_from_url

    return screen_id_from_url(url)


def build_screens(observations: list[Observation]) -> list[Screen]:
    grouped: dict[str, Screen] = {}
    for observation in sorted(observations, key=lambda item: item.captured_at):
        key = screen_key_from_observation(observation)
        if key not in grouped:
            grouped[key] = Screen(
                id=key,
                name=screen_name_from_observation(observation),
                url=observation.url,
                path=key,
            )
        screen = grouped[key]
        screen.visit_count += 1
        screen.observation_ids.append(observation.id)
        screen.form_count = max(screen.form_count, len(observation.forms))
        if observation.framework_hints:
            screen.framework_hints.update(observation.framework_hints)

        field_map = {field.name: field for field in screen.fields}
        for incoming in _fields_from_observation(observation):
            if incoming.name in field_map:
                field_map[incoming.name] = _merge_field(field_map[incoming.name], incoming)
            else:
                field_map[incoming.name] = incoming
        screen.fields = sorted(field_map.values(), key=lambda item: item.name)
        screen.field_count = len(screen.fields)
        if observation.title and screen.name in {key, observation.url}:
            screen.name = observation.title

    screens = list(grouped.values())
    for screen in screens:
        _enrich_screen_entities(screen)
    return sorted(screens, key=lambda item: (-item.visit_count, item.name))


def build_navigation(
    events: list[TimelineEvent],
    states: list[ApplicationState],
    observations: list[Observation],
) -> list[NavigationEdge]:
    state_urls = _state_url_lookup(states)
    obs_by_state: dict[UUID, str] = {}
    sorted_states = sorted(states, key=lambda item: item.sequence)
    for index, state in enumerate(sorted_states):
        if state.url:
            obs_by_state[state.id] = _screen_id_from_url(state.url)

    edges: list[NavigationEdge] = []
    seen: set[tuple[str, str, str]] = set()

    for event in sorted(events, key=lambda item: item.occurred_at):
        if event.type not in {TimelineEventType.NAVIGATE, TimelineEventType.ROUTE}:
            continue
        before_url = state_urls.get(event.state_before_id) if event.state_before_id else None
        after_url = state_urls.get(event.state_after_id) if event.state_after_id else None
        if not before_url or not after_url:
            continue
        from_id = _screen_id_from_url(before_url)
        to_id = _screen_id_from_url(after_url)
        if from_id == to_id:
            continue
        signature = (from_id, to_id, event.description)
        if signature in seen:
            continue
        seen.add(signature)
        href = None
        if " href=" in event.description:
            href = event.description.split(" href=", 1)[1].split(" ", 1)[0]
        edges.append(
            NavigationEdge(
                from_screen_id=from_id,
                to_screen_id=to_id,
                trigger=event.description,
                event_type=event.type.value,
                occurred_at=event.occurred_at,
                href=href,
                visited=True,
            )
        )

    if edges:
        return edges

    # Fallback: infer edges from observation URL sequence when timeline lacks state links.
    prev_key: str | None = None
    for observation in sorted(observations, key=lambda item: item.captured_at):
        key = screen_key_from_observation(observation)
        if prev_key and key != prev_key:
            signature = (prev_key, key, f"visited {key}")
            if signature not in seen:
                seen.add(signature)
                edges.append(
                    NavigationEdge(
                        from_screen_id=prev_key,
                        to_screen_id=key,
                        trigger=f"Navigation to {key}",
                        event_type="observed",
                    )
                )
        prev_key = key
    return edges


def build_flows_from_timeline(
    events: list[TimelineEvent],
    states: list[ApplicationState],
    screens: list[Screen] | None = None,
) -> list[SystemFlow]:
    state_urls = _state_url_lookup(states)
    steps: list[SystemFlowStep] = []
    screen_ids: list[str] = []
    entity_by_screen = {
        screen.id: screen.entity_names for screen in (screens or [])
    }

    for event in sorted(events, key=lambda item: item.occurred_at):
        if event.type not in _ACTION_EVENT_TYPES:
            continue
        screen_id: str | None = None
        url = state_urls.get(event.state_after_id) if event.state_after_id else None
        if url:
            screen_id = _screen_id_from_url(url)
            if not screen_ids or screen_ids[-1] != screen_id:
                screen_ids.append(screen_id)
        steps.append(
            SystemFlowStep(
                order=len(steps),
                description=event.description,
                screen_id=screen_id,
                action_id=str(event.id),
            )
        )

    if len(steps) < 2:
        return []

    entity_names: list[str] = []
    for screen_id in screen_ids:
        for name in entity_by_screen.get(screen_id, []):
            if name not in entity_names:
                entity_names.append(name)
    # also sniff step text
    for step in steps:
        matched = match_entity_name(step.description)
        if matched and matched not in entity_names:
            entity_names.append(matched)

    if entity_names:
        flow_name = f"{' → '.join(entity_names[:3])} flow ({len(steps)} actions)"
    else:
        flow_name = f"Exploration path ({len(steps)} actions)"

    return [
        SystemFlow(
            name=flow_name,
            steps=steps[:40],
            screen_ids=screen_ids,
            entity_names=entity_names,
            confidence=0.65 if entity_names else (0.6 if len(steps) >= 4 else 0.4),
        )
    ]


def build_flows_from_workflows(
    workflows: list[Workflow],
    screens: list[Screen] | None = None,
) -> list[SystemFlow]:
    entity_by_screen = {screen.id: screen.entity_names for screen in (screens or [])}
    flows: list[SystemFlow] = []
    for workflow in workflows:
        entity_names: list[str] = []
        for step in workflow.steps:
            matched = match_entity_name(step.description)
            if matched and matched not in entity_names:
                entity_names.append(matched)
        for screen_id, names in entity_by_screen.items():
            if any(screen_id in (step.description or "") for step in workflow.steps):
                for name in names:
                    if name not in entity_names:
                        entity_names.append(name)
        name = workflow.name
        if entity_names and "flow" not in name.lower():
            name = f"{entity_names[0]} — {workflow.name}"
        flows.append(
            SystemFlow(
                name=name,
                steps=[
                    SystemFlowStep(order=step.order, description=step.description)
                    for step in workflow.steps
                ],
                entity_names=entity_names,
                confidence=workflow.confidence,
            )
        )
    return flows


def build_domain_entities(
    screens: list[Screen],
    rules: list[BusinessRule],
) -> list[DomainEntity]:
    maps: list[dict[str, list[EntityFieldRef]]] = []
    for screen in screens:
        grouped: dict[str, list[EntityFieldRef]] = {}
        for field in screen.fields:
            entity = field.entity or match_entity_name(field.name, field.label)
            if not entity:
                continue
            grouped.setdefault(entity, []).append(
                EntityFieldRef(field=field.name, label=field.label, screen_id=screen.id)
            )
        if screen.primary_entity and screen.primary_entity not in grouped:
            grouped[screen.primary_entity] = [
                EntityFieldRef(field=screen.path, label=screen.name, screen_id=screen.id)
            ]
        if grouped:
            maps.append(grouped)

    entities = merge_entity_maps(maps)
    rule_names_by_field: dict[str, list[str]] = {}
    for rule in rules:
        label = rule.name or f"{rule.condition.field} → {rule.effect.field}"
        for key in (rule.condition.field, rule.effect.field):
            rule_names_by_field.setdefault(key.lower(), []).append(label)
    return attach_rules_to_entities(entities, rule_names_by_field)


def map_rules_to_screens(rules: list[BusinessRule], screens: list[Screen]) -> list[ScreenRules]:
    screen_fields: dict[str, set[str]] = {}
    for screen in screens:
        names: set[str] = set()
        for field in screen.fields:
            names.add(field.name.lower())
            if field.label:
                names.add(field.label.lower())
        screen_fields[screen.id] = names

    mapped: dict[str, ScreenRules] = {
        screen.id: ScreenRules(screen_id=screen.id) for screen in screens
    }
    unmatched_verified: list[str] = []
    unmatched_candidate: list[str] = []
    unmatched_under_verification: list[str] = []
    unmatched_contradicted: list[str] = []

    for rule in rules:
        haystack = {
            rule.condition.field.lower(),
            rule.effect.field.lower(),
            (rule.name or "").lower(),
        }
        matched = False
        label = rule.name or f"{rule.condition.field} → {rule.effect.field}"
        for screen_id, names in screen_fields.items():
            if haystack & names:
                bucket = mapped[screen_id]
                if rule.status.value == "verified":
                    bucket.verified.append(label)
                elif rule.status.value == "contradicted":
                    bucket.contradicted.append(label)
                elif rule.status.value == "under_verification":
                    bucket.under_verification.append(label)
                else:
                    bucket.candidate.append(label)
                matched = True
        if not matched:
            if rule.status.value == "verified":
                unmatched_verified.append(label)
            elif rule.status.value == "contradicted":
                unmatched_contradicted.append(label)
            elif rule.status.value == "under_verification":
                unmatched_under_verification.append(label)
            else:
                unmatched_candidate.append(label)

    result = [
        item
        for item in mapped.values()
        if item.verified or item.candidate or item.under_verification or item.contradicted
    ]
    if (
        unmatched_verified
        or unmatched_candidate
        or unmatched_under_verification
        or unmatched_contradicted
    ):
        result.append(
            ScreenRules(
                screen_id="_unscoped",
                verified=unmatched_verified,
                candidate=unmatched_candidate,
                under_verification=unmatched_under_verification,
                contradicted=unmatched_contradicted,
            )
        )
    return result


def _collect_framework_hints(screens: list[Screen]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for screen in screens:
        merged.update(screen.framework_hints)
    return merged


def _compute_unexplored_fields(screens: list[Screen], rules: list[BusinessRule]) -> list[str]:
    referenced = set()
    for rule in rules:
        referenced.add(rule.condition.field.lower())
        referenced.add(rule.effect.field.lower())
    unknown: list[str] = []
    for screen in screens:
        for field in screen.fields:
            if field.name.lower() not in referenced:
                unknown.append(f"{screen.id}:{field.name}")
    return unknown[:40]


def build_reference_system_context(
    investigation: Investigation,
    *,
    observations: list[Observation],
    events: list[TimelineEvent],
    rules: list[BusinessRule],
    workflows: list[Workflow] | None = None,
    states: list[ApplicationState] | None = None,
    catalog: ApplicationCatalog | None = None,
    exploration_coverage: float = 0.0,
    unexplored_fields: list[str] | None = None,
    discovered_links: list[Any] | None = None,
) -> ReferenceSystemContext:
    from webtwin_core.reference_system.site_graph import build_site_graph

    states = states or []
    workflows = workflows or []
    links = discovered_links or []
    role = normalize_role_scope(investigation.role_scope)
    app_key = investigation.application_key or application_key_for(
        investigation.target_url,
        application_name=investigation.application_name,
    )

    screens = build_screens(observations)
    for screen in screens:
        screen.role_scope = role
    navigation = build_navigation(events, states, observations)
    for edge in navigation:
        edge.role_scope = role
    timeline_flows = build_flows_from_timeline(events, states, screens)
    workflow_flows = build_flows_from_workflows(workflows, screens)
    flows = timeline_flows + workflow_flows
    for flow in flows:
        flow.role_scope = role
    rules_by_screen = map_rules_to_screens(rules, screens)
    entities = build_domain_entities(screens, rules)
    framework_hints = _collect_framework_hints(screens)
    unexplored = unexplored_fields if unexplored_fields is not None else _compute_unexplored_fields(screens, rules)
    site_graph = build_site_graph(
        screens,
        links,
        navigation,
        origin_url=investigation.target_url,
    )

    verified_rules = [rule for rule in rules if rule.status.value == "verified"]
    candidate_rules = [rule for rule in rules if rule.status.value == "candidate"]
    entity_label = ", ".join(entity.name for entity in entities[:4]) or "no domain entities"
    role_label = role if role != "default" else "default role"
    summary = (
        f"{investigation.application_name or 'Application'} ({app_key}) "
        f"as {role_label}: "
        f"{len(entities)} entit{'y' if len(entities) == 1 else 'ies'} ({entity_label}); "
        f"{len(screens)} screen(s), {len(navigation)} navigation edge(s), "
        f"{len(flows)} flow(s), {len(verified_rules)} verified and "
        f"{len(candidate_rules)} candidate rule(s)."
    )

    role_map = role_map_from_context(
        role_scope=role,
        investigation_id=investigation.id,
        entity_names=[entity.name for entity in entities],
        flow_names=[flow.name for flow in flows],
        screen_count=len(screens),
        navigation_count=len(navigation),
        verified_rule_names=[rule.name for rule in verified_rules],
        candidate_rule_names=[rule.name for rule in candidate_rules],
        summary=summary,
    )
    related_roles = sorted(catalog.roles.keys()) if catalog else [role]

    return ReferenceSystemContext(
        investigation_id=investigation.id,
        application_name=investigation.application_name,
        application_key=app_key,
        target_url=investigation.target_url,
        role_scope=role,
        environment=investigation.environment,
        application_version=investigation.application_version,
        feature_scope=investigation.feature_scope,
        framework_hints=framework_hints,
        entities=entities,
        screens=screens,
        navigation=navigation,
        flows=flows,
        rules_by_screen=rules_by_screen,
        role_map=role_map,
        catalog=catalog,
        related_roles=related_roles,
        exploration_coverage=exploration_coverage,
        unexplored_fields=unexplored,
        discovered_links=links,
        site_graph_stats=site_graph.stats.model_dump(mode="json"),
        summary=summary,
    )


def format_reference_system_markdown(context: ReferenceSystemContext) -> str:
    lines = [
        "## Reference system overview",
        "",
        context.summary,
        "",
    ]
    if (
        context.role_scope
        or context.feature_scope
        or context.environment
        or context.application_key
    ):
        lines.append("### Scope")
        if context.application_name:
            lines.append(f"- Application: **{context.application_name}**")
        if context.application_key:
            lines.append(f"- Application key: `{context.application_key}`")
        if context.role_scope:
            lines.append(f"- Role: `{context.role_scope}`")
        if context.related_roles:
            lines.append(f"- Known roles: {', '.join(f'`{r}`' for r in context.related_roles)}")
        if context.feature_scope:
            lines.append(f"- Feature scope: `{context.feature_scope}`")
        if context.environment:
            lines.append(f"- Environment: `{context.environment}`")
        if context.application_version:
            lines.append(f"- Version: `{context.application_version}`")
        lines.append("")

    if context.catalog and (
        len(context.catalog.roles) > 1 or len(context.catalog.investigation_ids) > 1
    ):
        lines.append("### Shared application catalog")
        lines.append(
            f"- Key `{context.catalog.application_key}` — "
            f"{len(context.catalog.entities)} merged entities, "
            f"{len(context.catalog.roles)} role map(s), "
            f"{len(context.catalog.investigation_ids)} investigation(s)"
        )
        for role_name, role_map in sorted(context.catalog.roles.items()):
            lines.append(
                f"- Role `{role_name}`: {role_map.screen_count} screens, "
                f"entities {', '.join(role_map.entity_names[:5]) or '—'}, "
                f"{len(role_map.verified_rule_names)} verified rules"
            )
        for entity in context.catalog.entities[:8]:
            lines.append(
                f"  - catalog entity **{entity.name}** ({entity.field_count} fields)"
            )
        lines.append("")

    if context.framework_hints:
        lines.append("### Technology signals")
        for key, value in sorted(context.framework_hints.items()):
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.append("### Domain entities")
    if not context.entities:
        lines.append("_No domain entities inferred yet._")
    for entity in context.entities:
        screens = ", ".join(f"`{sid}`" for sid in entity.screen_ids[:5]) or "—"
        lines.append(
            f"- **{entity.name}** (confidence={entity.confidence:.2f}, "
            f"{entity.field_count} fields) — screens: {screens}"
        )
        for ref in entity.fields[:8]:
            label = f" ({ref.label})" if ref.label else ""
            lines.append(f"  - `{ref.field}`{label}")
        for rule_name in entity.rule_names[:5]:
            lines.append(f"  - rule: {rule_name}")
    lines.append("")

    lines.append("### Screens")
    if not context.screens:
        lines.append("_No screens captured._")
    for screen in context.screens:
        entity_bit = (
            f" · entities: {', '.join(screen.entity_names)}" if screen.entity_names else ""
        )
        lines.append(
            f"- **{screen.name}** (`{screen.id}`) — "
            f"{screen.field_count} fields, visited {screen.visit_count}×{entity_bit}"
        )
        for field in screen.fields[:12]:
            label = f" ({field.label})" if field.label else ""
            entity = f" → {field.entity}" if field.entity else ""
            flags = []
            if field.required:
                flags.append("required")
            if not field.visible:
                flags.append("hidden")
            flag_text = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  - `{field.name}`{label}{entity}{flag_text}")
        if len(screen.fields) > 12:
            lines.append(f"  - … and {len(screen.fields) - 12} more fields")
    lines.append("")

    lines.append("### Navigation")
    if not context.navigation:
        lines.append("_No cross-screen navigation observed._")
    for edge in context.navigation[:20]:
        lines.append(f"- `{edge.from_screen_id}` → `{edge.to_screen_id}` via {edge.trigger}")
    lines.append("")

    lines.append("### Flows")
    if not context.flows:
        lines.append("_No multi-step flows recorded._")
    for flow in context.flows[:5]:
        entity_bit = (
            f" · entities: {', '.join(flow.entity_names)}" if flow.entity_names else ""
        )
        lines.append(f"- **{flow.name}** (confidence={flow.confidence}){entity_bit}")
        for step in flow.steps[:10]:
            prefix = f"[{step.screen_id}] " if step.screen_id else ""
            lines.append(f"  {step.order + 1}. {prefix}{step.description}")
    lines.append("")

    lines.append("### Logic by screen")
    if not context.rules_by_screen:
        lines.append("_No rules mapped to screens._")
    for group in context.rules_by_screen:
        title = "Unscoped rules" if group.screen_id == "_unscoped" else f"Screen `{group.screen_id}`"
        lines.append(f"- **{title}**")
        for name in group.verified[:8]:
            lines.append(f"  - verified: {name}")
        for name in group.candidate[:8]:
            lines.append(f"  - candidate: {name}")
        for name in group.contradicted[:8]:
            lines.append(f"  - contradicted: {name}")
    lines.append("")

    return "\n".join(lines)
