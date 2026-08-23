from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from webtwin_core.models.common import KnowledgeKind
from webtwin_core.models.rule_status import RuleStatus


class RuleCondition(BaseModel):
    field: str
    operator: str
    value: str | bool | int | float | None = None


class RuleEffect(BaseModel):
    field: str
    visible: bool | None = None
    required: bool | None = None
    enabled: bool | None = None


class BusinessRule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    name: str
    condition: RuleCondition
    effect: RuleEffect
    status: RuleStatus = RuleStatus.CANDIDATE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    knowledge_kind: KnowledgeKind = KnowledgeKind.INFERRED
    evidence_ids: list[UUID] = Field(default_factory=list)
    verification_run_ids: list[UUID] = Field(default_factory=list)
