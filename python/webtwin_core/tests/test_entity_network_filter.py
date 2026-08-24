"""Entity and network filter tests."""

from webtwin_core.reference_system.entities import (
    match_entity_from_route,
    match_entity_name,
    merge_entity_maps,
)
from webtwin_core.reference_system.network_filter import is_relevant_api_url


def test_match_entity_from_route_job_seeker_not_employment() -> None:
    assert match_entity_from_route("/job-seeker-management/edit/123") == "JobSeeker"
    assert match_entity_from_route("/company-management/edit/456") == "Company"
    assert match_entity_from_route("/task-management") == "Task"
    assert match_entity_from_route("/agency-management") == "Agency"


def test_match_entity_name_prefers_route_over_lexicon() -> None:
    assert (
        match_entity_name("job", route_path="/job-seeker-management/edit/1")
        == "JobSeeker"
    )
    assert match_entity_name("position", route_path="/task-management") == "Task"


def test_merge_entity_maps_dedupes_field_names() -> None:
    from webtwin_core.reference_system.entities import EntityFieldRef

    entities = merge_entity_maps(
        [
            {
                "JobSeeker": [
                    EntityFieldRef(field="first_name", screen_id="/job-seeker-management/edit/1"),
                    EntityFieldRef(field="first_name", screen_id="/job-seeker-management/edit/2"),
                    EntityFieldRef(field="email", screen_id="/job-seeker-management/edit/1"),
                ]
            }
        ]
    )
    assert len(entities) == 1
    assert entities[0].field_count == 2
    assert {ref.field for ref in entities[0].fields} == {"first_name", "email"}


def test_is_relevant_api_url_filters_vite_assets() -> None:
    assert is_relevant_api_url("http://localhost:3001/src/components/ui/dropdown-menu.tsx") is False
    assert is_relevant_api_url("http://localhost:3001/@vite/client") is False
    assert is_relevant_api_url("https://api.example.com/users/123") is True
    assert is_relevant_api_url("http://localhost:3001/api/v1/companies") is True
