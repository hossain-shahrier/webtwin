"""Evidence-bound prompt capsules for Cursor — refuse capsules without citations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule, Evidence
from webtwin_core.negative_space import AbsenceAssertion, derive_absences_from_rules
from webtwin_core.privacy import redact_mapping


class PromptCapsule(BaseModel):
    id: str
    title: str
    rule_id: str
    status: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    condition_field: str
    condition_operator: str
    condition_value: str | bool | int | float | None = None
    effect_field: str
    effect_visible: bool | None = None
    effect_required: bool | None = None
    effect_enabled: bool | None = None
    condition_selector: str | None = None
    effect_selector: str | None = None
    setup_fields: dict[str, str] = Field(default_factory=dict)
    test_scenario: str = ""
    related_absences: list[AbsenceAssertion] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    evidence_summaries: list[str] = Field(default_factory=list)
    prompt_markdown: str = ""


class CapsuleExport(BaseModel):
    investigation_id: str
    capsules: list[PromptCapsule] = Field(default_factory=list)
    skipped_without_evidence: list[str] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


def _evidence_summary(evidence: Evidence) -> str:
    payload = evidence.payload or {}
    summary = payload.get("summary") or payload.get("description") or evidence.type.value
    text = str(summary)[:160]
    return f"`{evidence.id}` — {text}"


def _build_prompt(capsule: PromptCapsule) -> str:
    lines = [
        f"# WebTwin Prompt Capsule: {capsule.title}",
        "",
        "Implement this rule exactly. Do not invent related behavior.",
        "",
        "## Rule",
        f"- id: `{capsule.rule_id}`",
        f"- status: **{capsule.status}** (confidence={capsule.confidence})",
        f"- when `{capsule.condition_field}` {capsule.condition_operator} "
        f"{capsule.condition_value!r}",
        f"- then `{capsule.effect_field}` "
        f"visible={capsule.effect_visible} required={capsule.effect_required} "
        f"enabled={capsule.effect_enabled}",
    ]
    if capsule.condition_selector or capsule.effect_selector:
        lines.extend(
            [
                "",
                "## Selectors",
                f"- condition: `{capsule.condition_selector or '—'}`",
                f"- effect: `{capsule.effect_selector or '—'}`",
            ]
        )
    if capsule.setup_fields:
        lines.append("")
        lines.append("## Setup (preconditions)")
        for key, value in capsule.setup_fields.items():
            lines.append(f"- `{key}` = {value!r}")
    lines.extend(["", "## Test scenario", capsule.test_scenario or "_none_"])
    lines.extend(["", "## Required evidence (must cite)"])
    if capsule.evidence_summaries:
        for item in capsule.evidence_summaries:
            lines.append(f"- {item}")
    else:
        for eid in capsule.evidence_ids:
            lines.append(f"- `{eid}`")
    if capsule.related_absences:
        lines.extend(["", "## Related absences (assert_never)"])
        for absence in capsule.related_absences:
            lines.append(
                f"- when `{absence.condition_field}`={absence.condition_value!r}, "
                f"never `{absence.effect_field}.{absence.assert_attribute}"
                f"={not absence.assert_value}`"
            )
    lines.extend(["", "## Forbidden"])
    for item in capsule.forbidden:
        lines.append(f"- {item}")
    return "\n".join(lines)


def build_prompt_capsules(
    investigation_id: UUID,
    rules: list[BusinessRule],
    evidence: list[Evidence],
    *,
    absences: list[AbsenceAssertion] | None = None,
    verified_only: bool = True,
) -> CapsuleExport:
    evidence_by_id = {item.id: item for item in evidence}
    derived = absences if absences is not None else derive_absences_from_rules(rules)
    capsules: list[PromptCapsule] = []
    skipped: list[str] = []

    for rule in rules:
        if verified_only and rule.status.value != "verified":
            continue
        if not rule.evidence_ids:
            skipped.append(rule.name)
            continue
        resolved = [evidence_by_id[eid] for eid in rule.evidence_ids if eid in evidence_by_id]
        if not resolved:
            skipped.append(rule.name)
            continue

        related = [
            item
            for item in derived
            if item.source_rule_id == str(rule.id)
            or (
                item.effect_field == rule.effect.field
                and item.condition_field == rule.condition.field
            )
        ]
        setup = redact_mapping(rule.setup_fields)
        capsule = PromptCapsule(
            id=f"capsule:{rule.id}",
            title=rule.name,
            rule_id=str(rule.id),
            status=rule.status.value,
            confidence=rule.confidence,
            evidence_ids=[str(eid) for eid in rule.evidence_ids],
            condition_field=rule.condition.field,
            condition_operator=rule.condition.operator,
            condition_value=rule.condition.value,
            effect_field=rule.effect.field,
            effect_visible=rule.effect.visible,
            effect_required=rule.effect.required,
            effect_enabled=rule.effect.enabled,
            condition_selector=rule.condition_selector,
            effect_selector=rule.effect_selector,
            setup_fields=setup,
            test_scenario=(
                f"Given {rule.condition.field} {rule.condition.operator} "
                f"{rule.condition.value!r}, expect {rule.effect.field} "
                f"visible={rule.effect.visible}"
            ),
            related_absences=related,
            forbidden=[
                "Do not invent visibility/required/enabled for other field values without evidence.",
                "Do not drop assert_never absences listed in this capsule.",
                "Do not claim network/API contracts not cited in evidence.",
            ],
            evidence_summaries=[_evidence_summary(item) for item in resolved[:5]],
        )
        capsule.prompt_markdown = _build_prompt(capsule)
        capsules.append(capsule)

    return CapsuleExport(
        investigation_id=str(investigation_id),
        capsules=capsules,
        skipped_without_evidence=skipped,
        guidance=[
            "Only implement capsules that include resolvable evidence IDs.",
            "Treat related absences as hard constraints.",
            "If a capsule was skipped for missing evidence, investigate before coding.",
        ],
    )


def format_capsules_bundle_markdown(export: CapsuleExport) -> str:
    lines = [
        "# WebTwin Prompt Capsules",
        "",
        f"- Investigation: `{export.investigation_id}`",
        f"- Capsules: {len(export.capsules)}",
        f"- Skipped (no evidence): {len(export.skipped_without_evidence)}",
        "",
        "## Guidance",
    ]
    for item in export.guidance:
        lines.append(f"- {item}")
    for capsule in export.capsules:
        lines.extend(["", "---", "", capsule.prompt_markdown])
    if export.skipped_without_evidence:
        lines.extend(["", "## Skipped without evidence"])
        for name in export.skipped_without_evidence:
            lines.append(f"- {name}")
    return "\n".join(lines)
