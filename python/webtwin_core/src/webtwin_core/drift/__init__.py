"""Behavioral Drift Twin — golden vs live verified-rule freshness."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from webtwin_core.models import BusinessRule


class DriftItem(BaseModel):
    rule_name: str
    status: str  # still_verified | broken | missing | new | weakened | contradicted
    live_rule_id: str | None = None
    live_status: str | None = None
    confidence: float | None = None
    detail: str = ""


class DriftReport(BaseModel):
    application_key: str
    golden_version: str | None = None
    investigation_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_pct: float = 0.0
    still_verified: list[DriftItem] = Field(default_factory=list)
    broken: list[DriftItem] = Field(default_factory=list)
    missing: list[DriftItem] = Field(default_factory=list)
    weakened: list[DriftItem] = Field(default_factory=list)
    new_verified: list[DriftItem] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)


def _rule_names_from_golden(
    golden: dict[str, Any] | None,
    *,
    role_scope: str | None = None,
) -> tuple[str | None, set[str]]:
    if not golden:
        return None, set()
    version = golden.get("version")
    catalog = golden.get("catalog") or {}
    names: set[str] = set()
    roles = catalog.get("roles") or {}
    if role_scope and role_scope in roles:
        for name in roles[role_scope].get("verified_rule_names") or []:
            if name:
                names.add(str(name))
    else:
        for role in roles.values():
            for name in role.get("verified_rule_names") or []:
                if name:
                    names.add(str(name))
    for name in catalog.get("verified_rule_names") or []:
        names.add(str(name))
    return (str(version) if version else None), names


def compute_drift_report(
    *,
    application_key: str,
    golden: dict[str, Any] | None,
    live_rules: list[BusinessRule],
    investigation_id: UUID | None = None,
    role_scope: str | None = None,
) -> DriftReport:
    """Compare golden verified rule names against live investigation rules."""
    version, golden_names = _rule_names_from_golden(golden, role_scope=role_scope)
    by_name: dict[str, BusinessRule] = {}
    for rule in live_rules:
        by_name.setdefault(rule.name, rule)

    still: list[DriftItem] = []
    broken: list[DriftItem] = []
    missing: list[DriftItem] = []
    weakened: list[DriftItem] = []
    new_verified: list[DriftItem] = []

    for name in sorted(golden_names):
        live = by_name.get(name)
        if live is None:
            missing.append(
                DriftItem(
                    rule_name=name,
                    status="missing",
                    detail="Present in golden catalog but absent from live investigation.",
                )
            )
            continue
        status = live.status.value
        item = DriftItem(
            rule_name=name,
            status="still_verified",
            live_rule_id=str(live.id),
            live_status=status,
            confidence=live.confidence,
        )
        if status == "verified":
            item.status = "still_verified"
            still.append(item)
        elif status == "contradicted":
            item.status = "broken"
            item.detail = "Golden rule is contradicted on live run."
            broken.append(item)
        elif status in {"under_verification", "candidate"}:
            item.status = "weakened"
            item.detail = f"Golden rule degraded to {status}."
            weakened.append(item)
        else:
            item.status = "weakened"
            item.detail = f"Unexpected live status {status}."
            weakened.append(item)

    for rule in live_rules:
        if rule.status.value != "verified":
            continue
        if rule.name in golden_names:
            continue
        new_verified.append(
            DriftItem(
                rule_name=rule.name,
                status="new",
                live_rule_id=str(rule.id),
                live_status=rule.status.value,
                confidence=rule.confidence,
                detail="Verified on live run but not in golden pin.",
            )
        )

    denominator = len(golden_names) or 1
    freshness = round(len(still) / denominator, 3) if golden_names else (
        1.0 if any(r.status.value == "verified" for r in live_rules) else 0.0
    )

    guidance = [
        "Re-run verification on broken/weakened rules before trusting Clone Spec.",
        "Promote new verified rules into the next golden pin when intentional.",
        "Missing golden rules usually mean the live investigation did not cover that path.",
    ]
    if not golden_names:
        guidance.insert(0, "No golden verified rules found — pin a golden catalog first.")

    return DriftReport(
        application_key=application_key,
        golden_version=version,
        investigation_id=str(investigation_id) if investigation_id else None,
        freshness_pct=freshness,
        still_verified=still,
        broken=broken,
        missing=missing,
        weakened=weakened,
        new_verified=new_verified,
        guidance=guidance,
    )


def format_drift_markdown(report: DriftReport) -> str:
    lines = [
        "# WebTwin Drift Report",
        "",
        f"- Application: `{report.application_key}`",
        f"- Golden version: `{report.golden_version or '—'}`",
        f"- Investigation: `{report.investigation_id or '—'}`",
        f"- Freshness: {round(report.freshness_pct * 100)}%",
        f"- Still verified: {len(report.still_verified)}",
        f"- Broken: {len(report.broken)}",
        f"- Missing: {len(report.missing)}",
        f"- Weakened: {len(report.weakened)}",
        f"- New verified: {len(report.new_verified)}",
    ]
    for title, items in (
        ("Broken", report.broken),
        ("Missing", report.missing),
        ("Weakened", report.weakened),
        ("New verified", report.new_verified),
        ("Still verified", report.still_verified),
    ):
        if not items:
            continue
        lines.extend(["", f"## {title}"])
        for item in items:
            lines.append(f"- **{item.rule_name}** ({item.status}) {item.detail}".rstrip())
    lines.extend(["", "## Guidance"])
    for tip in report.guidance:
        lines.append(f"- {tip}")
    return "\n".join(lines)
