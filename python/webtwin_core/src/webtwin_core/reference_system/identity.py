"""Stable application identity shared across investigations."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
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
    host = normalize_host(target_url)
    if application_name and application_name.strip():
        return f"{host}:{slugify(application_name)}"
    return host or "unknown"


def normalize_role_scope(role_scope: str | None) -> str:
    if not role_scope or not role_scope.strip():
        return "default"
    return slugify(role_scope.strip())
