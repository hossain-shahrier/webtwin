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
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    print(f"Schema ready at {url}")


if __name__ == "__main__":
    main()
