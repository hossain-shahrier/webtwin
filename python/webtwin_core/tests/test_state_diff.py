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


def test_infer_ignores_visit_nav_actions_and_bare_anchor() -> None:
    """Catalog nav actions (visit_*) and bare `a` must not become candidate rules."""
    investigation_id = __import__("uuid").uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        fields=[
            FieldState(name="visit_product_category_hoodie", value=None, visible=True),
            FieldState(name="visit_product_category_co-ord_set_male", value=None, visible=False),
            FieldState(name="login", value=None, visible=True),
            FieldState(name="a", value=None, visible=False),
        ],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        fields=[
            FieldState(
                name="visit_product_category_hoodie",
                value="https://gorurghash.com/product-category/men/hoodie-men/",
                visible=True,
            ),
            FieldState(name="visit_product_category_co-ord_set_male", value=None, visible=True),
            FieldState(name="login", value=None, visible=True),
            FieldState(name="a", value=None, visible=True),
        ],
    )
    diff = compute_state_diff(before, after)
    rules = infer_candidate_rules(diff, before, after)
    assert not any("visit_" in rule.name for rule in rules)
    assert not any(rule.effect.field == "a" for rule in rules)
    assert not any(rule.condition.field.startswith("visit_") for rule in rules)


def test_infer_does_not_treat_unavailable_as_nav_chrome() -> None:
    """Substring 'nav' must not match field names like 'unavailable'."""
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
            FieldState(name="unavailable_reason", value=None, visible=True, required=True),
        ],
    )
    diff = compute_state_diff(before, after)
    rules = infer_candidate_rules(diff, before, after)
    assert any(rule.effect.field == "unavailable_reason" for rule in rules)


def test_infer_ignores_url_valued_triggers() -> None:
    investigation_id = __import__("uuid").uuid4()
    before = ApplicationState(
        investigation_id=investigation_id,
        sequence=1,
        fields=[FieldState(name="category_picker", value="", visible=True)],
    )
    after = ApplicationState(
        investigation_id=investigation_id,
        sequence=2,
        fields=[
            FieldState(
                name="category_picker",
                value="https://shop.example/product-category/men/",
                visible=True,
            ),
            FieldState(name="size", value=None, visible=True),
        ],
    )
    diff = compute_state_diff(before, after)
    rules = infer_candidate_rules(diff, before, after)
    assert not any(rule.condition.field == "category_picker" for rule in rules)
