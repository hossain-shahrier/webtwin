from pydantic import BaseModel, Field

from webtwin_core.models.rules import RuleCondition, RuleEffect


class ExpectedRule(BaseModel):
    id: str
    condition: RuleCondition
    effect: RuleEffect


class BenchmarkLevel(BaseModel):
    level: str
    name: str
    fixture: str
    rules: list[ExpectedRule] = Field(default_factory=list)


class DiscoveryMetrics(BaseModel):
    expected_rules: int
    discovered_rules: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0


class VerificationMetrics(BaseModel):
    candidate_rules: int
    verified_rules: int
    contradicted_rules: int
    verification_accuracy: float = 0.0
    false_verification_rate: float = 0.0


class EvaluationMetrics(BaseModel):
    level: str
    discovery: DiscoveryMetrics
    verification: VerificationMetrics
    actions_taken: int = 0
    rules_per_action: float = 0.0
    exploration: "ExplorationMetrics | None" = None


class ExplorationMetrics(BaseModel):
    policy: str
    exploration_coverage: float = 0.0
    state_coverage: int = 0
    actions_taken: int = 0
    candidate_rules: int = 0
    verified_rules: int = 0
    rules_per_action: float = 0.0
    safety_violations: int = 0
    blocked_unsafe_actions: int = 0
    pages_seen: int = 1


def _rule_signature(condition: RuleCondition, effect: RuleEffect) -> tuple[str, str, str, str | None]:
    return (
        condition.field,
        str(condition.value),
        effect.field,
        str(effect.visible) if effect.visible is not None else None,
    )


def match_rules(expected: ExpectedRule, discovered: ExpectedRule) -> bool:
    return _rule_signature(expected.condition, expected.effect) == _rule_signature(
        discovered.condition, discovered.effect
    )


def compute_discovery_metrics(expected: list[ExpectedRule], discovered: list[ExpectedRule]) -> DiscoveryMetrics:
    expected_sigs = {_rule_signature(r.condition, r.effect) for r in expected}
    discovered_sigs = {_rule_signature(r.condition, r.effect) for r in discovered}

    true_positives = len(expected_sigs & discovered_sigs)
    false_positives = len(discovered_sigs - expected_sigs)
    false_negatives = len(expected_sigs - discovered_sigs)

    precision = true_positives / len(discovered_sigs) if discovered_sigs else 0.0
    recall = true_positives / len(expected_sigs) if expected_sigs else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return DiscoveryMetrics(
        expected_rules=len(expected),
        discovered_rules=len(discovered),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1_score=round(f1, 3),
    )


def compute_verification_metrics(
    candidates: int,
    verified: int,
    contradicted: int,
) -> VerificationMetrics:
    accuracy = verified / candidates if candidates else 0.0
    false_rate = contradicted / candidates if candidates else 0.0
    return VerificationMetrics(
        candidate_rules=candidates,
        verified_rules=verified,
        contradicted_rules=contradicted,
        verification_accuracy=round(accuracy, 3),
        false_verification_rate=round(false_rate, 3),
    )


def compute_exploration_metrics(
    *,
    policy: str,
    state,
    candidate_rules: int,
    verified_rules: int,
    actions_taken: int,
    safety_violations: int = 0,
    blocked_unsafe_actions: int = 0,
    pages_seen: int = 1,
) -> ExplorationMetrics:
    return ExplorationMetrics(
        policy=policy,
        exploration_coverage=state.exploration_coverage(),
        state_coverage=state.state_coverage(),
        actions_taken=actions_taken,
        candidate_rules=candidate_rules,
        verified_rules=verified_rules,
        rules_per_action=round(verified_rules / actions_taken, 3) if actions_taken else 0.0,
        safety_violations=safety_violations,
        blocked_unsafe_actions=blocked_unsafe_actions,
        pages_seen=pages_seen,
    )


def compute_metrics(
    level: str,
    expected: list[ExpectedRule],
    discovered: list[ExpectedRule],
    verified: list[ExpectedRule],
    contradicted: int,
    actions_taken: int,
    exploration: ExplorationMetrics | None = None,
) -> EvaluationMetrics:
    discovery = compute_discovery_metrics(expected, discovered)
    verification = compute_verification_metrics(
        candidates=len(discovered),
        verified=len(verified),
        contradicted=contradicted,
    )

    return EvaluationMetrics(
        level=level,
        discovery=discovery,
        verification=verification,
        actions_taken=actions_taken,
        rules_per_action=round(len(verified) / actions_taken, 3) if actions_taken else 0.0,
        exploration=exploration,
    )
