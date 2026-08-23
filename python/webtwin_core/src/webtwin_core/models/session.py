from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.auth import AuthState, SessionStatus
from webtwin_core.models.investigation import InvestigationCheckpoint


class InvestigationSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    auth_state: AuthState = AuthState.UNKNOWN
    session_status: SessionStatus = SessionStatus.NOT_STARTED
    storage_state_ref: str | None = None
    checkpoint: InvestigationCheckpoint | None = None
    human_ready_at: datetime | None = None
    auth_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
