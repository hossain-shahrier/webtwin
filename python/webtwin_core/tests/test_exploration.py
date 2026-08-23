from uuid import uuid4

from webtwin_core.exploration import (
    ActionType,
    ExplorationBudget,
    ExplorationState,
    SafetyClass,
    build_action_inventory,
    choose_first_unexplored,
    choose_max_information_gain,
    choose_random_unexplored,
    classify_action_safety,
    filter_automatable,
)
from webtwin_core.evaluation.metrics import compute_exploration_metrics
from webtwin_core.models import ElementSnapshot, Observation


def _observation(elements: list[ElementSnapshot]) -> Observation:
    return Observation(
        investigation_id=uuid4(),
        url="https://example.com/form",
        title="Form",
        elements=elements,
    )


def test_action_inventory_from_observation() -> None:
    observation = _observation(
        [
            ElementSnapshot(
                selector="#condition",
                tag="select",
                name="condition",
                options=["yes", "no"],
                visible=True,
            ),
            ElementSnapshot(selector="#reason", tag="input", name="reason", input_type="text"),
            ElementSnapshot(selector="#save", tag="button", name="save", text="Save"),
            ElementSnapshot(selector="#delete", tag="button", text="Delete Account"),
        ]
    )
    inventory = build_action_inventory(observation)
    types = {action.type for action in inventory.actions}
    assert ActionType.SELECT in types
    assert ActionType.INPUT in types
    assert ActionType.CLICK in types
    select = next(action for action in inventory.actions if action.target == "condition")
    assert select.values == ["yes", "no"]


def test_safety_classifies_destructive_and_filters() -> None:
    observation = _observation(
        [
            ElementSnapshot(selector="#delete", tag="button", text="Delete Account"),
            ElementSnapshot(selector="#expand", tag="button", text="Expand details"),
        ]
    )
    inventory = build_action_inventory(observation)
    delete = next(action for action in inventory.actions if "delete" in action.target or action.label == "Delete Account")
    expand = next(action for action in inventory.actions if action.label == "Expand details")
    assert classify_action_safety(delete) == SafetyClass.DESTRUCTIVE
    assert classify_action_safety(expand) == SafetyClass.SAFE
    automatable = filter_automatable(inventory.actions)
    assert all(action.safety == SafetyClass.SAFE for action in automatable)
    assert delete.id not in {action.id for action in automatable}


def test_first_unexplored_and_information_gain_policies() -> None:
    observation = _observation(
        [
            ElementSnapshot(
                selector="#employment_type",
                tag="select",
                name="employment_type",
                options=["permanent", "contract", "temporary"],
                value="permanent",
            )
        ]
    )
    inventory = build_action_inventory(observation)
    state = ExplorationState()
    state.sync_inventory(inventory)
    state.mark_tested(inventory.actions[0], "permanent")
    state.mark_tested(inventory.actions[0], "contract")

    first = choose_first_unexplored(state, inventory)
    assert first is not None
    assert first.value == "temporary"

    gain = choose_max_information_gain(state, inventory)
    assert gain is not None
    assert gain.value == "temporary"
    assert gain.expected_information_gain >= 1.0


def test_budget_exhaustion() -> None:
    budget = ExplorationBudget(max_actions=2, max_duration_seconds=600)
    assert not budget.exhausted()
    budget.consume_action()
    budget.consume_action()
    assert budget.exhausted()


def test_random_policy_picks_unexplored() -> None:
    import random

    observation = _observation(
        [
            ElementSnapshot(
                selector="#employment_type",
                tag="select",
                name="employment_type",
                options=["permanent", "contract", "temporary"],
            )
        ]
    )
    inventory = build_action_inventory(observation)
    state = ExplorationState()
    state.sync_inventory(inventory)
    rng = random.Random(0)
    plan = choose_random_unexplored(state, inventory, rng=rng)
    assert plan is not None
    assert plan.value in {"permanent", "contract", "temporary"}


def test_exploration_metrics() -> None:
    from webtwin_core.exploration.state import TargetCoverage

    state = ExplorationState(
        coverage={
            "employment_type": TargetCoverage(
                target="employment_type",
                possible_values=["permanent", "contract", "temporary"],
                tested_values=["permanent", "contract"],
            )
        },
        states_seen=["a", "b"],
        actions_taken=5,
    )
    metrics = compute_exploration_metrics(
        policy="information_gain",
        state=state,
        candidate_rules=2,
        verified_rules=1,
        actions_taken=5,
        safety_violations=0,
        blocked_unsafe_actions=1,
    )
    assert metrics.exploration_coverage == 0.667
    assert metrics.state_coverage == 2
    assert metrics.rules_per_action == 0.2
    assert metrics.safety_violations == 0
    assert metrics.blocked_unsafe_actions == 1
