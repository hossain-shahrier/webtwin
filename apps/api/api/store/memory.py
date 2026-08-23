from uuid import UUID

from webtwin_core.models.investigation import InvestigationTransition
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
from webtwin_core.verification.engine import VerificationRun


class MemoryStore:
    def __init__(self) -> None:
        self.investigations: dict[UUID, Investigation] = {}
        self.transitions: dict[UUID, InvestigationTransition] = {}
        self.sessions: dict[UUID, InvestigationSession] = {}
        self.observations: dict[UUID, Observation] = {}
        self.states: dict[UUID, ApplicationState] = {}
        self.events: dict[UUID, TimelineEvent] = {}
        self.evidence: dict[UUID, Evidence] = {}
        self.diffs: dict[UUID, StateDiff] = {}
        self.rules: dict[UUID, BusinessRule] = {}
        self.verification_runs: dict[UUID, VerificationRun] = {}

    def clear(self) -> None:
        self.investigations.clear()
        self.transitions.clear()
        self.sessions.clear()
        self.observations.clear()
        self.states.clear()
        self.events.clear()
        self.evidence.clear()
        self.diffs.clear()
        self.rules.clear()
        self.verification_runs.clear()
