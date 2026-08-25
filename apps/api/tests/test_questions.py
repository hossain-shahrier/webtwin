from webtwin_core.models import (
    BusinessRule,
    Evidence,
    RuleCondition,
    RuleEffect,
    RuleStatus,
)
from webtwin_core.models.evidence import EvidenceType

from api.services import investigations as svc
from api.store import store


def test_ask_question_with_citations() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="test", target_url="file:///tmp/x.html")
    )
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "condition shows reason", "path": "/form"},
    )
    store.evidence[evidence.id] = evidence
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition affects reason visibility",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.85,
        status=RuleStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    store.rules[rule.id] = rule

    answer = svc.ask_question(investigation.id, "Why does reason appear?")
    assert answer.refused is False
    assert answer.citations[0].rule_id == rule.id
    assert answer.citations[0].evidence_summary == "condition shows reason"
    assert answer.citations[0].screen_path == "/form"


def test_ask_question_refuses_without_evidence() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="refuse test", target_url="https://example.com/form")
    )
    answer = svc.ask_question(investigation.id, "Why does unicorn_field appear?")
    assert answer.refused is True
    assert answer.confidence == 0.0


def test_ask_question_refuses_unrelated_even_with_rules() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="refuse unrelated", target_url="https://example.com/form")
    )
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "condition shows reason"},
    )
    store.evidence[evidence.id] = evidence
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition affects reason visibility",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.9,
        status=RuleStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    store.rules[rule.id] = rule

    answer = svc.ask_question(investigation.id, "Why does unicorn_xyz appear?")
    assert answer.refused is True
    assert answer.confidence == 0.0


def test_export_cursor_context_includes_verified_rules() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="export test", target_url="https://example.com/app")
    )
    evidence = Evidence(
        investigation_id=investigation.id,
        type=EvidenceType.DOM,
        payload={"summary": "condition shows reason"},
    )
    store.evidence[evidence.id] = evidence
    rule = BusinessRule(
        investigation_id=investigation.id,
        name="condition affects reason visibility",
        condition=RuleCondition(field="condition", operator="equals", value="no"),
        effect=RuleEffect(field="reason", visible=True),
        confidence=0.95,
        status=RuleStatus.VERIFIED,
        evidence_ids=[evidence.id],
    )
    store.rules[rule.id] = rule

    payload = svc.export_cursor_context(investigation.id)
    assert "WebTwin AI context" in payload["markdown"]
    assert "condition affects reason visibility" in payload["markdown"]
    assert len(payload["verified_rules"]) == 1
    assert payload["ai_spec_url"].endswith("/export/ai-spec")
    assert "prompt-capsules" in payload["markdown"]
    assert payload["prompt_capsules_url"].endswith("/export/prompt-capsules")
    assert "Reference system overview" not in payload["markdown"]
    assert "Negative space" in payload["markdown"]

    capsules = svc.export_prompt_capsules(investigation.id)
    assert len(capsules["capsules"]) == 1
    assert "Required evidence" in capsules["markdown"]

    absences = svc.list_absences(investigation.id)
    assert absences["count"] >= 1
    assert absences["absences"][0]["condition_value"] == "yes"

    plan = svc.plan_counterfactual_experiment(
        investigation.id,
        {
            "condition_field": "condition",
            "condition_value": "yes",
            "effect_field": "reason",
            "expect_visible": False,
        },
    )
    assert plan["hypothesized_absence"] is True
    assert plan["status"] == "planned"


def test_export_ai_spec_is_compact() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="ai export", target_url="https://example.com/app")
    )
    payload = svc.export_ai_spec(investigation.id)
    assert "WebTwin AI context" in payload["markdown"]
    assert "routes" in payload
    assert "interactions" in payload
    assert payload["full_clone_spec_url"].endswith("/export/clone-spec")


def test_get_clone_scorecard() -> None:
    store.clear()
    from webtwin_core.models import Investigation

    investigation = svc.create_investigation(
        Investigation(goal="scorecard", target_url="https://example.com/form")
    )
    scorecard = svc.get_clone_scorecard(investigation.id)
    assert scorecard["verified_rules"] == 0
    assert scorecard["clone_ready"] is False
