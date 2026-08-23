"""Session persistence — Playwright storage_state only (never log secrets)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

from playwright.sync_api import Browser, BrowserContext


class SessionStore:
    """Persist Playwright storage state locally per investigation (sensitive — never logged)."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".webtwin" / "sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, investigation_id: UUID) -> Path:
        return self.base_dir / f"{investigation_id}.json"

    def save(self, context: BrowserContext, investigation_id: UUID) -> Path:
        path = self.path_for(investigation_id)
        context.storage_state(path=str(path))
        return path

    def exists(self, investigation_id: UUID) -> bool:
        return self.path_for(investigation_id).exists()

    def bootstrap_from_env(self, investigation_id: UUID) -> Path | None:
        """
        Optionally seed this investigation from WEBTWIN_STORAGE_STATE.
        Use after a headed HITL login export — does not read Chrome's cookie DB.
        """
        raw = os.environ.get("WEBTWIN_STORAGE_STATE", "").strip()
        if not raw:
            return None
        source = Path(raw).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"WEBTWIN_STORAGE_STATE not found: {source}")
        dest = self.path_for(investigation_id)
        shutil.copyfile(source, dest)
        return dest

    def new_context(self, browser: Browser, investigation_id: UUID) -> BrowserContext:
        self.bootstrap_from_env(investigation_id)
        path = self.path_for(investigation_id)
        if path.exists() and path.stat().st_size > 50:
            return browser.new_context(storage_state=str(path))
        return browser.new_context()

    def delete(self, investigation_id: UUID) -> None:
        path = self.path_for(investigation_id)
        if path.exists():
            path.unlink()
