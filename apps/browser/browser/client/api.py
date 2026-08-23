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

    def claim_investigation(self, investigation_id: UUID) -> Investigation:
        response = httpx.post(f"{self.base_url}/investigations/{investigation_id}/claim")
        response.raise_for_status()
        return Investigation.model_validate(response.json())

    def list_pending(self) -> list[Investigation]:
        response = httpx.get(f"{self.base_url}/investigations/pending")
        response.raise_for_status()
        return [Investigation.model_validate(item) for item in response.json()]

    def upsert_auth_form(self, investigation_id: UUID, schema) -> dict:
        response = httpx.put(
            f"{self.base_url}/investigations/{investigation_id}/auth/form",
            json=schema.model_dump(mode="json") if hasattr(schema, "model_dump") else schema,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_pending_auth_fill(self, investigation_id: UUID) -> dict | None:
        response = httpx.get(
            f"{self.base_url}/investigations/{investigation_id}/auth/pending-fill",
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("submission")

    def mark_auth_fill_applied(
        self,
        investigation_id: UUID,
        *,
        status: str = "applied",
        error: str | None = None,
    ) -> dict:
        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/auth/fill-applied",
            json={"status": status, "error": error},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_auth_form(self, investigation_id: UUID) -> dict | None:
        response = httpx.get(
            f"{self.base_url}/investigations/{investigation_id}/auth/form",
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("form")

    def save_exploration_progress(self, investigation_id: UUID, progress) -> dict:
        payload = progress.model_dump(mode="json") if hasattr(progress, "model_dump") else progress
        response = httpx.put(
            f"{self.base_url}/investigations/{investigation_id}/exploration-progress",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_exploration_progress(self, investigation_id: UUID) -> dict | None:
        response = httpx.get(
            f"{self.base_url}/investigations/{investigation_id}/exploration-progress",
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("exploration")

    def list_discovered_links(self, investigation_id: UUID) -> list[dict]:
        response = httpx.get(
            f"{self.base_url}/investigations/{investigation_id}/site-graph",
            timeout=20,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        links: list[dict] = []
        for edge in data.get("edges") or []:
            links.append(
                {
                    "investigation_id": str(investigation_id),
                    "from_screen_id": edge.get("from") or "/",
                    "to_screen_id": edge.get("to"),
                    "href": edge.get("href") or "",
                    "visited": bool(edge.get("visited")),
                    "link_type": edge.get("link_type") or "navigate",
                    "selector": edge.get("selector"),
                }
            )
        return links

    def record_metrics(self, investigation_id: UUID, run) -> object:
        from webtwin_core.evaluation.runs import EvaluationRun

        response = httpx.post(
            f"{self.base_url}/investigations/{investigation_id}/metrics",
            json=run.model_dump(mode="json") if hasattr(run, "model_dump") else run,
        )
        response.raise_for_status()
        return EvaluationRun.model_validate(response.json())
