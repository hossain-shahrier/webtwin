from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TimelineEventType(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    INPUT = "input"
    SELECT = "select"
    SUBMIT = "submit"
    SCROLL = "scroll"
    STATE_CHANGE = "state_change"
    VALIDATION = "validation"
    CHALLENGE = "challenge"
    EXPERIMENT = "experiment"


class TimelineEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    type: TimelineEventType
    description: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    state_before_id: UUID | None = None
    state_after_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
