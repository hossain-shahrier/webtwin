from webtwin_core.models import (
    ApplicationState,
    FieldState,
    compute_state_diff,
    infer_candidate_rules,
)


def test_compute_state_diff_detects_visibility_change() -> None:
    investigation_id = __import__("uuid").uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        fields=[
            FieldState(name="condition", value="yes", visible=True),
            FieldState(name="reason", value=None, visible=False, required=False),
        ],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        fields=[
            FieldState(name="condition", value="no", visible=True),
            FieldState(name="reason", value=None, visible=True, required=True),
        ],
    )

    diff = compute_state_diff(before, after)
    assert any(change.field == "reason" and change.attribute == "visible" for change in diff.changes)
    assert any(change.field == "condition" and change.attribute == "value" for change in diff.changes)

    rules = infer_candidate_rules(diff, before, after)
    assert len(rules) >= 1
    assert "reason" in rules[0].name


def test_infer_rules_from_spa_appeared_fields() -> None:
    investigation_id = __import__("uuid").uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        fields=[
            FieldState(name="employment_type", value="permanent", visible=True),
        ],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        fields=[
            FieldState(name="employment_type", value="contract", visible=True),
            FieldState(name="end_date", value=None, visible=True, required=True),
        ],
    )
    diff = compute_state_diff(before, after)
    assert any(change.attribute == "appeared" and change.field == "end_date" for change in diff.changes)
    rules = infer_candidate_rules(diff, before, after)
    assert any(rule.effect.field == "end_date" and rule.condition.field == "employment_type" for rule in rules)


def test_infer_ignores_nav_link_appeared_noise() -> None:
    investigation_id = __import__("uuid").uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        fields=[FieldState(name="username", value="", visible=True)],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        fields=[
            FieldState(name="username", value="alice", visible=True),
            FieldState(name='a[href="/agency-management/create"]', value="/agency-management/create", visible=True),
        ],
    )
    diff = compute_state_diff(before, after)
    rules = infer_candidate_rules(diff, before, after)
    assert not any("agency-management" in rule.effect.field for rule in rules)
