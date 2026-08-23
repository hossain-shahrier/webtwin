from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    order: int
    description: str
    action_id: str | None = None
    from_state_id: UUID | None = None
    to_state_id: UUID | None = None


class Workflow(BaseModel):
    """Ordered state-transition chain discovered during exploration."""

    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    name: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    trigger_action_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    role_scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
