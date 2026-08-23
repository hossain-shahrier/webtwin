from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.auth import AuthPauseMetadata


class InvestigationStatus(StrEnum):
    CREATED = "created"
    INITIALIZING = "initializing"
    AUTH_CHECK = "auth_check"
    AUTH_REQUIRED = "auth_required"
    AUTHENTICATED = "authenticated"
    EXPLORING = "exploring"
    OBSERVING = "observing"
    GENERATING_RULE = "generating_rule"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class InvestigationGoalType(StrEnum):
    DISCOVER_BUSINESS_LOGIC = "discover_business_logic"


class InvestigationGoal(BaseModel):
    type: InvestigationGoalType = InvestigationGoalType.DISCOVER_BUSINESS_LOGIC
    target: str
    scope: str | None = None
    description: str | None = None


class TransitionEvent(StrEnum):
    START = "start"
    INIT_COMPLETE = "init_complete"
    AUTH_REQUIRED = "auth_required"
    AUTH_OK = "auth_ok"
    AUTH_COMPLETED = "auth_completed"
    AUTH_TIMEOUT = "auth_timeout"
    BEGIN_EXPLORATION = "begin_exploration"
    CAPTURE_OBSERVATION = "capture_observation"
    GENERATE_RULES = "generate_rules"
    START_VERIFICATION = "start_verification"
    VERIFICATION_COMPLETE = "verification_complete"
    COMPLETE = "complete"
    FAIL = "fail"
    BLOCK = "block"
    CANCEL = "cancel"
    RESUME = "resume"
    BROWSER_CRASH = "browser_crash"


class InvestigationTransition(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    from_status: InvestigationStatus
    to_status: InvestigationStatus
    event: TransitionEvent
    reason: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvestigationCheckpoint(BaseModel):
    status: InvestigationStatus
    target_url: str
    last_event: TransitionEvent | None = None
    observation_count: int = 0
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Investigation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    goal: str
    target_url: str
    goal_spec: InvestigationGoal | None = None
    status: InvestigationStatus = InvestigationStatus.CREATED
    application_name: str | None = None
    feature_scope: str | None = None
    session_id: UUID | None = None
    auth_pause: AuthPauseMetadata | None = None
    checkpoint: InvestigationCheckpoint | None = None
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    blocked_reason: str | None = None
