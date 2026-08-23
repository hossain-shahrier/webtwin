from uuid import UUID

from fastapi import APIRouter
from webtwin_core.evaluation.runs import EvaluationRun
from webtwin_core.models import (
    ApplicationState,
    BusinessRule,
    Evidence,
    Investigation,
    Observation,
    StateDiff,
    TimelineEvent,
)
from webtwin_core.models.investigation import InvestigationTransition
from webtwin_core.qa.models import QuestionAnswer, QuestionRequest
from webtwin_core.verification.engine import VerificationRun

from api.services import investigations as svc

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.post("", response_model=Investigation, status_code=201)
def create_investigation(investigation: Investigation) -> Investigation:
    return svc.create_investigation(investigation)


@router.post("/{investigation_id}/transition", response_model=Investigation)
def transition_investigation(
    investigation_id: UUID,
    request: svc.TransitionRequest,
) -> Investigation:
    return svc.transition_investigation(investigation_id, request)


@router.post("/{investigation_id}/resume", response_model=Investigation)
def resume_investigation(investigation_id: UUID) -> Investigation:
    return svc.resume_failed(investigation_id)


@router.post("/{investigation_id}/restart", response_model=Investigation)
def restart_investigation(investigation_id: UUID) -> Investigation:
    return svc.restart_failed(investigation_id)


@router.post("/{investigation_id}/auth/begin", response_model=svc.SessionPublic)
def begin_authentication(investigation_id: UUID) -> svc.SessionPublic:
    return svc.begin_authentication(investigation_id)


@router.post("/{investigation_id}/auth/mark-ready", response_model=svc.SessionPublic)
def mark_authentication_ready(investigation_id: UUID) -> svc.SessionPublic:
    return svc.mark_authentication_ready(investigation_id)


@router.post("/{investigation_id}/auth/resume", response_model=Investigation)
def resume_after_authentication(investigation_id: UUID) -> Investigation:
    return svc.resume_after_authentication(investigation_id)


@router.post("/{investigation_id}/session", response_model=svc.SessionPublic)
def upsert_session(investigation_id: UUID, request: svc.SessionUpdateRequest) -> svc.SessionPublic:
    return svc.upsert_session(investigation_id, request)


@router.get("/{investigation_id}/session", response_model=svc.SessionPublic)
def get_session(investigation_id: UUID) -> svc.SessionPublic:
    return svc.get_session(investigation_id)


@router.get("/{investigation_id}/detail", response_model=svc.InvestigationDetail)
def get_investigation_detail(investigation_id: UUID) -> svc.InvestigationDetail:
    return svc.get_detail(investigation_id)


@router.get("/{investigation_id}/transitions", response_model=list[InvestigationTransition])
def get_transitions(investigation_id: UUID) -> list[InvestigationTransition]:
    return svc.get_transitions(investigation_id)


@router.get("", response_model=list[Investigation])
def list_investigations() -> list[Investigation]:
    return svc.list_investigations()


@router.get("/pending", response_model=list[Investigation])
def list_pending() -> list[Investigation]:
    return svc.list_pending_investigations()


@router.post("/{investigation_id}/claim", response_model=Investigation)
def claim_investigation(investigation_id: UUID) -> Investigation:
    return svc.claim_investigation(investigation_id)


@router.get("/{investigation_id}", response_model=Investigation)
def get_investigation(investigation_id: UUID) -> Investigation:
    return svc.get_investigation(investigation_id)


@router.post("/{investigation_id}/observations", response_model=Observation, status_code=201)
def record_observation(investigation_id: UUID, observation: Observation) -> Observation:
    return svc.record_observation(investigation_id, observation)


@router.get("/{investigation_id}/observations", response_model=list[Observation])
def list_observations(investigation_id: UUID) -> list[Observation]:
    return svc.list_observations(investigation_id)


@router.post("/{investigation_id}/states", response_model=ApplicationState, status_code=201)
def record_state(investigation_id: UUID, state: ApplicationState) -> ApplicationState:
    return svc.record_state(investigation_id, state)


@router.get("/{investigation_id}/states", response_model=list[ApplicationState])
def list_states(investigation_id: UUID) -> list[ApplicationState]:
    return svc.list_states(investigation_id)


@router.post("/{investigation_id}/events", response_model=TimelineEvent, status_code=201)
def record_event(investigation_id: UUID, event: TimelineEvent) -> TimelineEvent:
    return svc.record_event(investigation_id, event)


@router.post("/{investigation_id}/evidence", response_model=Evidence, status_code=201)
def record_evidence(investigation_id: UUID, evidence: Evidence) -> Evidence:
    return svc.record_evidence(investigation_id, evidence)


@router.get("/{investigation_id}/evidence", response_model=list[Evidence])
def list_evidence(investigation_id: UUID) -> list[Evidence]:
    return svc.list_evidence(investigation_id)


@router.post("/{investigation_id}/diff", response_model=StateDiff)
def diff_states(
    investigation_id: UUID,
    before_state_id: UUID,
    after_state_id: UUID,
) -> StateDiff:
    return svc.diff_states(investigation_id, before_state_id, after_state_id)


@router.get("/{investigation_id}/diffs", response_model=list[StateDiff])
def list_diffs(investigation_id: UUID) -> list[StateDiff]:
    return svc.list_diffs(investigation_id)


@router.post("/{investigation_id}/rules/{rule_id}/verify", response_model=BusinessRule)
def verify_rule(
    investigation_id: UUID,
    rule_id: UUID,
    verification_run: VerificationRun,
) -> BusinessRule:
    return svc.verify_rule(investigation_id, rule_id, verification_run)


@router.get("/{investigation_id}/rules/{rule_id}/provenance", response_model=svc.RuleProvenance)
def get_rule_provenance(investigation_id: UUID, rule_id: UUID) -> svc.RuleProvenance:
    return svc.get_rule_provenance(investigation_id, rule_id)


@router.get("/{investigation_id}/timeline", response_model=list[TimelineEvent])
def get_timeline(investigation_id: UUID) -> list[TimelineEvent]:
    return svc.list_timeline(investigation_id)


@router.get("/{investigation_id}/rules", response_model=list[BusinessRule])
def get_rules(investigation_id: UUID) -> list[BusinessRule]:
    return svc.list_rules(investigation_id)


@router.post("/{investigation_id}/metrics", response_model=EvaluationRun, status_code=201)
def record_metrics(investigation_id: UUID, run: EvaluationRun) -> EvaluationRun:
    return svc.save_evaluation_run(investigation_id, run)


@router.get("/{investigation_id}/metrics", response_model=list[EvaluationRun])
def get_metrics(investigation_id: UUID) -> list[EvaluationRun]:
    return svc.list_metrics(investigation_id)


@router.post("/{investigation_id}/questions", response_model=QuestionAnswer)
def ask_question(investigation_id: UUID, request: QuestionRequest) -> QuestionAnswer:
    return svc.ask_question(investigation_id, request.question)


@router.get("/{investigation_id}/workflows")
def get_workflows(investigation_id: UUID) -> list:
    return svc.list_workflows(investigation_id)


@router.post("/{investigation_id}/sync-kg")
def sync_kg(investigation_id: UUID) -> dict:
    return svc.sync_knowledge_graph(investigation_id)
