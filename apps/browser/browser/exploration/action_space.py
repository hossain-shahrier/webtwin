from webtwin_core.exploration import ActionInventory, build_action_inventory
from webtwin_core.models import Observation

from browser.observer.snapshot import capture_observation


def inventory_from_page(page, investigation_id, *, spa_mode: bool = False) -> ActionInventory:
    observation = capture_observation(page, investigation_id)
    return build_action_inventory(observation, spa_mode=spa_mode)


def inventory_from_observation(
    observation: Observation,
    goal=None,
    *,
    spa_mode: bool = False,
) -> ActionInventory:
    return build_action_inventory(observation, goal=goal, spa_mode=spa_mode)
