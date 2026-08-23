"""CLI: sync investigation(s) into Neo4j knowledge graph."""

from __future__ import annotations

import os
import sys
from uuid import UUID

# Ensure apps/api is on path when run via nx
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.kg.sync import kg_enabled, sync_investigation_to_kg  # noqa: E402
from api.store.factory import create_store  # noqa: E402


def main() -> None:
    if not kg_enabled():
        print("WEBTWIN_KG_ENABLED is not set — nothing to sync.")
        return

    store = create_store()
    investigation_id = os.environ.get("WEBTWIN_INVESTIGATION_ID")
    investigations = list(store.investigations.values())
    if investigation_id:
        inv = store.investigations.get(UUID(investigation_id))
        investigations = [inv] if inv else []

    total = {"nodes": 0, "edges": 0}
    for investigation in investigations:
        rules = [r for r in store.rules.values() if r.investigation_id == investigation.id]
        evidence = [e for e in store.evidence.values() if e.investigation_id == investigation.id]
        result = sync_investigation_to_kg(
            investigation_id=investigation.id,
            application_name=investigation.application_name,
            target_url=investigation.target_url,
            rules=rules,
            evidence=evidence,
            role_scope=investigation.role_scope,
            application_version=investigation.application_version,
            environment=investigation.environment,
        )
        print(f"{investigation.id}: {result}")
        total["nodes"] += result.get("nodes", 0)
        total["edges"] += result.get("edges", 0)

    print(f"Done. nodes={total['nodes']} edges={total['edges']}")


if __name__ == "__main__":
    main()
