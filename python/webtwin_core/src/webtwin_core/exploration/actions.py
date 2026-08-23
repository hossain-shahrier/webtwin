from __future__ import annotations

from enum import StrEnum
from urllib.parse import urljoin, urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.investigation import InvestigationGoal
from webtwin_core.models.observation import ElementSnapshot, Observation


class ActionType(StrEnum):
    SELECT = "select"
    INPUT = "input"
    CLICK = "click"
    NAVIGATE = "navigate"
    ROUTE = "route"
    SCROLL = "scroll"


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
    if element.text:
        return element.text.lower().replace(" ", "_")[:48]
    return element.selector.lstrip("#")


def _same_origin(base_url: str, href: str) -> bool:
    if href.startswith("javascript:"):
        return False
    if href.startswith("#"):
        return True
    absolute = urljoin(base_url, href)
    base = urlparse(base_url)
    target = urlparse(absolute)
    if absolute.startswith("file:") or base.scheme == "file":
        return True
    return base.netloc == target.netloc


_SKIP_HREF_TOKENS = (
    "mailto:",
    "tel:",
    "javascript:",
    "/login",
    "/signin",
    "/sign-in",
    "/logout",
    "idp.",
    "sso.",
    ".pdf",
    ".zip",
    ".doc",
)


def _should_skip_href(href: str) -> bool:
    lowered = href.lower()
    return any(token in lowered for token in _SKIP_HREF_TOKENS)


def _locale_prefix(url: str) -> str:
    path = urlparse(url).path or "/"
    parts = [p for p in path.split("/") if p]
    if parts and len(parts[0]) in {2, 5} and parts[0].replace("-", "").isalpha():
        return f"/{parts[0]}"
    return ""


def _navigate_priority(base_url: str, absolute: str) -> int:
    """Lower is better: same locale + shallow hubs over deep news articles."""
    base_prefix = _locale_prefix(base_url)
    target = urlparse(absolute)
    path = target.path or "/"
    score = 0
    if base_prefix and not path.startswith(base_prefix):
        score += 50
    depth = len([p for p in path.split("/") if p])
    score += max(0, depth - 2) * 3
    if target.query:
        score += 5
    if any(token in path.lower() for token in ("news", "poliflash", "comunicazione", "press")):
        score += 8
    return score


def build_action_inventory(
    observation: Observation,
    goal: InvestigationGoal | None = None,
    *,
    spa_mode: bool = False,
) -> ActionInventory:
    """Derive candidate actions from an observation — no LLM."""
    actions: list[ExploratoryAction] = []
    scope = (goal.scope or "").lower() if goal else ""

    for element in observation.elements:
        if not element.visible or not element.enabled:
            continue
        target = element.stable_key or _target_name(element)
        if element.tag == "a" and element.value:
            href = element.value
            if href.startswith("javascript:") or _should_skip_href(href):
                continue
            if not _same_origin(observation.url, href):
                continue
            absolute = href if href.startswith("#") else urljoin(observation.url, href)
            soft = spa_mode and (
                href.startswith("#") or href.startswith("/") or bool(element.testid)
            )
            if soft:
                actions.append(
                    ExploratoryAction(
                        type=ActionType.ROUTE,
                        target=target or href,
                        selector=element.selector,
                        values=[absolute],
                        label=element.text or element.label,
                        metadata={
                            "href": href,
                            "nav": "soft",
                            "priority": str(_navigate_priority(observation.url, absolute)),
                        },
                    )
                )
            elif href.startswith("#"):
                continue
            else:
                absolute_nav = urljoin(observation.url, href)
                actions.append(
                    ExploratoryAction(
                        type=ActionType.NAVIGATE,
                        target=target or href,
                        selector=element.selector,
                        values=[absolute_nav],
                        label=element.text or element.label,
                        metadata={
                            "href": href,
                            "priority": str(_navigate_priority(observation.url, absolute_nav)),
                        },
                    )
                )
            continue
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
            if input_type in {"hidden", "submit", "button", "reset", "file", "password"}:
                continue
            actions.append(
                ExploratoryAction(
                    type=ActionType.INPUT,
                    target=target,
                    selector=element.selector,
                    label=element.label,
                    metadata={
                        "input_type": input_type,
                        "goal_relevant": str(bool(scope and scope in target.lower())),
                    },
                )
            )
        elif element.tag == "button" or (
            element.tag == "input" and (element.input_type or "").lower() in {"submit", "button"}
        ):
            label_l = (element.text or element.label or "").lower()
            safety = SafetyClass.SAFE
            if any(token in label_l for token in ("delete", "remove", "destroy")):
                safety = SafetyClass.DESTRUCTIVE
            elif any(token in label_l for token in ("submit", "save", "send", "pay", "login", "sign in")):
                safety = SafetyClass.CAUTION
            elif any(token in label_l for token in ("accept", "cookie", "consent")):
                continue
            actions.append(
                ExploratoryAction(
                    type=ActionType.CLICK,
                    target=target or (element.text or "button").lower().replace(" ", "_"),
                    selector=element.selector,
                    label=element.text or element.label,
                    safety=safety,
                )
            )

    if spa_mode:
        actions.append(
            ExploratoryAction(
                type=ActionType.SCROLL,
                target="viewport",
                selector="body",
                values=["down"],
                label="scroll down",
                metadata={"nav": "scroll"},
            )
        )

    def _sort_key(action: ExploratoryAction) -> tuple:
        scope_miss = 0 if scope and scope in action.target.lower() else 1
        if action.type in {ActionType.NAVIGATE, ActionType.ROUTE}:
            try:
                priority = int(action.metadata.get("priority", "99"))
            except ValueError:
                priority = 99
            return (scope_miss, 1, priority, action.target)
        if action.type == ActionType.SELECT:
            return (scope_miss, 0, 0, action.target)
        return (scope_miss, 2, 0, action.target)

    actions.sort(key=_sort_key)
    return ActionInventory(url=observation.url, actions=actions)
