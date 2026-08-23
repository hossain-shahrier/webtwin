"""Cross-investigation application catalog: entities + role-partitioned maps."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from typing import Any

from pydantic import BaseModel, Field

from webtwin_core.reference_system.entities import DomainEntity, EntityFieldRef, merge_entity_maps
from webtwin_core.reference_system.identity import normalize_role_scope


class RoleSystemMap(BaseModel):
    """Reference-system slice for one persona / role."""

    role_scope: str
    screen_count: int = 0
    entity_names: list[str] = Field(default_factory=list)
    flow_names: list[str] = Field(default_factory=list)
    navigation_count: int = 0
    verified_rule_names: list[str] = Field(default_factory=list)
    candidate_rule_names: list[str] = Field(default_factory=list)
    investigation_ids: list[UUID] = Field(default_factory=list)
    summary: str = ""


class ApplicationCatalog(BaseModel):
    """Merged knowledge for one application across roles and runs."""

    application_key: str
    application_name: str | None = None
    target_hosts: list[str] = Field(default_factory=list)
    entities: list[DomainEntity] = Field(default_factory=list)
    roles: dict[str, RoleSystemMap] = Field(default_factory=dict)
    investigation_ids: list[UUID] = Field(default_factory=list)
    discovered_links: list[Any] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def merge_domain_entities(
    existing: list[DomainEntity],
    incoming: list[DomainEntity],
) -> list[DomainEntity]:
    maps = []
    for entity in existing + incoming:
        grouped = {
            entity.name: [
                EntityFieldRef(field=ref.field, label=ref.label, screen_id=ref.screen_id)
                for ref in entity.fields
            ]
            or [EntityFieldRef(field=entity.name, label=None, screen_id=None)]
        }
        # preserve rule names via a side channel after merge
        maps.append(grouped)

    merged = merge_entity_maps(maps)
    rules_by_entity: dict[str, list[str]] = {}
    confidence_by_entity: dict[str, float] = {}
    for entity in existing + incoming:
        rules_by_entity.setdefault(entity.name, []).extend(entity.rule_names)
        confidence_by_entity[entity.name] = max(
            confidence_by_entity.get(entity.name, 0.0),
            entity.confidence,
        )
    for entity in merged:
        entity.rule_names = sorted(set(rules_by_entity.get(entity.name, [])))[:30]
        entity.confidence = max(entity.confidence, confidence_by_entity.get(entity.name, 0.0))
    return merged


def merge_role_map(existing: RoleSystemMap | None, incoming: RoleSystemMap) -> RoleSystemMap:
    if existing is None:
        return incoming.model_copy(deep=True)

    inv_ids = list(existing.investigation_ids)
    for item in incoming.investigation_ids:
        if item not in inv_ids:
            inv_ids.append(item)

    def _union(left: list[str], right: list[str], limit: int = 40) -> list[str]:
        seen: list[str] = []
        for name in left + right:
            if name not in seen:
                seen.append(name)
        return seen[:limit]

    return RoleSystemMap(
        role_scope=incoming.role_scope,
        screen_count=max(existing.screen_count, incoming.screen_count),
        entity_names=_union(existing.entity_names, incoming.entity_names),
        flow_names=_union(existing.flow_names, incoming.flow_names),
        navigation_count=max(existing.navigation_count, incoming.navigation_count),
        verified_rule_names=_union(existing.verified_rule_names, incoming.verified_rule_names),
        candidate_rule_names=_union(existing.candidate_rule_names, incoming.candidate_rule_names),
        investigation_ids=inv_ids,
        summary=incoming.summary or existing.summary,
    )


def role_map_from_context(
    *,
    role_scope: str | None,
    investigation_id: UUID,
    entity_names: list[str],
    flow_names: list[str],
    screen_count: int,
    navigation_count: int,
    verified_rule_names: list[str],
    candidate_rule_names: list[str],
    summary: str,
) -> RoleSystemMap:
    role = normalize_role_scope(role_scope)
    return RoleSystemMap(
        role_scope=role,
        screen_count=screen_count,
        entity_names=entity_names,
        flow_names=flow_names,
        navigation_count=navigation_count,
        verified_rule_names=verified_rule_names,
        candidate_rule_names=candidate_rule_names,
        investigation_ids=[investigation_id],
        summary=summary,
    )


def upsert_catalog_from_run(
    catalog: ApplicationCatalog | None,
    *,
    application_key: str,
    application_name: str | None,
    host: str,
    investigation_id: UUID,
    entities: list[DomainEntity],
    role_map: RoleSystemMap,
    discovered_links: list[Any] | None = None,
) -> ApplicationCatalog:
    if catalog is None:
        catalog = ApplicationCatalog(
            application_key=application_key,
            application_name=application_name,
        )

    if application_name and not catalog.application_name:
        catalog.application_name = application_name
    if host and host not in catalog.target_hosts:
        catalog.target_hosts.append(host)
    if investigation_id not in catalog.investigation_ids:
        catalog.investigation_ids.append(investigation_id)

    catalog.entities = merge_domain_entities(catalog.entities, entities)
    if discovered_links:
        from webtwin_core.reference_system.site_graph import merge_discovered_links

        catalog.discovered_links = merge_discovered_links(
            catalog.discovered_links,
            discovered_links,
        )
    role = normalize_role_scope(role_map.role_scope)
    role_map.role_scope = role
    catalog.roles[role] = merge_role_map(catalog.roles.get(role), role_map)
    catalog.updated_at = datetime.now(UTC)
    return catalog
