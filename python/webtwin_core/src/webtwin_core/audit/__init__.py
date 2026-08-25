"""Lightweight audit trail for enterprise governance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID | None = None
    action: str
    actor: str = "system"
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def make_audit_event(
    action: str,
    *,
    investigation_id: UUID | None = None,
    actor: str = "system",
    **detail: Any,
) -> AuditEvent:
    return AuditEvent(
        investigation_id=investigation_id,
        action=action,
        actor=actor,
        detail=detail,
    )
