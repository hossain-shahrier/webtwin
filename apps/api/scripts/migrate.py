"""Initialize PostgreSQL schema for WebTwin API."""

from __future__ import annotations

from api.db.engine import create_db_engine, get_database_url, init_db, ping_db


def main() -> None:
    url = get_database_url()
    engine = create_db_engine(url)
    ping_db(engine)
    init_db(engine)
    # Additive columns for evolving M5/M6 schema (create_all does not alter existing tables).
    from sqlalchemy import text

    statements = [
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS options JSONB DEFAULT '[]'::jsonb",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS text TEXT",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS input_type VARCHAR(64)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS application_version VARCHAR(128)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS environment VARCHAR(128)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS role_scope VARCHAR(128)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS spa_mode BOOLEAN DEFAULT FALSE",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS application_key VARCHAR(256)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS exploration_policy VARCHAR(64)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS investigation_scope VARCHAR(64)",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS url_prefix TEXT",
        "ALTER TABLE investigations ADD COLUMN IF NOT EXISTS start_url TEXT",
        "CREATE TABLE IF NOT EXISTS discovered_links ("
        "id UUID PRIMARY KEY, "
        "investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE, "
        "from_screen_id TEXT NOT NULL, "
        "to_screen_id TEXT, "
        "href TEXT NOT NULL, "
        "label TEXT, "
        "selector TEXT, "
        "link_type VARCHAR(32) NOT NULL DEFAULT 'navigate', "
        "visited BOOLEAN DEFAULT FALSE, "
        "discovered_at TIMESTAMPTZ NOT NULL, "
        "CONSTRAINT uq_discovered_link UNIQUE (investigation_id, from_screen_id, href)"
        ")",
        "CREATE INDEX IF NOT EXISTS ix_discovered_links_investigation ON discovered_links(investigation_id)",
        "CREATE TABLE IF NOT EXISTS application_catalogs ("
        "application_key VARCHAR(256) PRIMARY KEY, "
        "payload JSONB NOT NULL, "
        "golden_version VARCHAR(128), "
        "golden_payload JSONB, "
        "updated_at TIMESTAMPTZ NOT NULL"
        ")",
        "ALTER TABLE observations ADD COLUMN IF NOT EXISTS route JSONB",
        "ALTER TABLE observations ADD COLUMN IF NOT EXISTS framework_hints JSONB DEFAULT '{}'::jsonb",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS testid TEXT",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS stable_key TEXT",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS selector_candidates JSONB DEFAULT '[]'::jsonb",
        "ALTER TABLE observation_elements ADD COLUMN IF NOT EXISTS in_shadow_dom BOOLEAN DEFAULT FALSE",
        "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS settle_timeouts INTEGER DEFAULT 0",
        "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS soft_nav_success_rate DOUBLE PRECISION",
        "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS routes_seen INTEGER DEFAULT 0",
        "ALTER TABLE network_events ADD COLUMN IF NOT EXISTS route_path TEXT",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    print(f"Schema ready at {url}")


if __name__ == "__main__":
    main()
