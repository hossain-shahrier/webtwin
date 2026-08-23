"""Clone readiness scorecard for an investigation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule
from webtwin_core.reference_system import ReferenceSystemContext


class CloneScorecard(BaseModel):
    verified_rules: int = 0
    candidate_rules: int = 0
    contradicted_rules: int = 0
    exploration_coverage: float = 0.0
    unknown_fields: int = 0
    screen_count: int = 0
    field_count: int = 0
    fields_with_selectors: int = 0
    discovered_pages: int = 0
    visited_pages: int = 0
    link_coverage_pct: float = 0.0
    export_completeness: float = 0.0
    clone_ready: bool = False
    gaps: list[str] = Field(default_factory=list)


def compute_clone_scorecard(
    rules: list[BusinessRule],
    reference: ReferenceSystemContext,
    *,
    exploration_coverage: float | None = None,
) -> CloneScorecard:
    verified = [rule for rule in rules if rule.status.value == "verified"]
    candidates = [rule for rule in rules if rule.status.value == "candidate"]
    contradicted = [rule for rule in rules if rule.status.value == "contradicted"]

    coverage = exploration_coverage if exploration_coverage is not None else reference.exploration_coverage
    unknown_count = len(reference.unexplored_fields)
    field_count = sum(len(screen.fields) for screen in reference.screens)
    fields_with_selectors = sum(
        1 for screen in reference.screens for field in screen.fields if field.selector
    )

    completeness_parts: list[float] = []
    if reference.screens:
        completeness_parts.append(1.0)
    else:
        completeness_parts.append(0.0)
    if field_count:
        completeness_parts.append(fields_with_selectors / field_count)
    else:
        completeness_parts.append(0.5)
    if verified:
        with_evidence = sum(1 for rule in verified if rule.evidence_ids)
        completeness_parts.append(with_evidence / len(verified))
    else:
        completeness_parts.append(0.0)
    if verified:
        completeness_parts.append(min(1.0, len(verified) / max(1, len(candidates) + len(verified))))
    export_completeness = round(sum(completeness_parts) / len(completeness_parts), 3)

    gaps: list[str] = []
    if not reference.screens:
        gaps.append("No screens mapped")
    if unknown_count:
        gaps.append(f"{unknown_count} unexplored field(s)")
    if not verified:
        gaps.append("No verified rules")
    if contradicted:
        gaps.append(f"{len(contradicted)} contradicted rule(s)")
    if field_count and fields_with_selectors < field_count:
        gaps.append("Some fields missing selectors in export")

    stats = reference.site_graph_stats or {}
    discovered_pages = int(stats.get("total_internal", 0) or 0)
    visited_pages = len({screen.id for screen in reference.screens if screen.visit_count > 0})
    link_coverage_pct = float(stats.get("coverage_pct", 0.0) or 0.0)
    if discovered_pages and not verified:
        gaps.append(
            f"Structural site map {round(link_coverage_pct * 100)}% covered — "
            "behavioral rules not verified (expected for marketing/catalog sites)"
        )

    clone_ready = (
        bool(reference.screens)
        and bool(verified)
        and export_completeness >= 0.6
        and not contradicted
    )

    return CloneScorecard(
        verified_rules=len(verified),
        candidate_rules=len(candidates),
        contradicted_rules=len(contradicted),
        exploration_coverage=round(coverage, 3),
        unknown_fields=unknown_count,
        screen_count=len(reference.screens),
        field_count=field_count,
        fields_with_selectors=fields_with_selectors,
        discovered_pages=discovered_pages,
        visited_pages=visited_pages,
        link_coverage_pct=round(link_coverage_pct, 3),
        export_completeness=export_completeness,
        clone_ready=clone_ready,
        gaps=gaps,
    )
