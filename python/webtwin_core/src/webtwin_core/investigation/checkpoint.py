from datetime import UTC, datetime

from webtwin_core.models.investigation import (
    Investigation,
    InvestigationStatus,
    TransitionEvent,
)
from webtwin_core.models.investigation import InvestigationCheckpoint

CHECKPOINT_STATUSES = {
    InvestigationStatus.AUTHENTICATED,
    InvestigationStatus.EXPLORING,
    InvestigationStatus.OBSERVING,
    InvestigationStatus.GENERATING_RULE,
    InvestigationStatus.VERIFYING,
    InvestigationStatus.AUTH_REQUIRED,
}


def save_checkpoint(
    investigation: Investigation,
    event: TransitionEvent,
    observation_count: int = 0,
) -> None:
    if investigation.status not in CHECKPOINT_STATUSES:
        return

    investigation.checkpoint = InvestigationCheckpoint(
        status=investigation.status,
        target_url=investigation.target_url,
        last_event=event,
        observation_count=observation_count,
    )


def resume_status(investigation: Investigation) -> InvestigationStatus:
    if investigation.checkpoint is None:
        raise ValueError("No checkpoint available for resume")
    return investigation.checkpoint.status
