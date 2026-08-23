"""SPA mode detection — env or investigation flag."""

from __future__ import annotations

import os

from webtwin_core.models.investigation import Investigation


def spa_mode_enabled(investigation: Investigation | None = None) -> bool:
    env = os.environ.get("WEBTWIN_SPA_MODE", "").lower()
    if env in {"1", "true", "yes"}:
        return True
    if investigation is None:
        return False
    if getattr(investigation, "spa_mode", False):
        return True
    if investigation.environment and "spa" in investigation.environment.lower():
        return True
    scope = (investigation.feature_scope or "").lower()
    if "spa" in scope:
        return True
    goal = investigation.goal_spec
    if goal and goal.scope and "spa" in goal.scope.lower():
        return True
    return False
