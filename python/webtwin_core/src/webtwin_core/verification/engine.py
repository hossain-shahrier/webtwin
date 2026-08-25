from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.observation import Observation
from webtwin_core.models.rule_status import RuleStatus
from webtwin_core.models.rules import BusinessRule, RuleCondition, RuleEffect
from webtwin_core.models.state import ApplicationState, FieldState


class VerificationExperiment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    rule_id: UUID
    description: str
    set_fields: dict[str, str] = Field(default_factory=dict)
    expectations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    network_expectations: dict[str, Any] = Field(default_factory=dict)
    kind: str = "positive"  # positive | absence | reapply | attribute


class VerificationExperimentResult(BaseModel):
    experiment_id: UUID
    passed: bool
    details: str
    observation_id: UUID | None = None
    inconclusive: bool = False


class VerificationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    rule_id: UUID
    investigation_id: UUID
    status: RuleStatus
    confidence: float
    results: list[VerificationExperimentResult] = Field(default_factory=list)


def _alternate_value(value: str, options: list[str] | None = None) -> str | None:
    pairs = {
        "yes": "no",
        "no": "yes",
        "true": "false",
        "false": "true",
        "1": "0",
        "0": "1",
        "on": "off",
        "off": "on",
    }
    lowered = value.lower()
    if lowered in pairs:
        return pairs[lowered]
    if options:
        others = [option for option in options if option != value and option != ""]
        if others:
            return others[0]
    return None


def generate_verification_experiments(
    rule: BusinessRule,
    *,
    alternate_options: list[str] | None = None,
    require_network: bool = False,
) -> list[VerificationExperiment]:
    experiments: list[VerificationExperiment] = []
    trigger = rule.condition.field
    trigger_value = str(rule.condition.value)
    effect_field = rule.effect.field
    effect_expectation: dict[str, Any] = {}
    if rule.effect.visible is not None:
        effect_expectation["visible"] = rule.effect.visible
    if rule.effect.required is not None:
        effect_expectation["required"] = rule.effect.required
    if rule.effect.enabled is not None:
        effect_expectation["enabled"] = rule.effect.enabled

    setup = {key: str(value) for key, value in (rule.setup_fields or {}).items()}

    if rule.condition.operator == "clicked":
        set_fields = dict(setup)
        set_fields[trigger] = "__click__"
        network_expectations = {"min_events": 1} if require_network else {}
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"When {trigger} is clicked, {effect_field} should match rule effect",
                set_fields=set_fields,
                expectations={effect_field: effect_expectation},
                network_expectations=network_expectations,
            )
        )
        return experiments

    positive_fields = dict(setup)
    positive_fields[trigger] = trigger_value
    experiments.append(
        VerificationExperiment(
            rule_id=rule.id,
            description=f"When {trigger}={trigger_value}, {effect_field} should match rule effect",
            set_fields=positive_fields,
            expectations={effect_field: effect_expectation},
        )
    )

    alternate = _alternate_value(trigger_value, alternate_options)
    if alternate is not None:
        # Soft negative: only invert visibility when exclusivity is binary (yes/no pairs).
        # Do NOT invent required=False — that falsely contradicts sticky required fields.
        inverted: dict[str, Any] = {}
        binary_pair = trigger_value.lower() in {"yes", "no", "true", "false", "0", "1", "on", "off"}
        if binary_pair and "visible" in effect_expectation:
            inverted["visible"] = not effect_expectation["visible"]
        if inverted:
            alt_fields = dict(setup)
            alt_fields[trigger] = alternate
            experiments.append(
                VerificationExperiment(
                    rule_id=rule.id,
                    description=(
                        f"When {trigger}={alternate}, {effect_field} should not match "
                        f"claimed exclusive effect"
                    ),
                    set_fields=alt_fields,
                    expectations={effect_field: inverted},
                    kind="absence",
                )
            )
    elif rule.effect.visible is True and not setup:
        # Clear only when no setup context (avoids wiping precondition dates)
        clear_fields = dict(setup)
        clear_fields[trigger] = ""
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"When {trigger} is cleared, {effect_field} should not stay visible",
                set_fields=clear_fields,
                expectations={effect_field: {"visible": False}},
                kind="absence",
            )
        )

    if rule.condition.operator == "equals" and trigger_value and alternate is None:
        reapply = dict(setup)
        reapply[trigger] = trigger_value
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"Re-apply {trigger}={trigger_value} — {effect_field} should match again",
                set_fields=reapply,
                expectations={effect_field: effect_expectation},
                kind="reapply",
            )
        )

    if rule.effect.required is not None:
        req_fields = dict(setup)
        req_fields[trigger] = trigger_value
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"Required state for {effect_field} when {trigger}={trigger_value}",
                set_fields=req_fields,
                expectations={effect_field: {"required": rule.effect.required}},
                kind="attribute",
            )
        )

    if rule.effect.enabled is not None:
        en_fields = dict(setup)
        en_fields[trigger] = trigger_value
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"Enabled state for {effect_field} when {trigger}={trigger_value}",
                set_fields=en_fields,
                expectations={effect_field: {"enabled": rule.effect.enabled}},
                kind="attribute",
            )
        )

    return experiments

def _field_from_state(state: ApplicationState, field_name: str) -> FieldState | None:
    for field in state.fields:
        if field.name == field_name:
            return field
    return None


def evaluate_expectations(state: ApplicationState, expectations: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    for field_name, expected in expectations.items():
        actual = _field_from_state(state, field_name)
        if actual is None:
            # Missing DOM node ≈ not visible / not required (SPA remounts, hide rules)
            actual = FieldState(name=field_name, visible=False, enabled=False, required=False)

        for attribute, expected_value in expected.items():
            actual_value = getattr(actual, attribute)
            if actual_value != expected_value:
                return False, (
                    f"{field_name}.{attribute}: expected {expected_value!r}, got {actual_value!r}"
                )

    return True, "Expectations met"


def evaluate_network_expectations(
    events: list[dict[str, Any]],
    expectations: dict[str, Any],
) -> tuple[bool, str]:
    if not expectations:
        return True, "No network expectations"
    min_events = int(expectations.get("min_events") or 0)
    if len(events) < min_events:
        return False, f"Expected at least {min_events} network events, got {len(events)}"
    return True, "Network expectations met"


def observation_to_state(observation: Observation, sequence: int) -> ApplicationState:
    return observation.to_application_state(sequence=sequence)


def summarize_verification(
    rule: BusinessRule, results: list[VerificationExperimentResult]
) -> VerificationRun:
    decisive = [result for result in results if not result.inconclusive]
    passed = sum(1 for result in decisive if result.passed)
    total = len(decisive)

    if total == 0:
        # Only inconclusive (e.g. budget) — do not contradict
        status = RuleStatus.UNDER_VERIFICATION
        confidence = rule.confidence
    elif passed == total:
        status = RuleStatus.VERIFIED
        confidence = 0.95
    elif passed == 0:
        status = RuleStatus.CONTRADICTED
        confidence = 0.2
    else:
        status = RuleStatus.UNDER_VERIFICATION
        confidence = round(rule.confidence * (passed / total), 2)

    return VerificationRun(
        rule_id=rule.id,
        investigation_id=rule.investigation_id,
        status=status,
        confidence=confidence,
        results=results,
    )
