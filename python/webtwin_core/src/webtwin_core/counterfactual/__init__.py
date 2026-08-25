"""Counterfactual Form Lab — plan controlled experiments without inventing outcomes."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.verification.engine import VerificationExperiment


class CounterfactualRequest(BaseModel):
    condition_field: str
    condition_value: str
    effect_field: str
    expect_visible: bool | None = None
    expect_required: bool | None = None
    expect_enabled: bool | None = None
    setup_fields: dict[str, str] = Field(default_factory=dict)
    operator: str = "equals"


class CounterfactualPlan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID | None = None
    description: str
    experiment: VerificationExperiment
    hypothesized_absence: bool = False
    guidance: list[str] = Field(default_factory=list)
    status: str = "planned"
    note: str = (
        "Plan only — run via browser verification worker to obtain evidence. "
        "Do not treat this hypothesis as a verified rule."
    )


def plan_counterfactual(
    request: CounterfactualRequest,
    *,
    investigation_id: UUID | None = None,
    rule_id: UUID | None = None,
) -> CounterfactualPlan:
    """Build a single controlled experiment from a what-if question."""
    expectations: dict[str, dict[str, Any]] = {}
    effect_bits: dict[str, Any] = {}
    if request.expect_visible is not None:
        effect_bits["visible"] = request.expect_visible
    if request.expect_required is not None:
        effect_bits["required"] = request.expect_required
    if request.expect_enabled is not None:
        effect_bits["enabled"] = request.expect_enabled
    if not effect_bits:
        # Default probe: observe visibility after setting the value (assert present or absent later)
        effect_bits["visible"] = True
    expectations[request.effect_field] = effect_bits

    set_fields = dict(request.setup_fields or {})
    if request.operator == "clicked":
        set_fields[request.condition_field] = "__click__"
        description = (
            f"Counterfactual: click {request.condition_field}, "
            f"observe {request.effect_field} → {effect_bits}"
        )
    else:
        set_fields[request.condition_field] = request.condition_value
        description = (
            f"Counterfactual: when {request.condition_field}={request.condition_value!r}, "
            f"observe {request.effect_field} → {effect_bits}"
        )

    experiment = VerificationExperiment(
        rule_id=rule_id or uuid4(),
        description=description,
        set_fields=set_fields,
        expectations=expectations,
    )
    hypothesized_absence = request.expect_visible is False
    guidance = [
        "Execute this experiment on the live page before updating Clone Spec.",
        "If expectations fail, record contradiction — do not invent a passing rule.",
    ]
    if hypothesized_absence:
        guidance.append(
            "On pass, promote to Negative Space (assert_never) with the experiment evidence id."
        )
    else:
        guidance.append(
            "On pass, promote to a verified candidate rule with linked evidence."
        )

    return CounterfactualPlan(
        investigation_id=investigation_id,
        description=description,
        experiment=experiment,
        hypothesized_absence=hypothesized_absence,
        guidance=guidance,
    )
