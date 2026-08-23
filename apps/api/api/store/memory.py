from uuid import UUID

from webtwin_core.evaluation.runs import EvaluationRun
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
from webtwin_core.reference_system.catalog import ApplicationCatalog
from api.store.catalog_store import CatalogStore
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
        self.evaluation_runs: dict[UUID, EvaluationRun] = {}
        self.network_events: dict[UUID, dict] = {}
        self.workflows: dict[UUID, dict] = {}
        self.application_catalogs: dict[str, ApplicationCatalog] = {}
        self.discovered_links: dict[UUID, object] = {}
        self.investigation_claims: dict[UUID, str] = {}
        self.auth_form_submissions: dict[UUID, object] = {}
        self.catalog_store = CatalogStore(memory=self.application_catalogs)
        for catalog in self.catalog_store.list_all():
            self.application_catalogs[catalog.application_key] = catalog

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
        self.evaluation_runs.clear()
        self.network_events.clear()
        self.workflows.clear()
        self.application_catalogs.clear()
        self.discovered_links.clear()
        self.investigation_claims.clear()
        self.auth_form_submissions.clear()
