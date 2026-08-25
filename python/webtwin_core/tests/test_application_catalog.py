from uuid import uuid4

from webtwin_core.reference_system.catalog import (
    ApplicationCatalog,
    RoleSystemMap,
    merge_domain_entities,
    upsert_catalog_from_run,
)
from webtwin_core.reference_system.entities import DomainEntity, EntityFieldRef
from webtwin_core.reference_system.identity import (
    application_key_for,
    normalize_role_scope,
)


def test_application_key_from_host_and_name() -> None:
    assert application_key_for("https://www.Example.com/apply") == "example.com"
    assert (
        application_key_for("https://example.com/app", application_name="Polito Apply")
        == "example.com:polito-apply"
    )


def test_application_key_for_file_urls_and_guards() -> None:
    key = application_key_for("file:///tmp/fixtures/level_01/form.html")
    assert key.startswith("file:")
    assert "unknown" not in key
    assert application_key_for("http://127.0.0.1:3000/app") == "localhost"
    assert application_key_for("http://localhost:8080/x") == "localhost"
    # Guard against accidental Investigation object passthrough
    class Fake:
        target_url = "https://acme.test/jobs"

    assert application_key_for(Fake()) == "acme.test"  # type: ignore[arg-type]


def test_normalize_role_scope() -> None:
    assert normalize_role_scope(None) == "default"
    assert normalize_role_scope("Applicant") == "applicant"


def test_upsert_catalog_merges_roles_and_entities() -> None:
    applicant_id = uuid4()
    recruiter_id = uuid4()
    address = DomainEntity(
        name="Address",
        confidence=0.7,
        field_count=2,
        fields=[
            EntityFieldRef(field="country", label="Country", screen_id="/apply"),
            EntityFieldRef(field="province", label="Province", screen_id="/apply"),
        ],
        rule_names=["country reveals province"],
        screen_ids=["/apply"],
    )
    employment = DomainEntity(
        name="Employment",
        confidence=0.6,
        field_count=1,
        fields=[EntityFieldRef(field="job_title", label="Title", screen_id="/jobs")],
        screen_ids=["/jobs"],
    )

    catalog = upsert_catalog_from_run(
        None,
        application_key="example.com",
        application_name="Demo ATS",
        host="example.com",
        investigation_id=applicant_id,
        entities=[address],
        role_map=RoleSystemMap(
            role_scope="applicant",
            screen_count=1,
            entity_names=["Address"],
            flow_names=["Address flow"],
            verified_rule_names=["country reveals province"],
            investigation_ids=[applicant_id],
            summary="applicant map",
        ),
    )
    catalog = upsert_catalog_from_run(
        catalog,
        application_key="example.com",
        application_name="Demo ATS",
        host="example.com",
        investigation_id=recruiter_id,
        entities=[employment, address],
        role_map=RoleSystemMap(
            role_scope="recruiter",
            screen_count=2,
            entity_names=["Employment"],
            flow_names=["Employment flow"],
            verified_rule_names=[],
            investigation_ids=[recruiter_id],
            summary="recruiter map",
        ),
    )

    assert isinstance(catalog, ApplicationCatalog)
    assert set(catalog.roles.keys()) == {"applicant", "recruiter"}
    assert len(catalog.investigation_ids) == 2
    names = {entity.name for entity in catalog.entities}
    assert names == {"Address", "Employment"}
    address_entity = next(entity for entity in catalog.entities if entity.name == "Address")
    assert "country reveals province" in address_entity.rule_names
    assert address_entity.field_count >= 2


def test_merge_domain_entities_unions_fields() -> None:
    left = [
        DomainEntity(
            name="Contact",
            fields=[EntityFieldRef(field="email", screen_id="/a")],
            field_count=1,
            rule_names=["r1"],
        )
    ]
    right = [
        DomainEntity(
            name="Contact",
            fields=[EntityFieldRef(field="phone", screen_id="/b")],
            field_count=1,
            rule_names=["r2"],
        )
    ]
    merged = merge_domain_entities(left, right)
    assert len(merged) == 1
    assert {ref.field for ref in merged[0].fields} == {"email", "phone"}
    assert set(merged[0].rule_names) == {"r1", "r2"}
