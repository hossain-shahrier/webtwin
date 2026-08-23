from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models.common import KnowledgeKind


class QuestionRequest(BaseModel):
    question: str


class AnswerCitation(BaseModel):
    rule_id: UUID | None = None
    evidence_id: UUID | None = None
    confidence: float | None = None
    label: str | None = None


class QuestionAnswer(BaseModel):
    answer: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    refused: bool = False
    knowledge_kind: KnowledgeKind = KnowledgeKind.INFERRED
    confidence: float = 0.0
