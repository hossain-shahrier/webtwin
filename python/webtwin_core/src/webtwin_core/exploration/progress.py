"""Lean durable exploration progress — resume without replaying the whole crawl.

Design goals:
- Small JSON blob on Investigation.checkpoint (already JSONB) — no new tables.
- Persist only resume-critical sets; never duplicate discovered_links / observations.
- Cap list sizes so long crawls stay cheap to write and load.
- Rebuild frontier from discovered_links when the lean frontier is empty (recovery).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from webtwin_core.exploration.budget import ExplorationBudget
    from webtwin_core.exploration.state import ExplorationState
    from webtwin_core.reference_system.site_graph import DiscoveredLink

# Soft caps — keep checkpoint under ~50–100KB even on large sites.
_MAX_FRONTIER = 200
_MAX_PAGES = 300
_MAX_ROUTES = 300
_MAX_TESTED_KEYS = 800
_MAX_EXPLORED_FIELDS = 400


def _dedupe_cap(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


class ExplorationProgress(BaseModel):
    """Minimal crawl cursor stored inside InvestigationCheckpoint."""

    version: int = 1
    last_url: str | None = None
    frontier: list[str] = Field(default_factory=list)
    pages_seen: list[str] = Field(default_factory=list)
    routes_seen: list[str] = Field(default_factory=list)
    tested_action_keys: list[str] = Field(default_factory=list)
    explored_field_targets: list[str] = Field(default_factory=list)
    actions_taken: int = 0
    scrolls_used: int = 0
    budget_actions_used: int = 0
    budget_pages_seen: int = 0
    budget_experiments_used: int = 0
    policy: str | None = None
    url_prefix: str | None = None
    saved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def capped(self) -> "ExplorationProgress":
        """Return a size-bounded copy safe for JSONB persistence."""
        return ExplorationProgress(
            version=self.version,
            last_url=self.last_url,
            frontier=_dedupe_cap(self.frontier, _MAX_FRONTIER),
            pages_seen=_dedupe_cap(self.pages_seen, _MAX_PAGES),
            routes_seen=_dedupe_cap(self.routes_seen, _MAX_ROUTES),
            tested_action_keys=_dedupe_cap(self.tested_action_keys, _MAX_TESTED_KEYS),
            explored_field_targets=_dedupe_cap(self.explored_field_targets, _MAX_EXPLORED_FIELDS),
            actions_taken=self.actions_taken,
            scrolls_used=self.scrolls_used,
            budget_actions_used=self.budget_actions_used,
            budget_pages_seen=self.budget_pages_seen,
            budget_experiments_used=self.budget_experiments_used,
            policy=self.policy,
            url_prefix=self.url_prefix,
            saved_at=self.saved_at,
        )


def snapshot_progress(
    state: "ExplorationState",
    budget: "ExplorationBudget",
    *,
    last_url: str | None,
    policy: str | None = None,
) -> ExplorationProgress:
    return ExplorationProgress(
        last_url=last_url or state.url,
        frontier=list(state.frontier),
        pages_seen=list(state.pages_seen_urls),
        routes_seen=list(state.routes_seen),
        tested_action_keys=list(state.tested_action_keys),
        explored_field_targets=list(state.explored_field_targets),
        actions_taken=state.actions_taken,
        scrolls_used=state.scrolls_used,
        budget_actions_used=budget.actions_used,
        budget_pages_seen=budget.pages_seen,
        budget_experiments_used=budget.experiments_used,
        policy=policy,
        url_prefix=state.url_prefix,
        saved_at=datetime.now(UTC),
    ).capped()


def reset_budget_for_resume(budget: "ExplorationBudget") -> None:
    """Give a resumed crawl a fresh action/page allowance."""
    budget.actions_used = 0
    budget.pages_seen = 0
    budget.experiments_used = 0


def apply_progress(
    state: "ExplorationState",
    budget: "ExplorationBudget",
    progress: ExplorationProgress,
) -> None:
    """Hydrate in-memory exploration state from a durable progress blob."""
    if progress.url_prefix and not state.url_prefix:
        state.url_prefix = progress.url_prefix
    state.url = progress.last_url or state.url
    state.frontier = list(progress.frontier)
    state.pages_seen_urls = list(progress.pages_seen)
    state.routes_seen = list(progress.routes_seen)
    state.tested_action_keys = list(progress.tested_action_keys)
    state.explored_field_targets = list(progress.explored_field_targets)
    state.actions_taken = progress.actions_taken
    state.scrolls_used = progress.scrolls_used
    budget.actions_used = progress.budget_actions_used
    budget.pages_seen = progress.budget_pages_seen
    budget.experiments_used = progress.budget_experiments_used


def rebuild_frontier_from_links(
    state: "ExplorationState",
    links: list[Any],
    *,
    origin_url: str,
) -> int:
    """If frontier was truncated/lost, rebuild from durable discovered_links."""
    from webtwin_core.reference_system.site_graph import DiscoveredLink, normalize_screen_id

    before = len(state.frontier)
    typed: list[DiscoveredLink] = []
    for link in links:
        if isinstance(link, DiscoveredLink):
            typed.append(link)
        elif isinstance(link, dict):
            try:
                typed.append(DiscoveredLink.model_validate(link))
            except Exception:
                continue
    state.enqueue_frontier_from_links(typed, origin_url=origin_url)
    state.frontier = [
        item for item in state.frontier if not state._screen_visited(normalize_screen_id(item))
    ]
    return max(0, len(state.frontier) - before)


def progress_from_checkpoint(checkpoint: Any) -> ExplorationProgress | None:
    if checkpoint is None:
        return None
    exploration = getattr(checkpoint, "exploration", None)
    if exploration is None and isinstance(checkpoint, dict):
        exploration = checkpoint.get("exploration")
    if exploration is None:
        return None
    if isinstance(exploration, ExplorationProgress):
        return exploration
    if isinstance(exploration, dict):
        try:
            return ExplorationProgress.model_validate(exploration)
        except Exception:
            return None
    return None
