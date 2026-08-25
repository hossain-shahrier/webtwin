from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

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
from webtwin_core.models.rule_status import RuleStatus
from api.store.catalog_store import CatalogStore
from webtwin_core.reference_system.catalog import ApplicationCatalog

from api.db import mappers
from api.db.schema import (
    ApplicationCatalogRow,
    ApplicationStateRow,
    EvaluationRunRow,
    EvidenceRow,
    ExperimentRow,
    InvestigationRow,
    InvestigationTransitionRow,
    NetworkEventRow,
    ObservationRow,
    DiscoveredLinkRow,
    RuleEvidenceRow,
    RuleExperimentRow,
    RuleRow,
    SessionRow,
    StateTransitionRow,
    TimelineEventRow,
    WorkflowRow,
)


class PostgresStore:
    """Persistent store matching MemoryStore's dict-shaped surface for the API router."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.investigations = _EntityMap(self, "investigation")
        self.transitions = _EntityMap(self, "transition")
        self.sessions = _EntityMap(self, "session")
        self.observations = _EntityMap(self, "observation")
        self.states = _EntityMap(self, "state")
        self.events = _EntityMap(self, "event")
        self.evidence = _EntityMap(self, "evidence")
        self.diffs = _EntityMap(self, "diff")
        self.rules = _EntityMap(self, "rule")
        self.verification_runs = _EntityMap(self, "experiment")
        self.evaluation_runs = _EntityMap(self, "evaluation_run")
        self.workflows = _EntityMap(self, "workflow")
        self.network_events = _EntityMap(self, "network_event")
        self.discovered_links = _EntityMap(self, "discovered_link")
        self.investigation_claims: dict[UUID, str] = {}
        self.investigation_claim_at: dict[UUID, object] = {}
        self.audit_events: dict[UUID, object] = {}
        self.auth_form_submissions: dict[UUID, object] = {}
        # Process-local catalog cache + durable catalog store
        self.application_catalogs: dict[str, ApplicationCatalog] = {}
        self.catalog_store = CatalogStore(
            session_factory=session_factory,
            memory=self.application_catalogs,
        )
        for catalog in self.catalog_store.list_all():
            self.application_catalogs[catalog.application_key] = catalog

    def clear(self) -> None:
        self.application_catalogs.clear()
        self.investigation_claims.clear()
        self.investigation_claim_at.clear()
        self.audit_events.clear()
        self.auth_form_submissions.clear()
        with self._session_factory() as session:
            for table in (
                NetworkEventRow,
                DiscoveredLinkRow,
                WorkflowRow,
                EvaluationRunRow,
                RuleExperimentRow,
                RuleEvidenceRow,
                ExperimentRow,
                RuleRow,
                EvidenceRow,
                StateTransitionRow,
                TimelineEventRow,
                ApplicationStateRow,
                ObservationRow,
                InvestigationTransitionRow,
                SessionRow,
                ApplicationCatalogRow,
                InvestigationRow,
            ):
                session.execute(delete(table))
            session.commit()

    def _get(self, kind: str, entity_id: UUID):
        with self._session_factory() as session:
            return self._load(session, kind, entity_id)

    def _set(self, kind: str, entity_id: UUID, value) -> None:
        with self._session_factory() as session:
            self._upsert(session, kind, entity_id, value)
            session.commit()

    def _contains(self, kind: str, entity_id: UUID) -> bool:
        return self._get(kind, entity_id) is not None

    def _values(self, kind: str) -> list:
        with self._session_factory() as session:
            return self._load_all(session, kind)

    def _load(self, session: Session, kind: str, entity_id: UUID):
        if kind == "investigation":
            row = session.get(InvestigationRow, entity_id)
            return mappers.investigation_from_row(row) if row else None
        if kind == "transition":
            row = session.get(InvestigationTransitionRow, entity_id)
            return mappers.transition_from_row(row) if row else None
        if kind == "session":
            row = session.get(SessionRow, entity_id)
            return mappers.session_from_row(row) if row else None
        if kind == "observation":
            row = session.scalar(
                select(ObservationRow)
                .where(ObservationRow.id == entity_id)
                .options(selectinload(ObservationRow.elements), selectinload(ObservationRow.forms))
            )
            return mappers.observation_from_row(row) if row else None
        if kind == "state":
            row = session.scalar(
                select(ApplicationStateRow)
                .where(ApplicationStateRow.id == entity_id)
                .options(selectinload(ApplicationStateRow.fields))
            )
            return mappers.state_from_row(row) if row else None
        if kind == "event":
            row = session.get(TimelineEventRow, entity_id)
            return mappers.event_from_row(row) if row else None
        if kind == "evidence":
            row = session.get(EvidenceRow, entity_id)
            return mappers.evidence_from_row(row) if row else None
        if kind == "diff":
            row = session.scalar(
                select(StateTransitionRow)
                .where(StateTransitionRow.id == entity_id)
                .options(selectinload(StateTransitionRow.changes))
            )
            return mappers.diff_from_row(row) if row else None
        if kind == "rule":
            row = session.get(RuleRow, entity_id)
            if row is None:
                return None
            evidence_ids = list(
                session.scalars(select(RuleEvidenceRow.evidence_id).where(RuleEvidenceRow.rule_id == entity_id))
            )
            experiment_ids = list(
                session.scalars(select(RuleExperimentRow.experiment_id).where(RuleExperimentRow.rule_id == entity_id))
            )
            return mappers.rule_from_row(row, evidence_ids, experiment_ids)
        if kind == "experiment":
            row = session.scalar(
                select(ExperimentRow)
                .where(ExperimentRow.id == entity_id)
                .options(selectinload(ExperimentRow.results))
            )
            return mappers.experiment_from_row(row) if row else None
        if kind == "evaluation_run":
            row = session.get(EvaluationRunRow, entity_id)
            return mappers.evaluation_run_from_row(row) if row else None
        if kind == "workflow":
            row = session.get(WorkflowRow, entity_id)
            return mappers.workflow_from_row(row) if row else None
        if kind == "network_event":
            row = session.get(NetworkEventRow, entity_id)
            return mappers.network_event_from_row(row) if row else None
        if kind == "discovered_link":
            row = session.get(DiscoveredLinkRow, entity_id)
            return mappers.discovered_link_from_row(row) if row else None
        raise KeyError(kind)

    def _load_all(self, session: Session, kind: str) -> list:
        if kind == "investigation":
            return [mappers.investigation_from_row(row) for row in session.scalars(select(InvestigationRow))]
        if kind == "transition":
            return [
                mappers.transition_from_row(row)
                for row in session.scalars(select(InvestigationTransitionRow))
            ]
        if kind == "session":
            return [mappers.session_from_row(row) for row in session.scalars(select(SessionRow))]
        if kind == "observation":
            rows = session.scalars(
                select(ObservationRow).options(
                    selectinload(ObservationRow.elements), selectinload(ObservationRow.forms)
                )
            )
            return [mappers.observation_from_row(row) for row in rows]
        if kind == "state":
            rows = session.scalars(
                select(ApplicationStateRow).options(selectinload(ApplicationStateRow.fields))
            )
            return [mappers.state_from_row(row) for row in rows]
        if kind == "event":
            return [mappers.event_from_row(row) for row in session.scalars(select(TimelineEventRow))]
        if kind == "evidence":
            return [mappers.evidence_from_row(row) for row in session.scalars(select(EvidenceRow))]
        if kind == "diff":
            rows = session.scalars(
                select(StateTransitionRow).options(selectinload(StateTransitionRow.changes))
            )
            return [mappers.diff_from_row(row) for row in rows]
        if kind == "rule":
            rules = []
            for row in session.scalars(select(RuleRow)):
                evidence_ids = list(
                    session.scalars(select(RuleEvidenceRow.evidence_id).where(RuleEvidenceRow.rule_id == row.id))
                )
                experiment_ids = list(
                    session.scalars(
                        select(RuleExperimentRow.experiment_id).where(RuleExperimentRow.rule_id == row.id)
                    )
                )
                rules.append(mappers.rule_from_row(row, evidence_ids, experiment_ids))
            return rules
        if kind == "experiment":
            rows = session.scalars(select(ExperimentRow).options(selectinload(ExperimentRow.results)))
            return [mappers.experiment_from_row(row) for row in rows]
        if kind == "evaluation_run":
            return [
                mappers.evaluation_run_from_row(row)
                for row in session.scalars(select(EvaluationRunRow))
            ]
        if kind == "workflow":
            return [mappers.workflow_from_row(row) for row in session.scalars(select(WorkflowRow))]
        if kind == "network_event":
            return [mappers.network_event_from_row(row) for row in session.scalars(select(NetworkEventRow))]
        if kind == "discovered_link":
            return [
                mappers.discovered_link_from_row(row)
                for row in session.scalars(select(DiscoveredLinkRow))
            ]
        raise KeyError(kind)

    def _upsert(self, session: Session, kind: str, entity_id: UUID, value) -> None:
        if kind == "investigation":
            assert isinstance(value, Investigation)
            session.merge(mappers.investigation_to_row(value))
            return
        if kind == "transition":
            assert isinstance(value, InvestigationTransition)
            session.merge(mappers.transition_to_row(value))
            return
        if kind == "session":
            assert isinstance(value, InvestigationSession)
            session.merge(mappers.session_to_row(value))
            return
        if kind == "observation":
            assert isinstance(value, Observation)
            existing = session.get(ObservationRow, entity_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(mappers.observation_to_row(value))
            return
        if kind == "state":
            assert isinstance(value, ApplicationState)
            existing = session.get(ApplicationStateRow, entity_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(mappers.state_to_row(value))
            return
        if kind == "event":
            assert isinstance(value, TimelineEvent)
            session.merge(mappers.event_to_row(value))
            return
        if kind == "evidence":
            assert isinstance(value, Evidence)
            session.merge(mappers.evidence_to_row(value))
            return
        if kind == "diff":
            assert isinstance(value, StateDiff)
            existing = session.get(StateTransitionRow, entity_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(mappers.diff_to_row(value))
            return
        if kind == "rule":
            assert isinstance(value, BusinessRule)
            session.merge(mappers.rule_to_row(value))
            session.flush()
            session.execute(delete(RuleEvidenceRow).where(RuleEvidenceRow.rule_id == entity_id))
            session.execute(delete(RuleExperimentRow).where(RuleExperimentRow.rule_id == entity_id))
            for link in mappers.rule_evidence_links(entity_id, value.evidence_ids, "supported_by"):
                session.add(link)
            for link in mappers.rule_experiment_links(entity_id, value.verification_run_ids, "verified_by"):
                session.add(link)
            return
        if kind == "experiment":
            assert isinstance(value, VerificationRun)
            existing = session.get(ExperimentRow, entity_id)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(mappers.experiment_to_row(value))
            session.flush()
            session.execute(
                delete(RuleExperimentRow).where(
                    RuleExperimentRow.rule_id == value.rule_id,
                    RuleExperimentRow.experiment_id == value.id,
                )
            )
            relation = "verified_by" if value.status == RuleStatus.VERIFIED else "tested_by"
            session.add(RuleExperimentRow(rule_id=value.rule_id, experiment_id=value.id, relation=relation))
            return
        if kind == "evaluation_run":
            assert isinstance(value, EvaluationRun)
            session.merge(mappers.evaluation_run_to_row(value))
            return
        if kind == "workflow":
            from webtwin_core.models.workflow import Workflow

            assert isinstance(value, Workflow)
            session.merge(mappers.workflow_to_row(value))
            return
        if kind == "network_event":
            session.merge(mappers.network_event_to_row(value))
            return
        if kind == "discovered_link":
            session.merge(mappers.discovered_link_to_row(value))
            return
        raise KeyError(kind)


class _EntityMap:
    def __init__(self, store: PostgresStore, kind: str) -> None:
        self._store = store
        self._kind = kind

    def __getitem__(self, key: UUID):
        value = self._store._get(self._kind, key)
        if value is None:
            raise KeyError(key)
        return value

    def get(self, key: UUID, default=None):
        value = self._store._get(self._kind, key)
        return default if value is None else value

    def __setitem__(self, key: UUID, value) -> None:
        self._store._set(self._kind, key, value)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, UUID):
            return False
        return self._store._contains(self._kind, key)

    def values(self):
        return self._store._values(self._kind)
