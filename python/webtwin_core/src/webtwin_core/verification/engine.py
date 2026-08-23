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


class VerificationExperimentResult(BaseModel):
    experiment_id: UUID
    passed: bool
    details: str
    observation_id: UUID | None = None


class VerificationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    rule_id: UUID
    investigation_id: UUID
    status: RuleStatus
    confidence: float
    results: list[VerificationExperimentResult] = Field(default_factory=list)


def _alternate_value(value: str) -> str | None:
    pairs = {"yes": "no", "no": "yes", "true": "false", "false": "true"}
    lowered = value.lower()
    return pairs.get(lowered)


def generate_verification_experiments(rule: BusinessRule) -> list[VerificationExperiment]:
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

    experiments.append(
        VerificationExperiment(
            rule_id=rule.id,
            description=f"When {trigger}={trigger_value}, {effect_field} should match rule effect",
            set_fields={trigger: trigger_value},
            expectations={effect_field: effect_expectation},
        )
    )

    alternate = _alternate_value(trigger_value)
    if alternate is not None:
        inverted = dict(effect_expectation)
        if "visible" in inverted:
            inverted["visible"] = not inverted["visible"]
        if "required" in inverted:
            inverted["required"] = False
        experiments.append(
            VerificationExperiment(
                rule_id=rule.id,
                description=f"When {trigger}={alternate}, {effect_field} should not match rule effect",
                set_fields={trigger: alternate},
                expectations={effect_field: inverted},
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
            return False, f"Field {field_name} not found in observation"

        for attribute, expected_value in expected.items():
            actual_value = getattr(actual, attribute)
            if actual_value != expected_value:
                return False, (
                    f"{field_name}.{attribute}: expected {expected_value!r}, got {actual_value!r}"
                )

    return True, "Expectations met"


def observation_to_state(observation: Observation, sequence: int) -> ApplicationState:
    return observation.to_application_state(sequence=sequence)


def summarize_verification(
    rule: BusinessRule, results: list[VerificationExperimentResult]
) -> VerificationRun:
    passed = sum(1 for result in results if result.passed)
    total = len(results)

    if total == 0:
        status = RuleStatus.CANDIDATE
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
