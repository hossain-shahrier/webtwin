from __future__ import annotations

from typing import Protocol
from uuid import UUID

from webtwin_core.evaluation.runs import EvaluationRun
from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    Evidence,
    Investigation,
    InvestigationSession,
    Observation,
    StateDiff,
    TimelineEvent,
)
from webtwin_core.models.investigation import InvestigationTransition
from webtwin_core.verification.engine import VerificationRun


class EntityMap(Protocol):
    def __getitem__(self, key: UUID): ...

    def get(self, key: UUID, default=None): ...

    def __setitem__(self, key: UUID, value) -> None: ...

    def __contains__(self, key: object) -> bool: ...

    def values(self): ...


class Store(Protocol):
    investigations: EntityMap
    transitions: EntityMap
    sessions: EntityMap
    observations: EntityMap
    states: EntityMap
    events: EntityMap
    evidence: EntityMap
    diffs: EntityMap
    rules: EntityMap
    verification_runs: EntityMap
    evaluation_runs: EntityMap
    workflows: EntityMap
    network_events: EntityMap

    def clear(self) -> None: ...
