"""Evidence-grounded Q&A — never invents facts without citations."""

from __future__ import annotations

import re
from uuid import UUID

from webtwin_core.models import BusinessRule, Evidence
from webtwin_core.models.common import KnowledgeKind
from webtwin_core.qa.models import AnswerCitation, QuestionAnswer


def _citation_extras(evidence_item: Evidence | None) -> dict[str, str | None]:
    if evidence_item is None:
        return {"evidence_summary": None, "screen_path": None}
    payload = evidence_item.payload or {}
    summary = payload.get("summary") or payload.get("description")
    if isinstance(summary, str):
        summary = summary[:160]
    else:
        summary = None
    screen_path = payload.get("screen_id") or payload.get("path") or payload.get("url")
    if isinstance(screen_path, str) and screen_path.startswith("http"):
        from urllib.parse import urlparse

        screen_path = urlparse(screen_path).path or screen_path
    if not isinstance(screen_path, str):
        screen_path = None
    return {"evidence_summary": summary, "screen_path": screen_path}


def _make_citation(
    rule: BusinessRule,
    evidence_item: Evidence | None = None,
) -> AnswerCitation:
    extras = _citation_extras(evidence_item)
    return AnswerCitation(
        rule_id=rule.id,
        evidence_id=evidence_item.id if evidence_item else None,
        confidence=rule.confidence,
        label=rule.name,
        evidence_summary=extras["evidence_summary"],
        screen_path=extras["screen_path"],
    )


def answer_from_evidence(
    question: str,
    rules: list[BusinessRule],
    evidence: list[Evidence],
    *,
    min_confidence: float = 0.4,
    preferred_rule_ids: list[UUID] | None = None,
) -> QuestionAnswer:
    # Graph-backed path: prefer verified rules from KG / entity graph when available
    if preferred_rule_ids:
        for rule_id in preferred_rule_ids:
            rule = next((item for item in rules if item.id == rule_id), None)
            if rule is None:
                continue
            linked_evidence = [item for item in evidence if item.id in rule.evidence_ids][:5]
            if rule.status.value == "verified" and linked_evidence:
                citations = [_make_citation(rule, linked_evidence[0])]
                visible = rule.effect.visible
                if visible:
                    answer = (
                        f"{rule.effect.field} becomes visible when {rule.condition.field} "
                        f"{rule.condition.operator} {rule.condition.value!r} "
                        f"(verified via graph path, confidence={rule.confidence})."
                    )
                else:
                    answer = (
                        f"Verified rule '{rule.name}': when {rule.condition.field} "
                        f"{rule.condition.operator} {rule.condition.value!r}, "
                        f"effect applies to {rule.effect.field} (graph-backed citation)."
                    )
                return QuestionAnswer(
                    answer=answer,
                    citations=citations,
                    refused=False,
                    knowledge_kind=KnowledgeKind.OBSERVED,
                    confidence=rule.confidence,
                )

    tokens = {token.lower() for token in re.findall(r"[a-zA-Z0-9_]+", question) if len(token) > 2}
    preferred = {str(item) for item in (preferred_rule_ids or [])}
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
        score = float(overlap) + float(rule.confidence or 0)
        if rule.status.value == "verified":
            score += 3.0
        elif rule.status.value == "candidate":
            score += 0.2
        elif rule.status.value == "contradicted":
            score -= 2.0
        if rule.evidence_ids:
            score += 0.5
        if str(rule.id) in preferred:
            score += 2.5
        # Require lexical overlap with the rule (or an explicit preferred id).
        # Do not admit every rule for generic question words like "why" / "appear".
        if overlap > 0 or str(rule.id) in preferred:
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
    linked_evidence = [item for item in evidence if item.id in evidence_ids][:5]
    if not linked_evidence:
        # Never forge citations from unrelated evidence blobs
        reason = (
            "it has no linked evidence yet"
            if not evidence_ids
            else "its evidence ids could not be resolved"
        )
        return QuestionAnswer(
            answer=(
                f"Matched rule '{top_rule.name}' but {reason} "
                f"(status={top_rule.status.value}). Refuse to claim without citations."
            ),
            refused=True,
            knowledge_kind=KnowledgeKind.UNKNOWN,
            confidence=0.0,
            citations=[_make_citation(top_rule)],
        )

    citations = [_make_citation(top_rule, linked_evidence[0])]
    for item in linked_evidence[1:]:
        citations.append(_make_citation(top_rule, item))

    status = top_rule.status.value
    visible = top_rule.effect.visible
    caveat = ""
    if status == "verified":
        kind = KnowledgeKind.OBSERVED
        caveat = " Supported by controlled verification experiments."
    elif status == "candidate":
        kind = KnowledgeKind.INFERRED
        caveat = " This is a candidate rule — not yet verified by controlled experiments."
    elif status == "contradicted":
        kind = KnowledgeKind.INFERRED
        caveat = " Verification contradicted this rule; treat as unreliable."
    else:
        kind = KnowledgeKind.INFERRED

    if visible:
        answer = (
            f"{top_rule.effect.field} becomes visible when {top_rule.condition.field} "
            f"{top_rule.condition.operator} {top_rule.condition.value!r} "
            f"(status={status}, confidence={top_rule.confidence}).{caveat}"
        )
    else:
        answer = (
            f"Rule '{top_rule.name}': when {top_rule.condition.field} "
            f"{top_rule.condition.operator} {top_rule.condition.value!r}, "
            f"effect applies to {top_rule.effect.field} "
            f"(status={status}, confidence={top_rule.confidence}).{caveat}"
        )

    return QuestionAnswer(
        answer=answer,
        citations=citations,
        refused=False,
        knowledge_kind=kind,
        confidence=min(1.0, top_score / 6),
    )


def neighborhood_for_rule(rule_id: UUID, rules: list[BusinessRule], evidence: list[Evidence]) -> dict:
    rule = next((item for item in rules if item.id == rule_id), None)
    if rule is None:
        return {"rule": None, "evidence": []}
    linked = [item for item in evidence if item.id in rule.evidence_ids]
    return {"rule": rule.model_dump(mode="json"), "evidence": [e.model_dump(mode="json") for e in linked]}
