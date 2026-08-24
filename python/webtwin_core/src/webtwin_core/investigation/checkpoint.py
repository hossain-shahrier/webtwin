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


FAIL_EVENTS = {
    TransitionEvent.FAIL,
    TransitionEvent.BROWSER_CRASH,
    TransitionEvent.AUTH_TIMEOUT,
}


def save_checkpoint(
    investigation: Investigation,
    event: TransitionEvent,
    observation_count: int = 0,
) -> None:
    if event in FAIL_EVENTS:
        # Keep exploration + resume status intact; only stamp failure metadata.
        if investigation.checkpoint is not None:
            investigation.checkpoint.last_event = event
            investigation.checkpoint.saved_at = datetime.now(UTC)
        return

    if investigation.status not in CHECKPOINT_STATUSES:
        return

    prior_exploration = None
    if investigation.checkpoint is not None:
        prior_exploration = investigation.checkpoint.exploration

    investigation.checkpoint = InvestigationCheckpoint(
        status=investigation.status,
        target_url=investigation.target_url,
        last_event=event,
        observation_count=observation_count,
        exploration=prior_exploration,
    )


def resume_status(investigation: Investigation) -> InvestigationStatus:
    if investigation.checkpoint is None:
        raise ValueError("No checkpoint available for resume")
    return investigation.checkpoint.status
