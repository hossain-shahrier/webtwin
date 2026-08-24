"""Filter network observations down to likely backend API calls."""

from __future__ import annotations

from urllib.parse import urlparse

_DEV_SERVER_MARKERS = (
    "/src/",
    "/node_modules/",
    "/@vite/",
    "/@fs/",
    "/@id/",
    "/__vite",
    "/webpack",
    "/hot-update",
)

_STATIC_EXTENSIONS = (
    ".tsx",
    ".jsx",
    ".vue",
    ".css",
    ".map",
    ".woff",
    ".woff2",
    ".ttf",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
)


def is_relevant_api_url(url: str) -> bool:
    """
    True for likely backend/API traffic — not Vite/webpack dev assets or static files.

    Crawling a local SPA (e.g. localhost:3001) captures module graph requests that are
    not REST endpoints. Those are excluded from api_hints exports.
    """
    if not url:
        return False
    lower = url.lower()
    if any(marker in lower for marker in _DEV_SERVER_MARKERS):
        return False
    if any(lower.split("?", 1)[0].endswith(ext) for ext in _STATIC_EXTENSIONS):
        return False

    parsed = urlparse(lower)
    path = parsed.path or "/"

    if path.endswith(".js") and "/api" not in path:
        return False
    if path.endswith(".ts") and "/api" not in path:
        return False

    api_markers = ("/api/", "/api/v", "/graphql", "/rest/", "/v1/", "/v2/")
    if any(marker in path for marker in api_markers):
        return True

    # Heuristic: short REST-ish paths on same host (e.g. /users/123, /companies)
    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[0] in {
        "users",
        "user",
        "companies",
        "company",
        "admin",
        "agencies",
        "agency",
        "jobs",
        "job",
        "applications",
        "application",
        "reports",
        "tasks",
        "auth",
        "login",
        "graphql",
    }:
        return True

    return False
