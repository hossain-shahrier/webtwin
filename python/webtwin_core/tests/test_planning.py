from webtwin_core.exploration.actions import ActionInventory, ActionType, ExploratoryAction, SafetyClass
from webtwin_core.exploration.state import ExplorationState
from webtwin_core.planning import resolve_planner


def test_deterministic_and_llm_planners_choose_actions() -> None:
    inventory = ActionInventory(
        url="file:///tmp/x.html",
        actions=[
            ExploratoryAction(
                type=ActionType.SELECT,
                target="condition",
                selector="#condition",
                values=["yes", "no"],
                safety=SafetyClass.SAFE,
            )
        ],
    )
    state = ExplorationState()
    state.sync_inventory(inventory)

    det = resolve_planner("information_gain")
    llm = resolve_planner("llm")
    plan_a = det.choose_next_action(state, inventory)
    plan_b = llm.choose_next_action(state, inventory)
    assert plan_a is not None
    assert plan_b is not None
    assert plan_a.action.target == "condition"
    experiments = llm.propose_experiments(state, inventory, [])
    assert experiments
    assert experiments[0].source.startswith("llm:")
