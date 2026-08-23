"""Neo4j knowledge graph sync — derived index from Postgres/memory store."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def kg_enabled() -> bool:
    return os.environ.get("WEBTWIN_KG_ENABLED", "").lower() in {"1", "true", "yes"}


def _driver():
    from neo4j import GraphDatabase  # type: ignore

    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "webtwin-neo4j")
    return GraphDatabase.driver(uri, auth=(user, password))


def sync_investigation_to_kg(
    *,
    investigation_id: UUID,
    application_name: str | None,
    target_url: str,
    rules: list[Any],
    evidence: list[Any],
    role_scope: str | None = None,
    application_version: str | None = None,
    environment: str | None = None,
    application_key: str | None = None,
    screens: list[Any] | None = None,
    entities: list[Any] | None = None,
    flows: list[Any] | None = None,
    discovered_links: list[Any] | None = None,
    navigation: list[Any] | None = None,
    rules_by_screen: list[Any] | None = None,
) -> dict[str, int]:
    """
    Idempotent upsert of Application/Page/Rule/Evidence nodes with evidence_id FKs.
    No-ops when WEBTWIN_KG_ENABLED is false or neo4j driver is unavailable.
    """
    if not kg_enabled():
        return {"nodes": 0, "edges": 0, "skipped": 1}

    try:
        driver = _driver()
    except ImportError:
        return {"nodes": 0, "edges": 0, "skipped": 1, "reason": "neo4j_driver_missing"}
    except Exception as error:
        logger.warning("Neo4j driver unavailable: %s", error)
        return {"nodes": 0, "edges": 0, "skipped": 1, "reason": str(error)}

    nodes = 0
    edges = 0
    app_id = application_key or str(investigation_id)
    links_synced: set[tuple[str, str, str | None]] = set()
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (a:Application {id: $id})
                SET a.name = $name,
                    a.target_url = $url,
                    a.role_scope = $role_scope,
                    a.application_version = $version,
                    a.environment = $environment,
                    a.investigation_id = $investigation_id
                """,
                id=app_id,
                name=application_name or "unknown",
                url=target_url,
                role_scope=role_scope,
                version=application_version,
                environment=environment,
                investigation_id=str(investigation_id),
            )
            nodes += 1

            page_items = screens or [{"id": "page", "url": target_url, "name": target_url}]
            for screen in page_items:
                screen_id = getattr(screen, "id", None) or (screen.get("id") if isinstance(screen, dict) else "page")
                screen_url = getattr(screen, "url", None) or (screen.get("url") if isinstance(screen, dict) else target_url)
                screen_name = getattr(screen, "name", None) or (screen.get("name") if isinstance(screen, dict) else screen_url)
                page_key = f"{investigation_id}:{screen_id}"
                session.run(
                    """
                    MERGE (p:Page {id: $page_id})
                    SET p.url = $url,
                        p.name = $name,
                        p.path = $path,
                        p.application_key = $app_id
                    WITH p
                    MATCH (a:Application {id: $app_id})
                    MERGE (a)-[:contains]->(p)
                    """,
                    page_id=page_key,
                    url=screen_url,
                    name=screen_name,
                    path=str(screen_id),
                    app_id=app_id,
                )
                nodes += 1
                edges += 1

            for entity in entities or []:
                entity_name = getattr(entity, "name", None) or (
                    entity.get("name") if isinstance(entity, dict) else None
                )
                if not entity_name:
                    continue
                session.run(
                    """
                    MERGE (e:Entity {name: $name, investigation_id: $app_id})
                    SET e.confidence = $confidence,
                        e.field_count = $field_count
                    WITH e
                    MATCH (a:Application {id: $app_id})
                    MERGE (a)-[:models]->(e)
                    """,
                    name=entity_name,
                    confidence=float(
                        getattr(entity, "confidence", None)
                        or (entity.get("confidence") if isinstance(entity, dict) else 0)
                        or 0
                    ),
                    field_count=int(
                        getattr(entity, "field_count", None)
                        or (entity.get("field_count") if isinstance(entity, dict) else 0)
                        or 0
                    ),
                    app_id=app_id,
                )
                nodes += 1
                edges += 1
                for screen_id in getattr(entity, "screen_ids", None) or (
                    entity.get("screen_ids") if isinstance(entity, dict) else []
                ):
                    session.run(
                        """
                        MATCH (e:Entity {name: $name, investigation_id: $app_id})
                        MATCH (p:Page {id: $page_id})
                        MERGE (e)-[:appears_on]->(p)
                        """,
                        name=entity_name,
                        app_id=app_id,
                        page_id=f"{investigation_id}:{screen_id}",
                    )
                    edges += 1

            for flow in flows or []:
                flow_name = getattr(flow, "name", None) or (
                    flow.get("name") if isinstance(flow, dict) else None
                )
                if not flow_name:
                    continue
                flow_id = f"{investigation_id}:flow:{flow_name[:80]}"
                session.run(
                    """
                    MERGE (f:Flow {id: $fid})
                    SET f.name = $name,
                        f.role_scope = $role
                    WITH f
                    MATCH (a:Application {id: $app_id})
                    MERGE (a)-[:contains]->(f)
                    """,
                    fid=flow_id,
                    name=flow_name,
                    role=getattr(flow, "role_scope", None)
                    or (flow.get("role_scope") if isinstance(flow, dict) else None),
                    app_id=app_id,
                )
                nodes += 1
                edges += 1
                for step in getattr(flow, "steps", None) or (
                    flow.get("steps") if isinstance(flow, dict) else []
                ):
                    screen_id = getattr(step, "screen_id", None) or (
                        step.get("screen_id") if isinstance(step, dict) else None
                    )
                    if not screen_id:
                        continue
                    session.run(
                        """
                        MATCH (f:Flow {id: $fid})
                        MATCH (p:Page {id: $page_id})
                        MERGE (f)-[:STEP_ON {order: $order}]->(p)
                        """,
                        fid=flow_id,
                        page_id=f"{investigation_id}:{screen_id}",
                        order=int(getattr(step, "order", None) or (step.get("order") if isinstance(step, dict) else 0)),
                    )
                    edges += 1

            for link in discovered_links or []:
                from_id = getattr(link, "from_screen_id", None) or (
                    link.get("from_screen_id") if isinstance(link, dict) else None
                )
                to_id = getattr(link, "to_screen_id", None) or (
                    link.get("to_screen_id") if isinstance(link, dict) else None
                )
                href = getattr(link, "href", None) or (
                    link.get("href") if isinstance(link, dict) else None
                )
                if not from_id or not to_id:
                    continue
                visited = bool(getattr(link, "visited", None) or (link.get("visited") if isinstance(link, dict) else False))
                selector = getattr(link, "selector", None) or (
                    link.get("selector") if isinstance(link, dict) else None
                )
                session.run(
                    """
                    MATCH (src:Page {id: $from_id})
                    MATCH (dst:Page {id: $to_id})
                    MERGE (src)-[r:LINKS_TO {href: $href}]->(dst)
                    SET r.selector = $selector,
                        r.visited = $visited,
                        r.trigger = $href
                    """,
                    from_id=f"{investigation_id}:{from_id}",
                    to_id=f"{investigation_id}:{to_id}",
                    href=href,
                    selector=selector,
                    visited=visited,
                )
                links_synced.add((from_id, to_id, href))
                edges += 1

            for edge in navigation or []:
                from_id = getattr(edge, "from_screen_id", None) or (
                    edge.get("from_screen_id") if isinstance(edge, dict) else None
                )
                to_id = getattr(edge, "to_screen_id", None) or (
                    edge.get("to_screen_id") if isinstance(edge, dict) else None
                )
                if not from_id or not to_id:
                    continue
                href = getattr(edge, "href", None) or (
                    edge.get("href") if isinstance(edge, dict) else None
                )
                trigger = getattr(edge, "trigger", None) or (
                    edge.get("trigger") if isinstance(edge, dict) else None
                )
                if (from_id, to_id, href) in links_synced or (from_id, to_id, trigger) in links_synced:
                    continue
                session.run(
                    """
                    MATCH (src:Page {id: $from_id})
                    MATCH (dst:Page {id: $to_id})
                    MERGE (src)-[r:LINKS_TO {href: coalesce($href, $trigger)}]->(dst)
                    SET r.visited = true,
                        r.trigger = $trigger,
                        r.selector = $selector
                    """,
                    from_id=f"{investigation_id}:{from_id}",
                    to_id=f"{investigation_id}:{to_id}",
                    href=href,
                    trigger=trigger,
                    selector=getattr(edge, "selector", None),
                )
                edges += 1

            for group in rules_by_screen or []:
                screen_id = getattr(group, "screen_id", None) or (
                    group.get("screen_id") if isinstance(group, dict) else None
                )
                if not screen_id or screen_id == "_unscoped":
                    continue
                rule_names = (
                    (getattr(group, "verified", None) or [])
                    + (getattr(group, "candidate", None) or [])
                    + (getattr(group, "contradicted", None) or [])
                )
                if isinstance(group, dict):
                    rule_names = (
                        (group.get("verified") or [])
                        + (group.get("candidate") or [])
                        + (group.get("contradicted") or [])
                    )
                for rule in rules:
                    rule_name = getattr(rule, "name", None) or (
                        rule.get("name") if isinstance(rule, dict) else None
                    )
                    if rule_name not in rule_names:
                        continue
                    rule_id = str(getattr(rule, "id", rule.get("id")))
                    session.run(
                        """
                        MATCH (r:Rule {id: $rid})
                        MATCH (p:Page {id: $page_id})
                        MERGE (r)-[:ON_SCREEN]->(p)
                        """,
                        rid=rule_id,
                        page_id=f"{investigation_id}:{screen_id}",
                    )
                    edges += 1

            for rule in rules:
                rule_id = str(getattr(rule, "id", rule.get("id")))
                condition_field = getattr(getattr(rule, "condition", None), "field", None) or (
                    (rule.get("condition", {}) or {}).get("field") if isinstance(rule, dict) else None
                )
                effect_field = getattr(getattr(rule, "effect", None), "field", None) or (
                    (rule.get("effect", {}) or {}).get("field") if isinstance(rule, dict) else None
                )
                session.run(
                    """
                    MERGE (r:Rule {id: $id})
                    SET r.name = $name,
                        r.status = $status,
                        r.confidence = $confidence,
                        r.condition_field = $condition_field,
                        r.effect_field = $effect_field,
                        r.evidence_ids = $evidence_ids,
                        r.investigation_id = $app_id
                    WITH r
                    MATCH (a:Application {id: $app_id})
                    MERGE (a)-[:contains]->(r)
                    """,
                    id=rule_id,
                    name=getattr(rule, "name", None) or (rule.get("name") if isinstance(rule, dict) else None),
                    status=str(
                        getattr(rule, "status", None) or (rule.get("status") if isinstance(rule, dict) else "")
                    ),
                    confidence=float(
                        getattr(rule, "confidence", None)
                        or (rule.get("confidence") if isinstance(rule, dict) else 0)
                        or 0
                    ),
                    condition_field=condition_field,
                    effect_field=effect_field,
                    evidence_ids=[str(eid) for eid in (getattr(rule, "evidence_ids", None) or [])],
                    app_id=app_id,
                )
                nodes += 1
                edges += 1

                if condition_field and effect_field:
                    session.run(
                        """
                        MATCH (r:Rule {id: $rid})
                        MERGE (c:Field {name: $condition_field, investigation_id: $app_id})
                        MERGE (e:Field {name: $effect_field, investigation_id: $app_id})
                        MERGE (c)-[:controls]->(e)
                        MERGE (r)-[:asserts]->(c)
                        MERGE (r)-[:affects]->(e)
                        """,
                        rid=rule_id,
                        condition_field=condition_field,
                        effect_field=effect_field,
                        app_id=app_id,
                    )
                    nodes += 2
                    edges += 3

                for eid in getattr(rule, "evidence_ids", None) or []:
                    session.run(
                        """
                        MERGE (e:Evidence {id: $eid})
                        WITH e
                        MATCH (r:Rule {id: $rid})
                        MERGE (r)-[:supported_by]->(e)
                        """,
                        eid=str(eid),
                        rid=rule_id,
                    )
                    nodes += 1
                    edges += 1

            for item in evidence:
                eid = str(getattr(item, "id", item.get("id")))
                session.run(
                    """
                    MERGE (e:Evidence {id: $id})
                    SET e.type = $type,
                        e.url = $url
                    """,
                    id=eid,
                    type=str(
                        getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else "")
                    ),
                    url=getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None),
                )
                nodes += 1
    finally:
        driver.close()

    return {"nodes": nodes, "edges": edges, "skipped": 0}


def query_related_rule_ids(
    investigation_id: UUID,
    question: str,
    limit: int = 8,
    application_key: str | None = None,
) -> list[str]:
    """Return rule ids from Neo4j that match question tokens on field names / rule names."""
    if not kg_enabled():
        return []
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", question) if len(t) > 2]
    if not tokens:
        return []
    app_id = application_key or str(investigation_id)
    try:
        driver = _driver()
    except Exception:
        return []

    try:
        with driver.session() as session:
            direct = session.run(
                """
                MATCH (a:Application {id: $app_id})-[:contains]->(r:Rule)
                WHERE any(token IN $tokens WHERE
                    toLower(coalesce(r.name, '')) CONTAINS token
                    OR toLower(coalesce(r.condition_field, '')) CONTAINS token
                    OR toLower(coalesce(r.effect_field, '')) CONTAINS token
                )
                RETURN r.id AS id, r.confidence AS confidence, r.status AS status
                LIMIT $limit
                """,
                app_id=app_id,
                tokens=tokens,
                limit=limit,
            )
            entity_rules = session.run(
                """
                MATCH (a:Application {id: $app_id})-[:models]->(e:Entity)
                WHERE any(token IN $tokens WHERE toLower(e.name) CONTAINS token)
                MATCH (a)-[:contains]->(r:Rule)
                WHERE toLower(coalesce(r.condition_field, '')) CONTAINS toLower(e.name)
                   OR toLower(coalesce(r.effect_field, '')) CONTAINS toLower(e.name)
                RETURN r.id AS id, r.confidence AS confidence, r.status AS status
                LIMIT $limit
                """,
                app_id=app_id,
                tokens=tokens,
                limit=limit,
            )
            seen: list[str] = []
            ranked: list[tuple[int, float, str]] = []
            for record in list(direct) + list(entity_rules):
                rid = record.get("id")
                if not rid or rid in seen:
                    continue
                seen.append(rid)
                status = str(record.get("status") or "")
                rank = 0 if status == "verified" else 1 if status == "candidate" else 2
                ranked.append((rank, float(record.get("confidence") or 0), rid))
            ranked.sort(key=lambda item: (item[0], -item[1]))
            return [rid for _, _, rid in ranked[:limit]]
    except Exception:
        return []
    finally:
        try:
            driver.close()
        except Exception:
            pass


def local_related_rule_ids(rules: list[Any], question: str, limit: int = 8) -> list[str]:
    """In-memory field graph: prefer rules sharing condition/effect fields mentioned in the question."""
    tokens = {t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", question) if len(t) > 2}
    scored: list[tuple[float, str]] = []
    for rule in rules:
        condition = getattr(getattr(rule, "condition", None), "field", "") or ""
        effect = getattr(getattr(rule, "effect", None), "field", "") or ""
        name = getattr(rule, "name", "") or ""
        status = str(getattr(rule, "status", "") or "")
        haystack = f"{name} {condition} {effect}".lower()
        overlap = sum(1 for token in tokens if token in haystack)
        if overlap == 0:
            continue
        score = float(overlap) + float(getattr(rule, "confidence", 0) or 0)
        if status == "verified":
            score += 2
        # Boost rules that share fields with other matched rules (local neighborhood)
        scored.append((score, str(getattr(rule, "id"))))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [rule_id for _, rule_id in scored[:limit]]
