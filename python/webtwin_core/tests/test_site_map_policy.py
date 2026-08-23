"""Multi-page HTML fixture for site graph BFS tests."""

from pathlib import Path
from uuid import uuid4

from uuid import uuid4

import pytest

from webtwin_core.exploration.policy import choose_site_map_action
from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.reference_system.site_graph import extract_discovered_links, LinkType
from webtwin_core.models.observation import ElementSnapshot, Observation
from webtwin_core.models.spa import RouteSnapshot


FIXTURE = Path(__file__).resolve().parents[2] / "tests/evaluation/synthetic_ats/fixtures/site_graph"


def _link_obs(path: str, targets: list[str]) -> Observation:
    base = "https://fixture.test"
    return Observation(
        investigation_id=uuid4(),
        url=f"{base}{path}",
        title="Fixture",
        route=RouteSnapshot(url=f"{base}{path}", path=path),
        elements=[
            ElementSnapshot(tag="a", selector=f"#{index}", value=href, label=href, visible=True)
            for index, href in enumerate(targets)
        ],
    )


def test_multi_page_link_inventory():
    home = _link_obs("/", ["/page-a", "/page-b"])
    page_a = _link_obs("/page-a", ["/page-c"])
    home_links = extract_discovered_links(home, origin_url=home.url)
    a_links = extract_discovered_links(page_a, origin_url=page_a.url)
    assert len([link for link in home_links if link.link_type != LinkType.EXTERNAL]) == 2
    assert len(a_links) == 1
    assert a_links[0].to_screen_id == "/page-c"


def test_site_map_policy_follows_frontier():
    state = ExplorationState(url="https://fixture.test/")
    state.enqueue_frontier_from_links(
        extract_discovered_links(_link_obs("/", ["/page-a", "/page-b"]), origin_url="https://fixture.test/"),
        origin_url="https://fixture.test/",
    )
    inventory = ActionInventory(
        url="https://fixture.test/",
        actions=[
            ExploratoryAction(
                id=uuid4(),
                key="nav:/page-a",
                type=ActionType.NAVIGATE,
                target="nav:/page-a",
                selector="a[href='/page-a']",
                values=["https://fixture.test/page-a"],
                metadata={"href": "/page-a"},
            ),
            ExploratoryAction(
                id=uuid4(),
                key="nav:/page-b",
                type=ActionType.NAVIGATE,
                target="nav:/page-b",
                selector="a[href='/page-b']",
                values=["https://fixture.test/page-b"],
                metadata={"href": "/page-b"},
            ),
        ],
    )
    plan = choose_site_map_action(state, inventory)
    assert plan is not None
    assert plan.value is not None
    assert "/page-a" in plan.value
    assert plan.frontier_target == "/page-a"
    assert "/page-a" in state.frontier
    state.remove_from_frontier(plan.frontier_target)
    assert "/page-a" not in state.frontier
    assert "/page-b" in state.frontier
