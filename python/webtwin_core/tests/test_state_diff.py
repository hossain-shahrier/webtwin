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
