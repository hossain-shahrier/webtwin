"""Persisted evaluation run for an investigation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.evaluation.metrics import ExplorationMetrics


class EvaluationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    policy: str = "first_unexplored"
    level: str | None = None
    exploration_coverage: float = 0.0
    state_coverage: int = 0
    actions_taken: int = 0
    candidate_rules: int = 0
    verified_rules: int = 0
    rules_per_action: float = 0.0
    safety_violations: int = 0
    blocked_unsafe_actions: int = 0
    pages_seen: int = 1
    discovery_precision: float | None = None
    discovery_recall: float | None = None
    discovery_f1: float | None = None
    verification_accuracy: float | None = None
    settle_timeouts: int = 0
    soft_nav_success_rate: float | None = None
    routes_seen: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_exploration_metrics(
        cls,
        investigation_id: UUID,
        metrics: ExplorationMetrics,
        *,
        level: str | None = None,
        discovery_precision: float | None = None,
        discovery_recall: float | None = None,
        discovery_f1: float | None = None,
        verification_accuracy: float | None = None,
    ) -> EvaluationRun:
        return cls(
            investigation_id=investigation_id,
            policy=metrics.policy,
            level=level,
            exploration_coverage=metrics.exploration_coverage,
            state_coverage=metrics.state_coverage,
            actions_taken=metrics.actions_taken,
            candidate_rules=metrics.candidate_rules,
            verified_rules=metrics.verified_rules,
            rules_per_action=metrics.rules_per_action,
            safety_violations=metrics.safety_violations,
            blocked_unsafe_actions=metrics.blocked_unsafe_actions,
            pages_seen=metrics.pages_seen,
            discovery_precision=discovery_precision,
            discovery_recall=discovery_recall,
            discovery_f1=discovery_f1,
            verification_accuracy=verification_accuracy,
        )
