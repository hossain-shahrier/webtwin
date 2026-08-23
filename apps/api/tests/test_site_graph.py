"""API tests for site graph endpoints."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.store import store
from webtwin_core.models import Investigation, TimelineEvent
from webtwin_core.models.events import TimelineEventType
from webtwin_core.models.observation import ElementSnapshot, Observation
from webtwin_core.models.spa import RouteSnapshot


@pytest.fixture(autouse=True)
def reset_store() -> None:
    store.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_site_graph_endpoint(client: TestClient) -> None:
    created = client.post(
        "/investigations",
        json=Investigation(
            goal="map site",
            target_url="https://example.com/",
            exploration_policy="site_map",
        ).model_dump(mode="json"),
    )
    investigation_id = UUID(created.json()["id"])
    obs = Observation(
        investigation_id=investigation_id,
        url="https://example.com/",
        title="Home",
        route=RouteSnapshot(url="https://example.com/", path="/"),
        elements=[
            ElementSnapshot(
                tag="a",
                selector="#home-about",
                value="/about",
                label="About",
                visible=True,
            )
        ],
    )
    client.post(
        f"/investigations/{investigation_id}/observations",
        json=obs.model_dump(mode="json"),
    )

    response = client.get(f"/investigations/{investigation_id}/site-graph")
    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["total_discovered"] >= 1
    assert any(edge["href"] == "/about" for edge in payload["edges"])
    assert any(node["id"] == "/about" for node in payload["nodes"])


def test_navigation_event_marks_link_visited(client: TestClient) -> None:
    created = client.post(
        "/investigations",
        json=Investigation(
            goal="map site",
            target_url="https://example.com/",
            exploration_policy="site_map",
        ).model_dump(mode="json"),
    )
    investigation_id = UUID(created.json()["id"])
    obs = Observation(
        investigation_id=investigation_id,
        url="https://example.com/",
        title="Home",
        route=RouteSnapshot(url="https://example.com/", path="/"),
        elements=[
            ElementSnapshot(
                tag="a",
                selector="#home-about",
                value="/about",
                label="About",
                visible=True,
            )
        ],
    )
    client.post(
        f"/investigations/{investigation_id}/observations",
        json=obs.model_dump(mode="json"),
    )
    before = client.post(
        f"/investigations/{investigation_id}/states",
        json={
            "investigation_id": str(investigation_id),
            "url": "https://example.com/",
            "sequence": 1,
        },
    ).json()
    after = client.post(
        f"/investigations/{investigation_id}/states",
        json={
            "investigation_id": str(investigation_id),
            "url": "https://example.com/about",
            "sequence": 2,
        },
    ).json()
    client.post(
        f"/investigations/{investigation_id}/events",
        json=TimelineEvent(
            investigation_id=investigation_id,
            type=TimelineEventType.NAVIGATE,
            description="nav a=/about href=/about",
            state_before_id=before["id"],
            state_after_id=after["id"],
        ).model_dump(mode="json"),
    )
    payload = client.get(f"/investigations/{investigation_id}/site-graph").json()
    about_edge = next(edge for edge in payload["edges"] if edge["href"] == "/about")
    assert about_edge["visited"] is True
