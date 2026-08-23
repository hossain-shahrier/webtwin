"""Tests for site graph link extraction and stats."""

from uuid import uuid4

from webtwin_core.models.observation import ElementSnapshot, Observation
from webtwin_core.models.spa import RouteSnapshot
from webtwin_core.reference_system.site_graph import (
    LinkType,
    extract_discovered_links,
    merge_discovered_links,
    mark_links_visited,
    compute_site_graph_stats,
)
from webtwin_core.reference_system import Screen, build_navigation
from webtwin_core.models import ApplicationState, TimelineEvent, TimelineEventType


def _observation(*, url: str, path: str, links: list[tuple[str, str]]) -> Observation:
    investigation_id = uuid4()
    return Observation(
        investigation_id=investigation_id,
        url=url,
        title="Test",
        route=RouteSnapshot(url=url, path=path),
        elements=[
            ElementSnapshot(
                tag="a",
                selector=f"a-{index}",
                value=href,
                label=label,
                visible=True,
            )
            for index, (href, label) in enumerate(links)
        ],
    )


def test_extract_discovered_links_same_origin():
    obs = _observation(
        url="https://shop.example/",
        path="/",
        links=[
            ("/about", "About"),
            ("/product-category/widgets", "Widgets"),
            ("https://other.example/x", "External"),
            ("mailto:support@example.com", "Email"),
        ],
    )
    links = extract_discovered_links(obs, origin_url=obs.url)
    internal = [link for link in links if link.link_type != LinkType.EXTERNAL]
    assert len(internal) == 2
    assert internal[0].from_screen_id == "/"
    assert internal[1].to_screen_id == "/product-category/widgets"
    assert all(not link.visited for link in links)


def test_merge_and_mark_visited():
    investigation_id = uuid4()
    first = extract_discovered_links(
        _observation(
            url="https://shop.example/",
            path="/",
            links=[("/about", "About")],
        )
    )
    for link in first:
        link.investigation_id = investigation_id
    second = extract_discovered_links(
        _observation(
            url="https://shop.example/about",
            path="/about",
            links=[("/contact", "Contact")],
        )
    )
    for link in second:
        link.investigation_id = investigation_id
    merged = merge_discovered_links(first, second)
    assert len(merged) == 2
    mark_links_visited(merged, to_screen_id="/about", href="/about")
    assert any(link.visited and link.href == "/about" for link in merged)


def test_strict_mark_requires_href():
    links = extract_discovered_links(
        _observation(
            url="https://shop.example/",
            path="/",
            links=[("/contact", "Contact")],
        )
    )
    mark_links_visited(links, to_screen_id="/contact", strict=True)
    assert not any(link.visited for link in links)
    mark_links_visited(links, to_screen_id="/contact", href="/contact")
    assert links[0].visited


def test_build_navigation_uses_state_ids():
    investigation_id = uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        url="https://shop.example/",
        sequence=1,
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        url="https://shop.example/about",
        sequence=2,
    )
    event = TimelineEvent(
        investigation_id=investigation_id,
        type=TimelineEventType.NAVIGATE,
        description="nav a=/about href=/about",
        state_before_id=before.id,
        state_after_id=after.id,
    )
    edges = build_navigation([event], [before, after], [])
    assert len(edges) == 1
    assert edges[0].from_screen_id == "/"
    assert edges[0].to_screen_id == "/about"
    assert edges[0].href == "/about"


def test_build_site_graph_adds_unvisited_target_nodes() -> None:
    from webtwin_core.reference_system import Screen
    from webtwin_core.reference_system.site_graph import build_site_graph, DiscoveredLink, LinkType

    links = [
        DiscoveredLink(
            investigation_id=uuid4(),
            from_screen_id="/",
            to_screen_id="/future",
            href="/future",
            link_type=LinkType.NAVIGATE,
        )
    ]
    graph = build_site_graph([], links, [], origin_url="https://shop.example/")
    assert any(node.id == "/future" for node in graph.nodes)
    assert graph.nodes[0].visit_count == 0

    investigation_id = uuid4()
    links = extract_discovered_links(
        _observation(
            url="https://shop.example/",
            path="/",
            links=[("/a", "A"), ("/b", "B")],
        )
    )
    for link in links:
        link.investigation_id = investigation_id
    mark_links_visited(links, to_screen_id="/a", href="/a")
    screens = [
        Screen(id="/", name="Home", url="https://shop.example/", path="/"),
        Screen(id="/a", name="A", url="https://shop.example/a", path="/a"),
    ]
    stats = compute_site_graph_stats(links, screens, origin_url="https://shop.example/")
    assert stats.total_internal == 2
    assert stats.total_visited_links == 1
    assert stats.coverage_pct == 0.5
