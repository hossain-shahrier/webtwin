from uuid import UUID

import httpx
import os
from webtwin_core.models import (
    ApplicationState,
    AuthPauseMetadata,
    AuthState,
    BusinessRule,
    Evidence,
    Investigation,
    InvestigationSession,
    Observation,
    StateDiff,
    TimelineEvent,
    TransitionEvent,
)
from webtwin_core.verification.engine import VerificationRun


class ApiClient:
    def __init__(self, base_url: str | None = None) -> None:
        from webtwin_core.defaults import DEFAULT_API_URL

        self.base_url = (base_url or os.environ.get("WEBTWIN_API_URL") or DEFAULT_API_URL).rstrip("/")

    def create_investigation(self, investigation: Investigation) -> Investigation:
        response = httpx.post(f"{self.base_url}/investigations", json=investigation.model_dump(mode="json"))
        response.raise_for_status()
        return Investigation.model_validate(response.json())

    def record_observation(self, observation: Observation) -> Observation:
        response = httpx.post(
            f"{self.base_url}/investigations/{observation.investigation_id}/observations",
            json=observation.model_dump(mode="json"),
        )
        response.raise_for_status()
        return Observation.model_validate(response.json())

    def record_state(self, state: ApplicationState) -> ApplicationState:
        response = httpx.post(
            f"{self.base_url}/investigations/{state.investigation_id}/states",
            json=state.model_dump(mode="json"),
        )
        response.raise_for_status()
        return ApplicationState.model_validate(response.json())

    def record_event(self, event: TimelineEvent) -> TimelineEvent:
        response = httpx.post(
            f"{self.base_url}/investigations/{event.investigation_id}/events",
            json=event.model_dump(mode="json"),
        )
        response.raise_for_status()
        return TimelineEvent.model_validate(response.json())

    def record_evidence(self, evidence: Evidence) -> Evidence:
        response = httpx.post(
            f"{self.base_url}/investigations/{evidence.investigation_id}/evidence",
            json=evidence.model_dump(mode="json"),
        )
        response.raise_for_status()
        return Evidence.model_validate(response.json())

    def diff_states(
        self, investigation_id: UUID, before_state_id: UUID, after_state_id: UUID
    ) -> StateDiff:
        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/diff",
            params={"before_state_id": str(before_state_id), "after_state_id": str(after_state_id)},
        )
        response.raise_for_status()
        return StateDiff.model_validate(response.json())

    def verify_rule(
        self, investigation_id: UUID, rule_id: UUID, verification_run: VerificationRun
    ) -> BusinessRule:
        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/rules/{rule_id}/verify",
            json=verification_run.model_dump(mode="json"),
        )
        response.raise_for_status()
        return BusinessRule.model_validate(response.json())

    def transition(
        self,
        investigation_id: UUID,
        event: TransitionEvent,
        reason: str | None = None,
        auth_pause: AuthPauseMetadata | None = None,
    ) -> Investigation:
        payload: dict[str, object] = {"event": event.value, "reason": reason}
        if auth_pause is not None:
            payload["auth_pause"] = auth_pause.model_dump(mode="json")
        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/transition",
            json=payload,
        )
        response.raise_for_status()
        return Investigation.model_validate(response.json())

    def upsert_session(
        self,
        investigation_id: UUID,
        auth_state: AuthState | None = None,
        storage_state_ref: str | None = None,
    ) -> InvestigationSession:
        payload: dict[str, object] = {}
        if auth_state is not None:
            payload["auth_state"] = auth_state.value
        if storage_state_ref is not None:
            payload["storage_state_ref"] = storage_state_ref
        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/session",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return InvestigationSession(
            id=data["id"],
            investigation_id=data["investigation_id"],
            auth_state=AuthState(data["auth_state"]),
        )

    def get_investigation(self, investigation_id: UUID) -> Investigation:
        response = httpx.get(f"{self.base_url}/investigations/{investigation_id}")
        response.raise_for_status()
        return Investigation.model_validate(response.json())

    def resume_investigation(self, investigation_id: UUID) -> Investigation:
        response = httpx.post(f"{self.base_url}/investigations/{investigation_id}/resume")
        response.raise_for_status()
        return Investigation.model_validate(response.json())
