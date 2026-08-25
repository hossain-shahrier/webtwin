"""Site graph — discovered outbound links and coverage stats."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.observation import Observation

if TYPE_CHECKING:
    from webtwin_core.models.observation import ElementSnapshot
    from webtwin_core.reference_system import NavigationEdge, Screen


def normalize_screen_id(screen_id: str) -> str:
    """Canonical screen key for graph matching (trailing slash insensitive)."""
    return (screen_id or "/").rstrip("/") or "/"


_OPAQUE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def _is_opaque_token(part: str) -> bool:
    """True for signed/random URL segments, not kebab-case route names."""
    if len(part) < 20 or part.isdigit():
        return False
    if not _OPAQUE_TOKEN.match(part):
        return False
    if "-" in part and part.lower() == part:
        return False
    has_upper = any(char.isupper() for char in part)
    has_lower = any(char.islower() for char in part)
    has_digit = any(char.isdigit() for char in part)
    return (has_upper and has_lower) or has_digit or len(part) >= 32


def export_path_pattern(path: str) -> str:
    """Collapse numeric IDs and opaque tokens for compact export grouping."""
    parts = [part for part in normalize_screen_id(path).split("/") if part]
    if not parts:
        return "/"
    out: list[str] = []
    for part in parts:
        if part.isdigit():
            out.append(":id")
        elif _is_opaque_token(part):
            out.append(":token")
        else:
            out.append(part)
    return "/" + "/".join(out)


def route_pattern_key(screen_id: str) -> str | None:
    """Pattern key for signed/tokenized routes (e.g. /forms/hearing/:token).

    Returns None when the path has no opaque token segment so numeric detail
    pages like /company-management/details/207 stay distinct.
    """
    parts = [part for part in normalize_screen_id(screen_id).split("/") if part]
    if not parts:
        return None
    out: list[str] = []
    has_token = False
    for part in parts:
        if _is_opaque_token(part):
            out.append(":token")
            has_token = True
        else:
            out.append(part)
    if not has_token:
        return None
    return "/" + "/".join(out)


def href_from_element(element: "ElementSnapshot") -> str | None:
    """Extract an internal navigation href from anchors, buttons, or copy-link inputs."""
    raw = (element.value or "").strip()
    if not raw:
        return None
    if element.tag == "a":
        return raw
    if raw.startswith("/") or raw.startswith("#"):
        return raw
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        return parsed.path or raw
    if "/forms/" in raw:
        parsed = urlparse(urljoin("https://placeholder.invalid", raw))
        return parsed.path or None
    return None


def screen_id_from_url(url: str) -> str:
    """Derive screen id from a URL including hash routes (SPA)."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.fragment:
        fragment = parsed.fragment
        if not fragment.startswith("#"):
            fragment = f"#{fragment}"
        return f"{path}{fragment}" if fragment.startswith("#") else f"{path}#{fragment}"
    return path


def _screen_key_from_observation(observation: Observation) -> str:
    if observation.route:
        path = observation.route.path or "/"
        fragment = observation.route.hash or ""
        if fragment and not fragment.startswith("#"):
            fragment = f"#{fragment}"
        return f"{path}{fragment}" if fragment else path
    return screen_id_from_url(observation.url)


class LinkType(StrEnum):
    NAVIGATE = "navigate"
    ROUTE = "route"
    EXTERNAL = "external"


class DiscoveredLink(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    from_screen_id: str
    to_screen_id: str | None = None
    href: str
    label: str | None = None
    selector: str | None = None
    link_type: LinkType = LinkType.NAVIGATE
    visited: bool = False
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SiteGraphStats(BaseModel):
    total_discovered: int = 0
    total_internal: int = 0
    total_visited_screens: int = 0
    total_visited_links: int = 0
    coverage_pct: float = 0.0
    unvisited_sample: list[str] = Field(default_factory=list)


class SiteGraph(BaseModel):
    nodes: list["Screen"] = Field(default_factory=list)
    discovered_links: list[DiscoveredLink] = Field(default_factory=list)
    visited_edges: list["NavigationEdge"] = Field(default_factory=list)
    stats: SiteGraphStats = Field(default_factory=SiteGraphStats)


def _is_fragment_only_href(href: str) -> bool:
    """True for same-page anchors (#, #content) — not crawlable screens.

    SPA hash routes (#/dashboard, #!/app) are crawlable and must NOT be skipped.
    """
    stripped = (href or "").strip()
    if not stripped or stripped == "#":
        return True
    if not stripped.startswith("#"):
        return False
    rest = stripped[1:]
    # Hash router / hashbang SPA paths
    if rest.startswith("/") or rest.startswith("!/"):
        return False
    return True


def _should_skip_href(href: str) -> bool:
    lowered = href.lower().strip()
    if _is_fragment_only_href(href):
        return True
    if lowered.startswith(("mailto:", "tel:", "javascript:")):
        return True
    if lowered.endswith((".pdf", ".zip", ".doc")):
        return True
    path = urlparse(urljoin("https://placeholder.invalid", href)).path.lower()
    skip_paths = ("/login", "/signin", "/sign-in", "/logout")
    if any(path == token or path.startswith(f"{token}/") for token in skip_paths):
        return True
    if any(token in lowered for token in ("idp.", "sso.")):
        return True
    return False


def _same_origin(base_url: str, href: str) -> bool:
    if href.startswith("javascript:"):
        return False
    if href.startswith("#"):
        return True
    absolute = urljoin(base_url, href)
    base = urlparse(base_url)
    target = urlparse(absolute)
    if absolute.startswith("file:") or base.scheme == "file":
        return True
    return base.netloc == target.netloc


def _screen_id_from_href(base_url: str, href: str) -> str | None:
    if href.startswith("#"):
        base_path = urlparse(base_url).path or "/"
        return f"{base_path}{href}"
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if not _same_origin(base_url, href):
        return None
    path = parsed.path or "/"
    fragment = parsed.fragment
    return f"{path}#{fragment}" if fragment else path


def navigate_priority(base_url: str, href: str) -> int:
    """Lower is better — hub pages before deep product URLs."""
    absolute = urljoin(base_url, href)
    target = urlparse(absolute)
    path = (target.path or "/").lower()
    score = 0
    depth = len([p for p in path.split("/") if p])
    if path in {"/", ""}:
        score -= 10
    if "/forms/" in path:
        score -= 15
    if "/details/" in path:
        score -= 4
    if "/edit/" in path:
        score += 4
    if any(token in path for token in ("/about", "/contact", "/legal", "/policies")):
        score -= 5
    if "/product-category/" in path:
        score += depth
    elif "/product/" in path or "/shop/" in path:
        score += depth + 2
    else:
        score += max(0, depth - 1) * 2
    if target.query:
        score += 3
    return score


def extract_discovered_links(
    observation: Observation,
    *,
    origin_url: str | None = None,
) -> list[DiscoveredLink]:
    """Extract outbound links from anchor elements in an observation."""
    base_url = origin_url or observation.url
    from_screen_id = _screen_key_from_observation(observation)
    seen: set[tuple[str, str]] = set()
    links: list[DiscoveredLink] = []

    for element in observation.elements:
        href = href_from_element(element)
        if not href or _should_skip_href(href):
            continue
        signature = (from_screen_id, href)
        if signature in seen:
            continue
        seen.add(signature)

        same_origin = _same_origin(base_url, href)
        to_screen_id = _screen_id_from_href(base_url, href) if same_origin else None
        if href.startswith("#"):
            link_type = LinkType.ROUTE
        elif same_origin:
            link_type = LinkType.NAVIGATE
        else:
            link_type = LinkType.EXTERNAL

        links.append(
            DiscoveredLink(
                investigation_id=observation.investigation_id,
                from_screen_id=from_screen_id,
                to_screen_id=to_screen_id,
                href=href,
                label=element.label or element.text,
                selector=element.selector,
                link_type=link_type,
                visited=False,
            )
        )
    return links


def merge_discovered_links(
    existing: list[DiscoveredLink],
    incoming: list[DiscoveredLink],
) -> list[DiscoveredLink]:
    def _link_key(link: DiscoveredLink) -> tuple[str, str]:
        return (normalize_screen_id(link.from_screen_id), normalize_screen_id(link.href))

    by_key: dict[tuple[str, str], DiscoveredLink] = {}
    for link in existing:
        by_key[_link_key(link)] = link
    for link in incoming:
        key = _link_key(link)
        if key in by_key:
            prior = by_key[key]
            if link.label and not prior.label:
                prior.label = link.label
            if link.selector and not prior.selector:
                prior.selector = link.selector
            if link.to_screen_id and not prior.to_screen_id:
                prior.to_screen_id = link.to_screen_id
            if link.visited:
                prior.visited = True
        else:
            by_key[key] = link
    return list(by_key.values())


def mark_links_visited(
    links: list[DiscoveredLink],
    *,
    to_screen_id: str,
    href: str | None = None,
    strict: bool = True,
) -> list[DiscoveredLink]:
    """Mark link(s) visited. With strict=True, only explicit href matches count."""
    normalized_target = normalize_screen_id(to_screen_id)
    for link in links:
        if href:
            if link.href == href or normalize_screen_id(link.href) == normalize_screen_id(href):
                link.visited = True
            continue
        if strict:
            continue
        if link.to_screen_id and normalize_screen_id(link.to_screen_id) == normalized_target:
            link.visited = True
    return links


def _is_crawlable_internal(link: DiscoveredLink) -> bool:
    """Exclude external, fragment-only, and same-page ROUTE anchors from coverage."""
    if link.link_type == LinkType.EXTERNAL:
        return False
    if not link.to_screen_id:
        return False
    if link.link_type == LinkType.ROUTE:
        return False
    if _is_fragment_only_href(link.href):
        return False
    # Same-page fragment targets (/about → /about/#content) inflate the denominator
    if "#" in (link.to_screen_id or ""):
        from_base = link.from_screen_id.split("#", 1)[0].rstrip("/") or "/"
        to_base = link.to_screen_id.split("#", 1)[0].rstrip("/") or "/"
        if from_base == to_base:
            return False
    return True


def compute_site_graph_stats(
    links: list[DiscoveredLink],
    screens: list["Screen"],
    *,
    origin_url: str,
) -> SiteGraphStats:
    internal = [link for link in links if _is_crawlable_internal(link)]
    visited_internal = [link for link in internal if link.visited]
    unique_targets = {link.to_screen_id for link in internal if link.to_screen_id}
    visited_targets = {
        link.to_screen_id
        for link in internal
        if link.visited and link.to_screen_id
    }
    coverage = (
        len(visited_targets) / len(unique_targets) if unique_targets else 0.0
    )
    unvisited = sorted(
        [link for link in internal if not link.visited and link.to_screen_id],
        key=lambda item: navigate_priority(origin_url, item.href),
    )
    return SiteGraphStats(
        total_discovered=len(links),
        total_internal=len(internal),
        total_visited_screens=len(screens),
        total_visited_links=len(visited_internal),
        coverage_pct=round(coverage, 3),
        unvisited_sample=[f"{link.from_screen_id} → {link.href}" for link in unvisited[:20]],
    )


def build_site_graph(
    screens: list["Screen"],
    discovered_links: list[DiscoveredLink],
    visited_edges: list["NavigationEdge"],
    *,
    origin_url: str,
) -> SiteGraph:
    from webtwin_core.reference_system import Screen

    stats = compute_site_graph_stats(discovered_links, screens, origin_url=origin_url)
    nodes_by_id = {screen.id: screen for screen in screens}
    for link in discovered_links:
        if not link.to_screen_id or link.link_type == LinkType.EXTERNAL:
            continue
        if link.to_screen_id not in nodes_by_id:
            nodes_by_id[link.to_screen_id] = Screen(
                id=link.to_screen_id,
                name=link.label or link.to_screen_id,
                url=urljoin(origin_url, link.href),
                path=link.to_screen_id,
                visit_count=0,
            )
    return SiteGraph(
        nodes=sorted(nodes_by_id.values(), key=lambda item: item.id),
        discovered_links=discovered_links,
        visited_edges=visited_edges,
        stats=stats,
    )


def _rebuild_site_graph_models() -> None:
    from webtwin_core.reference_system import NavigationEdge, Screen

    SiteGraph.model_rebuild(_types_namespace={"Screen": Screen, "NavigationEdge": NavigationEdge})


_rebuild_site_graph_models()
