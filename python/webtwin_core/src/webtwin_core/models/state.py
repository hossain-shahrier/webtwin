from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FieldState(BaseModel):
    name: str
    label: str | None = None
    value: str | None = None
    visible: bool = True
    enabled: bool = True
    required: bool = False


class ApplicationState(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    sequence: int
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None
    fields: list[FieldState] = Field(default_factory=list)
    triggered_by_event_id: UUID | None = None
