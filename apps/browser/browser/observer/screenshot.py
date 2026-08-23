"""Screenshot artifact capture under ~/.webtwin/artifacts."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID


def artifacts_root() -> Path:
    root = Path.home() / ".webtwin" / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def capture_screenshot(page, investigation_id: UUID, label: str = "observation") -> str:
    directory = artifacts_root() / str(investigation_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{label}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)
