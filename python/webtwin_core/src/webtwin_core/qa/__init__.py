"""Evidence-grounded Q&A — never invents facts without citations."""

from __future__ import annotations

import re
from uuid import UUID

from webtwin_core.models import BusinessRule, Evidence
from webtwin_core.models.common import KnowledgeKind
from webtwin_core.qa.models import AnswerCitation, QuestionAnswer


def answer_from_evidence(
    question: str,
    rules: list[BusinessRule],
    evidence: list[Evidence],
    *,
    min_confidence: float = 0.4,
) -> QuestionAnswer:
    tokens = {token.lower() for token in re.findall(r"[a-zA-Z0-9_]+", question) if len(token) > 2}
    scored: list[tuple[float, BusinessRule]] = []

    for rule in rules:
        haystack = " ".join(
            [
                rule.name or "",
                rule.condition.field,
                str(rule.condition.value),
                rule.effect.field,
            ]
        ).lower()
        overlap = sum(1 for token in tokens if token in haystack)
        score = overlap + float(rule.confidence or 0)
        if rule.status.value == "verified":
            score += 1.0
        if overlap > 0 or any(token in haystack for token in ("end", "date", "appear", "visible", "show")):
            scored.append((score, rule))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < min_confidence:
        return QuestionAnswer(
            answer="Insufficient evidence to answer confidently.",
            refused=True,
            knowledge_kind=KnowledgeKind.UNKNOWN,
            confidence=0.0,
        )

    top_score, top_rule = scored[0]
    evidence_ids = list(top_rule.evidence_ids)
    linked_evidence = [item for item in evidence if item.id in evidence_ids][:3]
    if not linked_evidence and evidence:
        linked_evidence = evidence[:1]

    citations = [
        AnswerCitation(
            rule_id=top_rule.id,
            evidence_id=linked_evidence[0].id if linked_evidence else None,
            confidence=top_rule.confidence,
            label=top_rule.name,
        )
    ]
    for item in linked_evidence[1:]:
        citations.append(
            AnswerCitation(rule_id=top_rule.id, evidence_id=item.id, confidence=top_rule.confidence)
        )

    visible = top_rule.effect.visible
    answer = (
        f"{top_rule.effect.field} becomes visible when {top_rule.condition.field} "
        f"{top_rule.condition.operator} {top_rule.condition.value!r} "
        f"(status={top_rule.status.value}, confidence={top_rule.confidence})."
        if visible
        else (
            f"Rule '{top_rule.name}': when {top_rule.condition.field} "
            f"{top_rule.condition.operator} {top_rule.condition.value!r}, "
            f"effect applies to {top_rule.effect.field} "
            f"(status={top_rule.status.value})."
        )
    )
    return QuestionAnswer(
        answer=answer,
        citations=citations,
        refused=False,
        knowledge_kind=KnowledgeKind.INFERRED,
        confidence=min(1.0, top_score / 5),
    )


def neighborhood_for_rule(rule_id: UUID, rules: list[BusinessRule], evidence: list[Evidence]) -> dict:
    rule = next((item for item in rules if item.id == rule_id), None)
    if rule is None:
        return {"rule": None, "evidence": []}
    linked = [item for item in evidence if item.id in rule.evidence_ids]
    return {"rule": rule.model_dump(mode="json"), "evidence": [e.model_dump(mode="json") for e in linked]}
