"""Application catalog APIs — cross-investigation memory."""

from fastapi import APIRouter

from api.services import investigations as svc

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
def list_applications() -> list[dict]:
    catalogs = svc.list_application_catalogs()
    return [catalog.model_dump(mode="json") for catalog in catalogs]


@router.get("/{application_key}/site-graph")
def get_application_site_graph(application_key: str) -> dict:
    return svc.get_application_site_graph(application_key)


@router.get("/{application_key}/export/clone-spec")
def export_application_clone_spec(application_key: str) -> dict:
    return svc.export_application_clone_spec(application_key)


@router.get("/{application_key}/drift")
def application_drift(
    application_key: str,
    investigation_id: str | None = None,
    version: str | None = None,
) -> dict:
    from uuid import UUID

    inv = UUID(investigation_id) if investigation_id else None
    return svc.compute_application_drift(
        application_key, investigation_id=inv, version=version
    )


@router.get("/{application_key}/role-diff")
def application_role_diff(
    application_key: str,
    left: str = "applicant",
    right: str = "recruiter",
) -> dict:
    return svc.compute_application_role_diff(application_key, left, right)


@router.get("/{application_key}/golden")
def get_golden(application_key: str, version: str | None = None) -> dict:
    return svc.get_golden_catalog(application_key, version)


@router.post("/{application_key}/golden/{version}")
def pin_golden(application_key: str, version: str) -> dict:
    return svc.pin_golden_catalog(application_key, version)


@router.get("/{application_key}")
def get_application(application_key: str) -> dict:
    catalog = svc.get_application_catalog(application_key)
    related = svc.list_investigations_for_application(application_key)
    return {
        "catalog": catalog.model_dump(mode="json"),
        "investigations": [
            {
                "id": str(item.id),
                "goal": item.goal,
                "status": item.status.value,
                "role_scope": item.role_scope,
                "target_url": item.target_url,
            }
            for item in related
        ],
    }
