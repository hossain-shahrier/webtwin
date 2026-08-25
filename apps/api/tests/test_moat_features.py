from uuid import uuid4

from webtwin_core.models import (
    BusinessRule,
    Evidence,
    Investigation,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.models.evidence import EvidenceType
from webtwin_core.reference_system.catalog import ApplicationCatalog, RoleSystemMap

from api.services import investigations as svc
from api.store import store


def test_moat_exports_drift_contracts_hunter_role_diff_tapes() -> None:
    store.clear()
    unique = uuid4().hex[:8]
    investigation = svc.create_investigation(
        Investigation(
            goal="moat",
            target_url=f"https://moat-{unique}.example.com/form",
            application_name=f"Demo ATS {unique}",
            role_scope="applicant",
        )
    )
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "condition shows reason"},
    )
    store.evidence[evidence.id] = evidence
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition shows reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        evidence_ids=[evidence.id],
        setup_fields={"prep": "1"},
    )
    store.rules[rule.id] = rule

    # Seed catalog + golden for drift / role-diff
    key = investigation.application_key
    assert key
    catalog = ApplicationCatalog(
        application_key=key,
        application_name=f"Demo ATS {unique}",
        roles={
            "applicant": RoleSystemMap(
                role_scope="applicant",
                verified_rule_names=["condition shows reason"],
                entity_names=["Form"],
                screen_count=1,
            ),
            "recruiter": RoleSystemMap(
                role_scope="recruiter",
                verified_rule_names=["other rule"],
                entity_names=["Job"],
                screen_count=2,
            ),
        },
    )
    store.application_catalogs[key] = catalog
    store.catalog_store.save(catalog)
    store.catalog_store.pin_golden(key, "v1", catalog)

    contracts = svc.export_contract_pack(investigation.id)
    assert contracts["rule_count"] == 1
    assert "test_contract_" in contracts["files"][0]["content"]

    drift = svc.compute_investigation_drift(investigation.id, "v1")
    assert drift["freshness_pct"] == 1.0
    assert any(item["rule_name"] == "condition shows reason" for item in drift["still_verified"])
    assert "Drift Report" in drift["markdown"]

    hunter = svc.get_unknown_hunter_queue(investigation.id)
    assert "items" in hunter
    assert "guidance" in hunter

    tapes = svc.get_action_tapes(investigation.id)
    assert tapes["count"] >= 1
    assert store.rules[rule.id].restore_tape or tapes["tapes"]

    role_diff = svc.compute_application_role_diff(key, "applicant", "recruiter")
    assert "condition shows reason" in role_diff["left_only_verified_rules"]
    assert "Role Diff" in role_diff["markdown"]
