"""Tests for site graph link extraction and stats."""

from uuid import uuid4

from webtwin_core.exploration.state import ExplorationState
from webtwin_core.models.observation import ElementSnapshot, Observation
from webtwin_core.models.spa import RouteSnapshot
from webtwin_core.reference_system.site_graph import (
    LinkType,
    extract_discovered_links,
    merge_discovered_links,
    mark_links_visited,
    compute_site_graph_stats,
    navigate_priority,
    route_pattern_key,
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


def test_navigate_priority_boosts_forms_and_details():
    base = "http://localhost:3001/company-management/details/207"
    forms = navigate_priority(base, "/forms/hearing/abc123token456789012345678")
    details = navigate_priority(base, "/company-management/details/208")
    edit = navigate_priority(base, "/company-management/edit/208")
    assert forms < details < edit


def test_route_pattern_key_collapses_opaque_tokens_only():
    token_path = "/forms/hearing/7sMkD1pZ2SiaHg6l5rPktUy6xUhH5upaMQ0fuwzrAs9ySt8OO47sahvJ4C4GknC3"
    assert route_pattern_key(token_path) == "/forms/hearing/:token"
    assert route_pattern_key("/company-management/details/207") is None


def test_extract_discovered_links_from_copy_link_input():
    obs = Observation(
        investigation_id=uuid4(),
        url="http://localhost:3001/company-management/details/207",
        title="Company",
        route=RouteSnapshot(
            url="http://localhost:3001/company-management/details/207",
            path="/company-management/details/207",
        ),
        elements=[
            ElementSnapshot(
                tag="input",
                selector="input[name=hearingLink]",
                value="http://localhost:3001/forms/hearing/7sMkD1pZ2SiaHg6l5rPktUy6xUhH5upaMQ0fuwzrAs9ySt8OO47sahvJ4C4GknC3",
                label="Hearing form link",
                visible=True,
            )
        ],
    )
    links = extract_discovered_links(obs, origin_url=obs.url)
    assert len(links) == 1
    assert links[0].to_screen_id == (
        "/forms/hearing/7sMkD1pZ2SiaHg6l5rPktUy6xUhH5upaMQ0fuwzrAs9ySt8OO47sahvJ4C4GknC3"
    )


def test_screen_visited_treats_hearing_tokens_as_one_pattern():
    state = ExplorationState(
        pages_seen_urls=[
            "http://localhost:3001/forms/hearing/visitedToken1234567890123456789012"
        ]
    )
    assert state._screen_visited(
        "/forms/hearing/differentToken123456789012345678901234"
    )
    assert not state._screen_visited("/company-management/details/207")


def test_extract_skips_fragment_only_hrefs():
    obs = _observation(
        url="https://shop.example/",
        path="/",
        links=[
            ("#", "Top"),
            ("#content", "Skip to content"),
            ("/about/", "About"),
            ("/product-category/men/", "Men"),
        ],
    )
    links = extract_discovered_links(obs, origin_url=obs.url)
    hrefs = {link.href for link in links}
    assert "#" not in hrefs
    assert "#content" not in hrefs
    assert hrefs == {"/about/", "/product-category/men/"}


def test_extract_keeps_spa_hash_routes():
    obs = _observation(
        url="https://app.example/",
        path="/",
        links=[
            ("#/dashboard", "Dashboard"),
            ("#!/jobs", "Jobs"),
            ("#content", "Skip"),
        ],
    )
    links = extract_discovered_links(obs, origin_url=obs.url)
    hrefs = {link.href for link in links}
    assert "#/dashboard" in hrefs
    assert "#!/jobs" in hrefs
    assert "#content" not in hrefs


def test_coverage_excludes_fragment_and_route_links():
    from webtwin_core.reference_system.site_graph import DiscoveredLink

    investigation_id = uuid4()
    links = [
        DiscoveredLink(
            investigation_id=investigation_id,
            from_screen_id="/",
            to_screen_id="/#content",
            href="#content",
            link_type=LinkType.ROUTE,
        ),
        DiscoveredLink(
            investigation_id=investigation_id,
            from_screen_id="/",
            to_screen_id="/about/",
            href="/about/",
            link_type=LinkType.NAVIGATE,
            visited=True,
        ),
        DiscoveredLink(
            investigation_id=investigation_id,
            from_screen_id="/",
            to_screen_id="/product/shirt/",
            href="/product/shirt/",
            link_type=LinkType.NAVIGATE,
            visited=False,
        ),
        DiscoveredLink(
            investigation_id=investigation_id,
            from_screen_id="/about/",
            to_screen_id="/about/#section",
            href="/about/#section",
            link_type=LinkType.NAVIGATE,
        ),
    ]
    screens = [
        Screen(id="/", name="Home", url="https://shop.example/", path="/"),
        Screen(id="/about/", name="About", url="https://shop.example/about/", path="/about/"),
    ]
    stats = compute_site_graph_stats(links, screens, origin_url="https://shop.example/")
    assert stats.total_internal == 2
    assert stats.coverage_pct == 0.5
    assert all("#" not in sample for sample in stats.unvisited_sample)
