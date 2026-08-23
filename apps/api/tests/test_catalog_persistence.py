"""Catalog persistence tests (file-backed store survives process restart)."""

from uuid import uuid4

from webtwin_core.models import Investigation, InvestigationStatus
from webtwin_core.reference_system.catalog import ApplicationCatalog, RoleSystemMap
from webtwin_core.reference_system.entities import DomainEntity, EntityFieldRef


def test_catalog_store_file_persistence(tmp_path, monkeypatch) -> None:
    from api.store.catalog_store import CatalogStore

    monkeypatch.setattr("api.store.catalog_store.Path.home", lambda: tmp_path)
    store_a = CatalogStore(memory={})
    inv_id = uuid4()
    catalog = ApplicationCatalog(
        application_key="demo.example",
        application_name="Demo",
        entities=[
            DomainEntity(
                name="Address",
                field_count=1,
                fields=[EntityFieldRef(field="country", screen_id="/apply")],
            )
        ],
        roles={
            "applicant": RoleSystemMap(
                role_scope="applicant",
                screen_count=1,
                entity_names=["Address"],
                investigation_ids=[inv_id],
            )
        },
        investigation_ids=[inv_id],
    )
    store_a.save(catalog)

    store_b = CatalogStore(memory={})
    loaded = store_b.get("demo.example")
    assert loaded is not None
    assert loaded.application_name == "Demo"
    assert "Address" in {entity.name for entity in loaded.entities}


def test_pin_golden_catalog(tmp_path, monkeypatch) -> None:
    from api.store.catalog_store import CatalogStore

    monkeypatch.setattr("api.store.catalog_store.Path.home", lambda: tmp_path)
    store = CatalogStore(memory={})
    catalog = ApplicationCatalog(application_key="app.test", application_name="Test")
    store.save(catalog)
    golden = store.pin_golden("app.test", "v1", catalog)
    assert golden["version"] == "v1"
    loaded = store.get_golden("app.test", "v1")
    assert loaded is not None
    assert loaded["catalog"]["application_key"] == "app.test"


def test_catalog_merge_survives_simulated_restart(tmp_path, monkeypatch) -> None:
    """Two store instances simulate API restart — catalog must persist."""
    from api.store.catalog_store import CatalogStore

    monkeypatch.setattr("api.store.catalog_store.Path.home", lambda: tmp_path)
    inv_a = uuid4()
    inv_b = uuid4()
    store_a = CatalogStore(memory={})
    catalog = ApplicationCatalog(
        application_key="merge.test",
        roles={
            "admin": RoleSystemMap(role_scope="admin", investigation_ids=[inv_a]),
            "recruiter": RoleSystemMap(role_scope="recruiter", investigation_ids=[inv_b]),
        },
        investigation_ids=[inv_a, inv_b],
    )
    store_a.save(catalog)

    store_b = CatalogStore(memory={})
    reloaded = store_b.get("merge.test")
    assert reloaded is not None
    assert set(reloaded.roles.keys()) == {"admin", "recruiter"}
    assert len(reloaded.investigation_ids) == 2
