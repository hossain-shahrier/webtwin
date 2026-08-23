"""Network observation with redaction — never stores cookies/tokens in plaintext."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from webtwin_core.models import Evidence, EvidenceType


SENSITIVE_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "proxy-authorization",
}


class NetworkEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    timeline_event_id: UUID | None = None
    method: str
    url: str
    status_code: int | None = None
    timing_ms: float | None = None
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)
    body_shape: dict[str, Any] = Field(default_factory=dict)
    evidence_id: UUID | None = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADER_KEYS:
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def body_shape_from_json(payload: Any, *, max_keys: int = 40) -> dict[str, Any]:
    """Store structure only — keys and types, not secret values."""
    if payload is None:
        return {}
    if isinstance(payload, dict):
        shape: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= max_keys:
                shape["__truncated__"] = True
                break
            shape[str(key)] = type(value).__name__
        return {"type": "object", "keys": shape}
    if isinstance(payload, list):
        return {"type": "array", "length": len(payload), "item": type(payload[0]).__name__ if payload else "empty"}
    return {"type": type(payload).__name__}


class NetworkCollector:
    def __init__(self, investigation_id: UUID) -> None:
        self.investigation_id = investigation_id
        self.events: list[NetworkEvent] = []

    def attach(self, page) -> None:
        def on_response(response) -> None:
            request = response.request
            try:
                headers = redact_headers(dict(response.headers))
            except Exception:
                headers = {}
            try:
                req_headers = redact_headers(dict(request.headers))
            except Exception:
                req_headers = {}
            shape: dict[str, Any] = {}
            try:
                content_type = (response.headers.get("content-type") or "").lower()
                if "json" in content_type:
                    shape = body_shape_from_json(response.json())
                else:
                    shape = {"type": "opaque", "content_type": content_type}
            except Exception:
                shape = {"type": "unreadable"}

            event = NetworkEvent(
                investigation_id=self.investigation_id,
                method=request.method,
                url=response.url,
                status_code=response.status,
                request_headers=req_headers,
                response_headers=headers,
                body_shape=shape,
            )
            self.events.append(event)

        page.on("response", on_response)

    def to_evidence(self, timeline_event_id: UUID | None = None) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        for event in self.events:
            if timeline_event_id is not None and event.timeline_event_id is None:
                event.timeline_event_id = timeline_event_id
            evidence = Evidence(
                investigation_id=self.investigation_id,
                type=EvidenceType.NETWORK,
                url=event.url,
                payload={
                    "network_event_id": str(event.id),
                    "timeline_event_id": str(event.timeline_event_id) if event.timeline_event_id else None,
                    "method": event.method,
                    "status_code": event.status_code,
                    "body_shape": event.body_shape,
                    "request_headers": event.request_headers,
                    "response_headers": event.response_headers,
                },
            )
            event.evidence_id = evidence.id
            evidence_list.append(evidence)
        return evidence_list
