"""Role Diff Twin — behavioral delta between two persona maps."""

from __future__ import annotations

from pydantic import BaseModel, Field

from webtwin_core.reference_system.catalog import ApplicationCatalog, RoleSystemMap


class RoleDiffSpec(BaseModel):
    application_key: str
    left_role: str
    right_role: str
    left_only_entities: list[str] = Field(default_factory=list)
    right_only_entities: list[str] = Field(default_factory=list)
    shared_entities: list[str] = Field(default_factory=list)
    left_only_verified_rules: list[str] = Field(default_factory=list)
    right_only_verified_rules: list[str] = Field(default_factory=list)
    shared_verified_rules: list[str] = Field(default_factory=list)
    left_only_flows: list[str] = Field(default_factory=list)
    right_only_flows: list[str] = Field(default_factory=list)
    screen_count_delta: int = 0
    navigation_count_delta: int = 0
    summary: str = ""
    guidance: list[str] = Field(default_factory=list)


def _diff_lists(left: list[str], right: list[str]) -> tuple[list[str], list[str], list[str]]:
    left_set = set(left)
    right_set = set(right)
    return (
        sorted(left_set - right_set),
        sorted(right_set - left_set),
        sorted(left_set & right_set),
    )


def compute_role_diff(
    catalog: ApplicationCatalog,
    left_role: str,
    right_role: str,
) -> RoleDiffSpec:
    left = catalog.roles.get(left_role) or RoleSystemMap(role_scope=left_role)
    right = catalog.roles.get(right_role) or RoleSystemMap(role_scope=right_role)

    lo_ent, ro_ent, shared_ent = _diff_lists(left.entity_names, right.entity_names)
    lo_rules, ro_rules, shared_rules = _diff_lists(
        left.verified_rule_names, right.verified_rule_names
    )
    lo_flows, ro_flows, _ = _diff_lists(left.flow_names, right.flow_names)

    summary = (
        f"{left_role} vs {right_role}: "
        f"{len(lo_rules)}/{len(ro_rules)} exclusive verified rules, "
        f"{len(shared_rules)} shared, "
        f"{len(lo_ent)}/{len(ro_ent)} exclusive entities."
    )
    return RoleDiffSpec(
        application_key=catalog.application_key,
        left_role=left_role,
        right_role=right_role,
        left_only_entities=lo_ent,
        right_only_entities=ro_ent,
        shared_entities=shared_ent,
        left_only_verified_rules=lo_rules,
        right_only_verified_rules=ro_rules,
        shared_verified_rules=shared_rules,
        left_only_flows=lo_flows,
        right_only_flows=ro_flows,
        screen_count_delta=right.screen_count - left.screen_count,
        navigation_count_delta=right.navigation_count - left.navigation_count,
        summary=summary,
        guidance=[
            "Implement shared verified rules once; gate exclusive rules by role.",
            "Exclusive entities usually imply separate screens or permissions.",
            "Re-run investigations per role after auth changes before trusting this delta.",
        ],
    )


def _bullets(items: list[str]) -> list[str]:
    if not items:
        return ["- _none_"]
    return [f"- {name}" for name in items]


def format_role_diff_markdown(spec: RoleDiffSpec) -> str:
    lines = [
        "# WebTwin Role Diff",
        "",
        f"- Application: `{spec.application_key}`",
        f"- Left: `{spec.left_role}` · Right: `{spec.right_role}`",
        f"- {spec.summary}",
        "",
        f"## Verified rules only in `{spec.left_role}`",
        *_bullets(spec.left_only_verified_rules),
        "",
        f"## Verified rules only in `{spec.right_role}`",
        *_bullets(spec.right_only_verified_rules),
        "",
        "## Shared verified rules",
        *_bullets(spec.shared_verified_rules),
        "",
        "## Guidance",
    ]
    for tip in spec.guidance:
        lines.append(f"- {tip}")
    return "\n".join(lines)
