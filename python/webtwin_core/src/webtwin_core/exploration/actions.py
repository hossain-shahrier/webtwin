from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.observation import ElementSnapshot, Observation


class ActionType(StrEnum):
    SELECT = "select"
    INPUT = "input"
    CLICK = "click"
    NAVIGATE = "navigate"


class SafetyClass(StrEnum):
    SAFE = "safe"
    CAUTION = "caution"
    DESTRUCTIVE = "destructive"


class ExploratoryAction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: ActionType
    target: str
    selector: str
    values: list[str] = Field(default_factory=list)
    label: str | None = None
    safety: SafetyClass = SafetyClass.SAFE
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.type.value}:{self.target}"


class ActionInventory(BaseModel):
    url: str
    actions: list[ExploratoryAction] = Field(default_factory=list)

    def for_target(self, target: str) -> list[ExploratoryAction]:
        return [action for action in self.actions if action.target == target]


def _target_name(element: ElementSnapshot) -> str:
    if element.name:
        return element.name
    if element.label:
        return element.label.lower().replace(" ", "_")
    return element.selector.lstrip("#")


def build_action_inventory(observation: Observation) -> ActionInventory:
    """Derive candidate actions from an observation — no LLM."""
    actions: list[ExploratoryAction] = []
    for element in observation.elements:
        if not element.visible or not element.enabled:
            continue
        target = _target_name(element)
        if element.tag == "select":
            actions.append(
                ExploratoryAction(
                    type=ActionType.SELECT,
                    target=target,
                    selector=element.selector,
                    values=list(element.options),
                    label=element.label,
                )
            )
        elif element.tag in {"input", "textarea"}:
            input_type = (element.input_type or "text").lower()
            if input_type in {"hidden", "submit", "button", "reset", "file"}:
                continue
            actions.append(
                ExploratoryAction(
                    type=ActionType.INPUT,
                    target=target,
                    selector=element.selector,
                    label=element.label,
                    metadata={"input_type": input_type},
                )
            )
        elif element.tag == "button" or (element.tag == "input" and (element.input_type or "").lower() in {"submit", "button"}):
            actions.append(
                ExploratoryAction(
                    type=ActionType.CLICK,
                    target=target or (element.text or "button").lower().replace(" ", "_"),
                    selector=element.selector,
                    label=element.text or element.label,
                )
            )
    return ActionInventory(url=observation.url, actions=actions)
