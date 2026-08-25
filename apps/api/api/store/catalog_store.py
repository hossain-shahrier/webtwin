"""Persistent application catalog storage (Postgres + memory fallback)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from webtwin_core.reference_system.catalog import ApplicationCatalog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


class CatalogStore:
    """Load/save ApplicationCatalog and golden reference pins."""

    def __init__(self, *, session_factory=None, memory: dict | None = None) -> None:
        self._session_factory = session_factory
        self._memory = memory if memory is not None else {}
        self._file_dir = Path.home() / ".webtwin" / "catalogs"
        self._file_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_key(application_key: str) -> str:
        """Filesystem-safe key (colons break some OSes / tools)."""
        return (application_key or "app").replace(":", "__").replace("/", "_")

    def get(self, application_key: str) -> ApplicationCatalog | None:
        if application_key in self._memory:
            return self._memory[application_key]
        file_path = self._file_dir / f"{self._safe_key(application_key)}.json"
        if file_path.exists():
            data = json.loads(file_path.read_text())
            catalog = ApplicationCatalog.model_validate(data)
            self._memory[application_key] = catalog
            return catalog
        # Legacy unsanitized filenames
        legacy = self._file_dir / f"{application_key}.json"
        if legacy.exists():
            data = json.loads(legacy.read_text())
            catalog = ApplicationCatalog.model_validate(data)
            self._memory[application_key] = catalog
            return catalog
        if self._session_factory is None:
            return None
        from api.db.schema import ApplicationCatalogRow
        from sqlalchemy import select

        with self._session_factory() as session:
            row = session.scalar(
                select(ApplicationCatalogRow).where(
                    ApplicationCatalogRow.application_key == application_key
                )
            )
            if row is None:
                return None
            catalog = ApplicationCatalog.model_validate(row.payload)
            self._memory[application_key] = catalog
            return catalog

    def list_all(self) -> list[ApplicationCatalog]:
        if self._session_factory is not None:
            from api.db.schema import ApplicationCatalogRow
            from sqlalchemy import select

            with self._session_factory() as session:
                rows = session.scalars(select(ApplicationCatalogRow)).all()
                catalogs = [ApplicationCatalog.model_validate(row.payload) for row in rows]
                for catalog in catalogs:
                    self._memory[catalog.application_key] = catalog
                if catalogs:
                    return catalogs
        if self._memory:
            return list(self._memory.values())
        catalogs: list[ApplicationCatalog] = []
        for path in self._file_dir.glob("*.json"):
            if path.name.startswith("golden_"):
                continue
            try:
                catalog = ApplicationCatalog.model_validate(json.loads(path.read_text()))
                self._memory[catalog.application_key] = catalog
                catalogs.append(catalog)
            except Exception:
                continue
        return catalogs

    def save(self, catalog: ApplicationCatalog) -> ApplicationCatalog:
        catalog.updated_at = datetime.now(UTC)
        self._memory[catalog.application_key] = catalog
        file_path = self._file_dir / f"{self._safe_key(catalog.application_key)}.json"
        file_path.write_text(catalog.model_dump_json())
        if self._session_factory is not None:
            from api.db.schema import ApplicationCatalogRow

            with self._session_factory() as session:
                row = session.get(ApplicationCatalogRow, catalog.application_key)
                payload = catalog.model_dump(mode="json")
                if row is None:
                    row = ApplicationCatalogRow(
                        application_key=catalog.application_key,
                        payload=payload,
                        updated_at=catalog.updated_at,
                    )
                    session.add(row)
                else:
                    row.payload = payload
                    row.updated_at = catalog.updated_at
                session.commit()
        return catalog

    def pin_golden(self, application_key: str, version: str, catalog: ApplicationCatalog) -> dict:
        snapshot = catalog.model_dump(mode="json")
        record = {
            "application_key": application_key,
            "version": version,
            "pinned_at": datetime.now(UTC).isoformat(),
            "catalog": snapshot,
        }
        golden_path = (
            self._file_dir / f"golden_{self._safe_key(application_key)}@{version}.json"
        )
        golden_path.write_text(json.dumps(record, default=str))
        if self._session_factory is not None:
            from api.db.schema import ApplicationCatalogRow

            with self._session_factory() as session:
                row = session.get(ApplicationCatalogRow, application_key)
                if row is None:
                    row = ApplicationCatalogRow(
                        application_key=application_key,
                        payload=snapshot,
                        golden_version=version,
                        golden_payload=snapshot,
                        updated_at=datetime.now(UTC),
                    )
                    session.add(row)
                else:
                    row.golden_version = version
                    row.golden_payload = snapshot
                    row.updated_at = datetime.now(UTC)
                session.commit()
        return record

    def get_golden(self, application_key: str, version: str | None = None) -> dict | None:
        if self._session_factory is not None:
            from api.db.schema import ApplicationCatalogRow

            with self._session_factory() as session:
                row = session.get(ApplicationCatalogRow, application_key)
                if row and row.golden_payload:
                    if version is None or row.golden_version == version:
                        return {
                            "application_key": application_key,
                            "version": row.golden_version,
                            "catalog": row.golden_payload,
                        }
        safe = self._safe_key(application_key)
        for path in self._file_dir.glob("golden_*.json"):
            if safe not in path.name and application_key not in path.name:
                continue
            data = json.loads(path.read_text())
            if data.get("application_key") not in {None, application_key}:
                continue
            if version is None or data.get("version") == version:
                return data
        return None
