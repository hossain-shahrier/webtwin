"""Checkpoint durability tests."""

from uuid import uuid4

from webtwin_core.exploration.progress import ExplorationProgress
from webtwin_core.investigation.checkpoint import save_checkpoint
from webtwin_core.models.investigation import (
    Investigation,
    InvestigationCheckpoint,
    InvestigationStatus,
    TransitionEvent,
)


def test_save_checkpoint_preserves_exploration_on_fail() -> None:
    inv_id = uuid4()
    progress = ExplorationProgress(
        last_url="https://shop.example/cart-2/",
        frontier=["https://shop.example/on-sale/"],
        pages_seen=["https://shop.example/", "https://shop.example/cart-2/"],
        actions_taken=42,
    )
    investigation = Investigation(
        id=inv_id,
        goal="test",
        target_url="https://shop.example/",
        status=InvestigationStatus.FAILED,
        checkpoint=InvestigationCheckpoint(
            status=InvestigationStatus.EXPLORING,
            target_url="https://shop.example/",
            exploration=progress.model_dump(mode="json"),
        ),
    )
    save_checkpoint(investigation, TransitionEvent.FAIL, observation_count=10)
    assert investigation.checkpoint is not None
    assert investigation.checkpoint.status == InvestigationStatus.EXPLORING
    assert investigation.checkpoint.exploration["last_url"] == "https://shop.example/cart-2/"
    assert investigation.checkpoint.exploration["actions_taken"] == 42
    assert investigation.checkpoint.last_event == TransitionEvent.FAIL
