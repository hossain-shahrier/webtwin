"""Unknown-Field Hunter — turn scorecard unknowns into a prioritized probe queue."""

from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.counterfactual import CounterfactualRequest, CounterfactualPlan, plan_counterfactual


class ProbeItem(BaseModel):
    screen_id: str | None = None
    field: str
    priority: float = 0.0
    reason: str = ""
    suggested_values: list[str] = Field(default_factory=list)
    plan: CounterfactualPlan | None = None


class ProbeQueue(BaseModel):
    investigation_id: str
    items: list[ProbeItem] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


_HIGH_SIGNAL = (
    "date",
    "type",
    "status",
    "country",
    "state",
    "province",
    "role",
    "consent",
    "agree",
    "email",
    "phone",
    "amount",
    "quantity",
)


def _parse_unknown(item: str) -> tuple[str | None, str]:
    if ":" in item:
        screen, field = item.split(":", 1)
        return screen or None, field
    return None, item


def _priority(field: str) -> float:
    lowered = field.lower()
    score = 0.4
    for token in _HIGH_SIGNAL:
        if token in lowered:
            score += 0.15
    if lowered.startswith(("btn", "nav", "menu", "footer", "header")):
        score -= 0.3
    return round(max(0.05, min(score, 1.0)), 2)


def build_probe_queue(
    investigation_id: str,
    unexplored_fields: list[str],
    *,
    max_items: int = 25,
) -> ProbeQueue:
    items: list[ProbeItem] = []
    for raw in unexplored_fields:
        screen_id, field = _parse_unknown(raw)
        if not field:
            continue
        priority = _priority(field)
        suggestions = ["", "1", "yes", "test"]
        # Plan a visibility probe (observe whether anything appears — hypothesis only)
        plan = plan_counterfactual(
            CounterfactualRequest(
                condition_field=field,
                condition_value="yes",
                effect_field=field,
                expect_visible=True,
            )
        )
        items.append(
            ProbeItem(
                screen_id=screen_id,
                field=field,
                priority=priority,
                reason="Visible during exploration but never used in a rule condition/effect.",
                suggested_values=suggestions,
                plan=plan,
            )
        )
    items.sort(key=lambda item: (-item.priority, item.field))
    return ProbeQueue(
        investigation_id=investigation_id,
        items=items[:max_items],
        guidance=[
            "Work the queue top-down; each probe should become evidence or be marked inert.",
            "Do not invent rules from probes that did not change DOM/network state.",
            "After probing, re-export Clone Spec and recompute scorecard unknowns.",
        ],
    )
