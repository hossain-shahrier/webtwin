from __future__ import annotations

import os

from api.store.memory import MemoryStore


def create_store():
    backend = os.environ.get("WEBTWIN_STORE", "memory").lower()
    if backend in {"postgres", "postgresql", "db"}:
        from api.db.engine import create_db_engine, create_session_factory, init_db
        from api.store.postgres import PostgresStore

        engine = create_db_engine()
        init_db(engine)
        return PostgresStore(create_session_factory(engine))
    return MemoryStore()
