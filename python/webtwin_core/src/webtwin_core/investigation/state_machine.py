from datetime import UTC, datetime

from webtwin_core.investigation.checkpoint import resume_status, save_checkpoint
from webtwin_core.models.investigation import (
    Investigation,
    InvestigationStatus,
    InvestigationTransition,
    TransitionEvent,
)
from webtwin_core.models.auth import AuthPauseMetadata, AuthPauseReason


class InvalidTransitionError(Exception):
    def __init__(self, current: InvestigationStatus, event: TransitionEvent) -> None:
        super().__init__(f"Invalid transition: {current.value} + {event.value}")
        self.current = current
        self.event = event


class DuplicateTransitionError(Exception):
    """Raised when a transition would corrupt investigation state."""

    def __init__(self, investigation_id, event: TransitionEvent) -> None:
        super().__init__(f"Duplicate transition rejected: {event.value}")
        self.investigation_id = investigation_id
        self.event = event


TERMINAL_STATUSES = {
    InvestigationStatus.COMPLETED,
    InvestigationStatus.FAILED,
    InvestigationStatus.CANCELLED,
}

TRANSITIONS: dict[tuple[InvestigationStatus, TransitionEvent], InvestigationStatus] = {
    (InvestigationStatus.CREATED, TransitionEvent.START): InvestigationStatus.INITIALIZING,
    (InvestigationStatus.INITIALIZING, TransitionEvent.INIT_COMPLETE): InvestigationStatus.AUTH_CHECK,
    (InvestigationStatus.AUTH_CHECK, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.AUTH_CHECK, TransitionEvent.AUTH_OK): InvestigationStatus.AUTHENTICATED,
    (InvestigationStatus.AUTH_CHECK, TransitionEvent.BLOCK): InvestigationStatus.BLOCKED,
    (InvestigationStatus.AUTH_REQUIRED, TransitionEvent.AUTH_COMPLETED): InvestigationStatus.AUTHENTICATED,
    (InvestigationStatus.AUTH_REQUIRED, TransitionEvent.CANCEL): InvestigationStatus.CANCELLED,
    (InvestigationStatus.AUTH_REQUIRED, TransitionEvent.BLOCK): InvestigationStatus.BLOCKED,
    (InvestigationStatus.AUTHENTICATED, TransitionEvent.BEGIN_EXPLORATION): InvestigationStatus.EXPLORING,
    (InvestigationStatus.EXPLORING, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.OBSERVING, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.AUTHENTICATED, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.GENERATING_RULE, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.VERIFYING, TransitionEvent.AUTH_REQUIRED): InvestigationStatus.AUTH_REQUIRED,
    (InvestigationStatus.EXPLORING, TransitionEvent.CAPTURE_OBSERVATION): InvestigationStatus.OBSERVING,
    (InvestigationStatus.OBSERVING, TransitionEvent.BEGIN_EXPLORATION): InvestigationStatus.EXPLORING,
    (InvestigationStatus.OBSERVING, TransitionEvent.GENERATE_RULES): InvestigationStatus.GENERATING_RULE,
    (InvestigationStatus.GENERATING_RULE, TransitionEvent.START_VERIFICATION): InvestigationStatus.VERIFYING,
    (InvestigationStatus.GENERATING_RULE, TransitionEvent.COMPLETE): InvestigationStatus.COMPLETED,
    (InvestigationStatus.EXPLORING, TransitionEvent.START_VERIFICATION): InvestigationStatus.VERIFYING,
    (InvestigationStatus.VERIFYING, TransitionEvent.VERIFICATION_COMPLETE): InvestigationStatus.EXPLORING,
    (InvestigationStatus.VERIFYING, TransitionEvent.COMPLETE): InvestigationStatus.COMPLETED,
    (InvestigationStatus.VERIFYING, TransitionEvent.CANCEL): InvestigationStatus.CANCELLED,
    (InvestigationStatus.EXPLORING, TransitionEvent.COMPLETE): InvestigationStatus.COMPLETED,
    (InvestigationStatus.BLOCKED, TransitionEvent.AUTH_COMPLETED): InvestigationStatus.AUTHENTICATED,
    (InvestigationStatus.BLOCKED, TransitionEvent.CANCEL): InvestigationStatus.CANCELLED,
}

FAIL_TRANSITIONS = {
    InvestigationStatus.INITIALIZING,
    InvestigationStatus.AUTH_CHECK,
    InvestigationStatus.AUTH_REQUIRED,
    InvestigationStatus.AUTHENTICATED,
    InvestigationStatus.EXPLORING,
    InvestigationStatus.OBSERVING,
    InvestigationStatus.GENERATING_RULE,
    InvestigationStatus.VERIFYING,
}


def next_status(current: InvestigationStatus, event: TransitionEvent) -> InvestigationStatus:
    if event in {TransitionEvent.FAIL, TransitionEvent.BROWSER_CRASH, TransitionEvent.AUTH_TIMEOUT}:
        if current in FAIL_TRANSITIONS:
            return InvestigationStatus.FAILED

    try:
        return TRANSITIONS[(current, event)]
    except KeyError as error:
        raise InvalidTransitionError(current, event) from error


def is_idempotent_retry(
    last_transition: InvestigationTransition | None,
    current_status: InvestigationStatus,
    event: TransitionEvent,
) -> bool:
    if last_transition is None or last_transition.event != event:
        return False
    try:
        expected = next_status(last_transition.from_status, event)
    except InvalidTransitionError:
        return False
    return current_status == expected == last_transition.to_status


def apply_transition(
    investigation: Investigation,
    event: TransitionEvent,
    reason: str | None = None,
    auth_pause: AuthPauseMetadata | None = None,
    last_transition: InvestigationTransition | None = None,
    observation_count: int = 0,
) -> InvestigationStatus | None:
    if investigation.status in TERMINAL_STATUSES:
        if not (investigation.status == InvestigationStatus.FAILED and event == TransitionEvent.RESUME):
            raise InvalidTransitionError(investigation.status, event)

    if is_idempotent_retry(last_transition, investigation.status, event):
        return None

    previous = investigation.status

    if event == TransitionEvent.RESUME:
        if previous != InvestigationStatus.FAILED:
            raise InvalidTransitionError(previous, event)
        new_status = resume_status(investigation)
        investigation.failure_reason = None
    else:
        new_status = next_status(previous, event)

    investigation.status = new_status
    investigation.updated_at = datetime.now(UTC)

    if event in {TransitionEvent.FAIL, TransitionEvent.BROWSER_CRASH, TransitionEvent.AUTH_TIMEOUT}:
        investigation.failure_reason = reason
    if event == TransitionEvent.BLOCK and reason:
        investigation.blocked_reason = reason
    if new_status == InvestigationStatus.AUTHENTICATED:
        investigation.blocked_reason = None
        investigation.auth_pause = None
    if event == TransitionEvent.AUTH_REQUIRED:
        investigation.auth_pause = auth_pause or AuthPauseMetadata(
            reason=AuthPauseReason.LOGIN_REQUIRED,
            resume_allowed=True,
            url=investigation.target_url,
            message=reason,
        )
    if new_status == InvestigationStatus.CANCELLED:
        investigation.failure_reason = reason or "cancelled"

    save_checkpoint(investigation, event, observation_count=observation_count)
    return new_status
