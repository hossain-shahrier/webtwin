"""Debounced crawl-progress sync to the API — durable resume without heavy writes."""

from __future__ import annotations

from uuid import UUID

from webtwin_core.exploration.budget import ExplorationBudget
from webtwin_core.exploration.progress import snapshot_progress
from webtwin_core.exploration.state import ExplorationState

from browser.client.api import ApiClient


class ExplorationProgressSync:
    """
    Persist lean progress on page boundaries / every N actions / on force flush.

    Writes merge into investigation.checkpoint.exploration (JSONB) — no new table.
    """

    def __init__(
        self,
        client: ApiClient,
        investigation_id: UUID,
        *,
        policy: str | None = None,
        every_actions: int = 2,
    ) -> None:
        self.client = client
        self.investigation_id = investigation_id
        self.policy = policy
        self.every_actions = max(1, every_actions)
        self._last_saved_actions = -1
        self._dirty = False

    def mark_dirty(self) -> None:
        self._dirty = True

    def maybe_save(
        self,
        state: ExplorationState,
        budget: ExplorationBudget,
        *,
        last_url: str | None,
        force: bool = False,
        reason: str = "periodic",
    ) -> bool:
        if not force and not self._dirty:
            return False
        if not force and (state.actions_taken - self._last_saved_actions) < self.every_actions:
            return False
        progress = snapshot_progress(state, budget, last_url=last_url, policy=self.policy)
        try:
            self.client.save_exploration_progress(self.investigation_id, progress)
            self._last_saved_actions = state.actions_taken
            self._dirty = False
            print(
                f"[WebTwin] Progress saved ({reason}): "
                f"pages={len(progress.pages_seen)} frontier={len(progress.frontier)} "
                f"actions={progress.actions_taken} url={(progress.last_url or '')[:80]}"
            )
            return True
        except Exception as error:
            print(f"[WebTwin] Progress save failed: {error}")
            return False
