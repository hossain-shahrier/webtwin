"""Tests for lean durable exploration progress."""

from webtwin_core.exploration.budget import ExplorationBudget
from webtwin_core.exploration.progress import (
    ExplorationProgress,
    apply_progress,
    rebuild_frontier_from_links,
    snapshot_progress,
)
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.reference_system.site_graph import DiscoveredLink, LinkType
from uuid import uuid4


def test_snapshot_and_apply_roundtrip():
    state = ExplorationState(url_prefix="/app")
    state.frontier = ["/a", "/b", "/c"]
    state.pages_seen_urls = ["https://ex.test/", "https://ex.test/a"]
    state.routes_seen = ["/", "/a"]
    state.tested_action_keys = ["nav:/a", "select:x"]
    state.explored_field_targets = ["email"]
    state.actions_taken = 12
    state.scrolls_used = 2
    budget = ExplorationBudget(max_actions=100, max_pages=20)
    budget.actions_used = 12
    budget.pages_seen = 2

    progress = snapshot_progress(state, budget, last_url="https://ex.test/a", policy="site_map")
    assert progress.last_url == "https://ex.test/a"
    assert progress.frontier == ["/a", "/b", "/c"]
    assert progress.policy == "site_map"

    restored = ExplorationState()
    restored_budget = ExplorationBudget(max_actions=100, max_pages=20)
    apply_progress(restored, restored_budget, progress)
    assert restored.frontier == ["/a", "/b", "/c"]
    assert restored.pages_seen_urls == ["https://ex.test/", "https://ex.test/a"]
    assert restored.tested_action_keys == ["nav:/a", "select:x"]
    assert restored_budget.actions_used == 12
    assert restored_budget.pages_seen == 2


def test_progress_caps_long_lists():
    progress = ExplorationProgress(
        frontier=[f"/p{i}" for i in range(500)],
        pages_seen=[f"https://ex.test/{i}" for i in range(500)],
        tested_action_keys=[f"k{i}" for i in range(2000)],
    ).capped()
    assert len(progress.frontier) <= 200
    assert len(progress.pages_seen) <= 300
    assert len(progress.tested_action_keys) <= 800


def test_rebuild_frontier_skips_visited():
    state = ExplorationState()
    state.pages_seen_urls = ["https://ex.test/a"]
    state.routes_seen = ["/a"]
    inv = uuid4()
    links = [
        DiscoveredLink(
            investigation_id=inv,
            from_screen_id="/",
            to_screen_id="/a",
            href="/a",
            link_type=LinkType.NAVIGATE,
            visited=True,
        ),
        DiscoveredLink(
            investigation_id=inv,
            from_screen_id="/",
            to_screen_id="/b",
            href="/b",
            link_type=LinkType.NAVIGATE,
            visited=False,
        ),
    ]
    rebuild_frontier_from_links(state, links, origin_url="https://ex.test/")
    assert "/b" in state.frontier
    assert "/a" not in state.frontier
