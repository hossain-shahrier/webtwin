from webtwin_core.exploration import ActionInventory, build_action_inventory
from webtwin_core.models import Observation

from browser.observer.snapshot import capture_observation


def inventory_from_page(page, investigation_id) -> ActionInventory:
    observation = capture_observation(page, investigation_id)
    return build_action_inventory(observation)


def inventory_from_observation(observation: Observation) -> ActionInventory:
    return build_action_inventory(observation)
