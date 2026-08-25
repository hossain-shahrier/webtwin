from uuid import uuid4

from webtwin_core.contracts import build_contract_pack
from webtwin_core.drift import compute_drift_report
from webtwin_core.hunter import build_probe_queue
from webtwin_core.models import BusinessRule, RuleCondition, RuleEffect, RuleStatus
from webtwin_core.models.events import TimelineEvent, TimelineEventType
from webtwin_core.reference_system.catalog import ApplicationCatalog, RoleSystemMap
from webtwin_core.role_diff import compute_role_diff
from webtwin_core.wizard import attach_restore_tapes, build_restore_tape_for_rule, timeline_to_steps


def test_drift_freshness_and_broken() -> None:
    inv = uuid4()
    golden = {
        "version": "v1",
        "catalog": {
            "roles": {
                "applicant": {
                    "verified_rule_names": ["condition shows reason", "gone rule"],
                }
            }
        },
    }
    live = [
        BusinessRule(
            investigation_id=inv,
            name="condition shows reason",
            condition=RuleCondition(field="condition", operator="equals", value="no"),
            effect=RuleEffect(field="reason", visible=True),
            status=RuleStatus.VERIFIED,
            confidence=0.95,
        ),
        BusinessRule(
            investigation_id=inv,
            name="gone rule",
            condition=RuleCondition(field="a", operator="equals", value="1"),
            effect=RuleEffect(field="b", visible=True),
            status=RuleStatus.CONTRADICTED,
            confidence=0.2,
        ),
        BusinessRule(
            investigation_id=inv,
            name="brand new",
            condition=RuleCondition(field="x", operator="equals", value="1"),
            effect=RuleEffect(field="y", visible=True),
            status=RuleStatus.VERIFIED,
            confidence=0.9,
        ),
    ]
    report = compute_drift_report(
        application_key="example.com",
        golden=golden,
        live_rules=live,
        investigation_id=inv,
    )
    assert report.freshness_pct == 0.5
    assert len(report.still_verified) == 1
    assert len(report.broken) == 1
    assert len(report.new_verified) == 1


def test_contract_pack_contains_pytest() -> None:
    inv = uuid4()
    rule = BusinessRule(
        investigation_id=inv,
        name="condition shows reason",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.95,
        condition_selector="#condition",
        effect_selector="#reason",
    )
    pack = build_contract_pack(inv, "https://example.com/form", [rule])
    assert pack.rule_count == 1
    content = pack.files[0].content
    assert "def test_contract_" in content
    assert "to_be_visible" in content
    assert "TARGET_URL" in content


def test_probe_queue_prioritizes_signal_fields() -> None:
    queue = build_probe_queue(
        str(uuid4()),
        [" /form:country", "/form:nav_footer", "/apply:start_date"],
    )
    assert queue.items
    assert queue.items[0].field in {"country", "start_date"}


def test_role_diff_exclusive_rules() -> None:
    catalog = ApplicationCatalog(
        application_key="ats.example",
        roles={
            "applicant": RoleSystemMap(
                role_scope="applicant",
                entity_names=["Address"],
                verified_rule_names=["country shows province"],
                flow_names=["Apply"],
                screen_count=2,
            ),
            "recruiter": RoleSystemMap(
                role_scope="recruiter",
                entity_names=["Job"],
                verified_rule_names=["status unlocks hire"],
                flow_names=["Hire"],
                screen_count=3,
            ),
        },
    )
    diff = compute_role_diff(catalog, "applicant", "recruiter")
    assert "country shows province" in diff.left_only_verified_rules
    assert "status unlocks hire" in diff.right_only_verified_rules
    assert diff.screen_count_delta == 1


def test_wizard_restore_tape_from_timeline_and_setup() -> None:
    inv = uuid4()
    events = [
        TimelineEvent(
            investigation_id=inv,
            type=TimelineEventType.NAVIGATE,
            description="Opened https://example.com/step1",
        ),
        TimelineEvent(
            investigation_id=inv,
            type=TimelineEventType.SELECT,
            description="Set start_date=2024-01-10",
        ),
        TimelineEvent(
            investigation_id=inv,
            type=TimelineEventType.SELECT,
            description="Set end_date=2024-01-05",
        ),
    ]
    assert len(timeline_to_steps(events)) == 3
    rule = BusinessRule(
        investigation_id=inv,
        name="submit shows validation_error",
        condition=RuleCondition(field="submit", operator="clicked", value=True),
        effect=RuleEffect(field="validation_error", visible=True),
        setup_fields={"start_date": "2024-01-10", "end_date": "2024-01-05"},
    )
    tape = build_restore_tape_for_rule(rule, events)
    assert tape.steps
    assert any(step.field == "start_date" for step in tape.steps)
    enriched = attach_restore_tapes([rule], events)[0]
    assert enriched.restore_tape
    assert enriched.cross_screen is True
