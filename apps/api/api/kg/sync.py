"""Neo4j knowledge graph sync — derived index from Postgres/memory store."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID


def kg_enabled() -> bool:
    return os.environ.get("WEBTWIN_KG_ENABLED", "").lower() in {"1", "true", "yes"}


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
) -> dict[str, int]:
    """
    Idempotent upsert of Application/Page/Rule/Evidence nodes with evidence_id FKs.
    No-ops when WEBTWIN_KG_ENABLED is false or neo4j driver is unavailable.
    """
    if not kg_enabled():
        return {"nodes": 0, "edges": 0, "skipped": 1}

    try:
        from neo4j import GraphDatabase  # type: ignore
    except ImportError:
        return {"nodes": 0, "edges": 0, "skipped": 1, "reason": "neo4j_driver_missing"}

    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "webtwin-neo4j")

    nodes = 0
    edges = 0
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (a:Application {id: $id})
                SET a.name = $name,
                    a.target_url = $url,
                    a.role_scope = $role_scope,
                    a.application_version = $version,
                    a.environment = $environment
                """,
                id=str(investigation_id),
                name=application_name or "unknown",
                url=target_url,
                role_scope=role_scope,
                version=application_version,
                environment=environment,
            )
            nodes += 1

            session.run(
                """
                MERGE (p:Page {id: $page_id})
                SET p.url = $url
                WITH p
                MATCH (a:Application {id: $app_id})
                MERGE (a)-[:contains]->(p)
                """,
                page_id=f"{investigation_id}:page",
                url=target_url,
                app_id=str(investigation_id),
            )
            nodes += 1
            edges += 1

            for rule in rules:
                rule_id = str(getattr(rule, "id", rule.get("id")))
                session.run(
                    """
                    MERGE (r:Rule {id: $id})
                    SET r.name = $name,
                        r.status = $status,
                        r.confidence = $confidence,
                        r.condition_field = $condition_field,
                        r.effect_field = $effect_field,
                        r.evidence_ids = $evidence_ids
                    WITH r
                    MATCH (a:Application {id: $app_id})
                    MERGE (a)-[:contains]->(r)
                    """,
                    id=rule_id,
                    name=getattr(rule, "name", None) or (rule.get("name") if isinstance(rule, dict) else None),
                    status=str(getattr(rule, "status", None) or (rule.get("status") if isinstance(rule, dict) else "")),
                    confidence=float(
                        getattr(rule, "confidence", None)
                        or (rule.get("confidence") if isinstance(rule, dict) else 0)
                        or 0
                    ),
                    condition_field=getattr(getattr(rule, "condition", None), "field", None)
                    or (rule.get("condition", {}) or {}).get("field")
                    if isinstance(rule, dict)
                    else None,
                    effect_field=getattr(getattr(rule, "effect", None), "field", None)
                    or (rule.get("effect", {}) or {}).get("field")
                    if isinstance(rule, dict)
                    else None,
                    evidence_ids=[str(eid) for eid in (getattr(rule, "evidence_ids", None) or [])],
                    app_id=str(investigation_id),
                )
                nodes += 1
                edges += 1

                for eid in getattr(rule, "evidence_ids", None) or []:
                    session.run(
                        """
                        MERGE (e:Evidence {id: $eid})
                        WITH e
                        MATCH (r:Rule {id: $rid})
                        MERGE (r)-[:supported_by]->(e)
                        MERGE (r)-[:verified_by]->(e)
                        """,
                        eid=str(eid),
                        rid=rule_id,
                    )
                    nodes += 1
                    edges += 2

            for item in evidence:
                eid = str(getattr(item, "id", item.get("id")))
                session.run(
                    """
                    MERGE (e:Evidence {id: $id})
                    SET e.type = $type,
                        e.url = $url
                    """,
                    id=eid,
                    type=str(getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else "")),
                    url=getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None),
                )
                nodes += 1
    finally:
        driver.close()

    return {"nodes": nodes, "edges": edges, "skipped": 0}
