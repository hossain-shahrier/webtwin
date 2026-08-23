import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from webtwin_core.models.common import KnowledgeKind


def compute_evidence_content_hash(payload: dict[str, Any], artifact_uri: str | None = None) -> str:
    canonical = json.dumps({"payload": payload, "artifact_uri": artifact_uri}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EvidenceType(StrEnum):
    DOM = "dom"
    ACCESSIBILITY = "accessibility"
    SCREENSHOT = "screenshot"
    NETWORK = "network"
    INTERACTION = "interaction"
    COOKIE = "cookie"
    TOKEN = "token"
    CREDENTIAL = "credential"


class EvidenceSensitivity(StrEnum):
    SAFE = "safe"
    SENSITIVE = "sensitive"


SENSITIVE_EVIDENCE_TYPES = {
    EvidenceType.COOKIE,
    EvidenceType.TOKEN,
    EvidenceType.CREDENTIAL,
    EvidenceType.NETWORK,
}


def evidence_sensitivity(evidence_type: EvidenceType) -> EvidenceSensitivity:
    if evidence_type in SENSITIVE_EVIDENCE_TYPES:
        return EvidenceSensitivity.SENSITIVE
    return EvidenceSensitivity.SAFE


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    type: EvidenceType
    sensitivity: EvidenceSensitivity = EvidenceSensitivity.SAFE
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    url: str | None = None
    knowledge_kind: KnowledgeKind = KnowledgeKind.OBSERVED
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_uri: str | None = None
    content_hash: str | None = None

    @model_validator(mode="after")
    def apply_defaults(self) -> Self:
        if self.type in SENSITIVE_EVIDENCE_TYPES:
            object.__setattr__(self, "sensitivity", EvidenceSensitivity.SENSITIVE)
        if self.content_hash is None:
            object.__setattr__(
                self,
                "content_hash",
                compute_evidence_content_hash(self.payload, self.artifact_uri),
            )
        return self
