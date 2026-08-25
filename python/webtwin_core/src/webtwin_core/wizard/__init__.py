"""Wizard Causality Replay — restore action tapes before verification experiments."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule
from webtwin_core.models.events import TimelineEvent, TimelineEventType

_SET_RE = re.compile(r"^Set\s+([^=]+)=(.*)$")
_OPEN_RE = re.compile(r"^Opened\s+(.+)$")


class ActionTapeStep(BaseModel):
    action: str  # navigate | set | click | route
    field: str | None = None
    value: str | None = None
    url: str | None = None
    event_id: str | None = None
    description: str = ""


class ActionTape(BaseModel):
    investigation_id: str
    rule_id: str | None = None
    steps: list[ActionTapeStep] = Field(default_factory=list)
    cross_screen: bool = False


def timeline_to_steps(events: list[TimelineEvent]) -> list[ActionTapeStep]:
    steps: list[ActionTapeStep] = []
    for event in events:
        description = event.description or ""
        set_match = _SET_RE.match(description)
        if set_match:
            field = set_match.group(1).strip()
            value = set_match.group(2)
            action = "click" if value == "__click__" else "set"
            steps.append(
                ActionTapeStep(
                    action=action,
                    field=field,
                    value=value,
                    event_id=str(event.id),
                    description=description,
                )
            )
            continue
        open_match = _OPEN_RE.match(description)
        if open_match or event.type in {TimelineEventType.NAVIGATE, TimelineEventType.ROUTE}:
            url = open_match.group(1).strip() if open_match else description
            steps.append(
                ActionTapeStep(
                    action="navigate",
                    url=url,
                    event_id=str(event.id),
                    description=description,
                )
            )
    return steps


def build_restore_tape_for_rule(
    rule: BusinessRule,
    events: list[TimelineEvent],
    *,
    max_steps: int = 12,
) -> ActionTape:
    """Build a minimal restore tape: setup_fields + recent sets leading to the rule context."""
    steps = timeline_to_steps(events)
    # Prefer explicit setup_fields from inference
    tape_steps: list[ActionTapeStep] = []
    for field, value in (rule.setup_fields or {}).items():
        if field == rule.condition.field:
            continue
        tape_steps.append(
            ActionTapeStep(
                action="click" if value == "__click__" else "set",
                field=field,
                value=str(value),
                description=f"setup {field}={value}",
            )
        )

    # Append recent distinct field sets from timeline (excluding the condition itself last)
    seen_fields = {step.field for step in tape_steps}
    for step in reversed(steps):
        if len(tape_steps) >= max_steps:
            break
        if step.action == "navigate":
            # Keep at most one leading navigate
            if any(item.action == "navigate" for item in tape_steps):
                continue
            tape_steps.insert(0, step)
            continue
        if not step.field or step.field in seen_fields:
            continue
        if step.field == rule.condition.field and step.value == str(rule.condition.value):
            continue
        seen_fields.add(step.field)
        tape_steps.append(step)

    # Chronological: navigates first, then sets in discovery order
    navigates = [step for step in tape_steps if step.action == "navigate"]
    others = [step for step in tape_steps if step.action != "navigate"]
    ordered = navigates[:1] + others[: max_steps - len(navigates[:1])]
    cross_screen = any(step.action == "navigate" for step in ordered)
    return ActionTape(
        investigation_id=str(rule.investigation_id),
        rule_id=str(rule.id),
        steps=ordered,
        cross_screen=cross_screen,
    )


def attach_restore_tapes(
    rules: list[BusinessRule],
    events: list[TimelineEvent],
) -> list[BusinessRule]:
    """Return copies of rules with restore_tape populated when empty."""
    updated: list[BusinessRule] = []
    for rule in rules:
        if rule.restore_tape:
            updated.append(rule)
            continue
        tape = build_restore_tape_for_rule(rule, events)
        data = rule.model_dump()
        data["restore_tape"] = [step.model_dump() for step in tape.steps]
        data["cross_screen"] = tape.cross_screen
        updated.append(BusinessRule.model_validate(data))
    return updated
