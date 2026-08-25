"""Unknown-Field Hunter — turn scorecard unknowns into a prioritized probe queue."""

from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.counterfactual import CounterfactualPlan, CounterfactualRequest, plan_counterfactual


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
    raw = (item or "").strip()
    if ":" in raw:
        screen, field = raw.split(":", 1)
        return (screen.strip() or None), field.strip()
    return None, raw


def _priority(field: str) -> float:
    lowered = field.lower()
    score = 0.4
    for token in _HIGH_SIGNAL:
        if token in lowered:
            score += 0.15
    if lowered.startswith(("btn", "nav", "menu", "footer", "header")):
        score -= 0.3
    return round(max(0.05, min(score, 1.0)), 2)


def _suggested_values(field: str) -> list[str]:
    lowered = field.lower()
    if any(token in lowered for token in ("date", "dob")):
        return ["2024-01-01", "2020-06-15", ""]
    if any(token in lowered for token in ("country", "state", "province", "type", "status")):
        return ["IT", "FR", "US", ""]
    if any(token in lowered for token in ("yes", "consent", "agree", "check")):
        return ["yes", "no", ""]
    return ["1", "yes", "test", ""]


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
        suggestions = _suggested_values(field)
        # Probe the field itself with a benign value; effect is observe-only via
        # a sibling "probe_signal" expectation placeholder (worker records DOM delta).
        plan = plan_counterfactual(
            CounterfactualRequest(
                condition_field=field,
                condition_value=suggestions[0] if suggestions else "1",
                effect_field="__observe__",
                observe_only=True,
            )
        )
        plan.description = (
            f"Probe unknown field {field!r} on {screen_id or 'current screen'} "
            f"with value {suggestions[0]!r}; record DOM/network delta only."
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
