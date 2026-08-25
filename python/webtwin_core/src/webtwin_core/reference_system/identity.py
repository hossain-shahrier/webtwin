"""Stable application identity shared across investigations."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse


def normalize_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme == "file":
        path = unquote(parsed.path or "")
        if not path:
            return "file-local"
        stem = Path(path).stem or Path(path).name or "local"
        parent = Path(path).parent.name or "fixture"
        return f"file:{slugify(parent)}:{slugify(stem)}"
    host = (parsed.netloc or "").lower()
    if not host and parsed.path:
        host = parsed.path.split("/")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    # Collapse localhost variants so same local app shares a key
    if host.startswith("127.0.0.1"):
        host = "localhost" + host[len("127.0.0.1") :]
    if host.startswith("localhost:"):
        host = "localhost"
    elif host == "127.0.0.1":
        host = "localhost"
    return host


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "app"


def application_key_for(
    target_url: str,
    *,
    application_name: str | None = None,
    application_key: str | None = None,
) -> str:
    """Stable key for an application across runs (host, optionally named)."""
    if application_key and application_key.strip():
        return slugify(application_key.strip())
    # Guard: callers sometimes pass a model by mistake
    if not isinstance(target_url, str):
        target_url = str(getattr(target_url, "target_url", "") or "")
    host = normalize_host(target_url or "")
    if application_name and application_name.strip():
        base = host or "app"
        return f"{base}:{slugify(application_name)}"
    return host or "unknown"


def normalize_role_scope(role_scope: str | None) -> str:
    if not role_scope or not role_scope.strip():
        return "default"
    return slugify(role_scope.strip())
