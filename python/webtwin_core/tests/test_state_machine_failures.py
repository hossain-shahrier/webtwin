from webtwin_core.investigation.state_machine import InvalidTransitionError, apply_transition, is_idempotent_retry
from webtwin_core.models import Investigation, InvestigationStatus, TransitionEvent
from webtwin_core.models.investigation import InvestigationTransition


def _to_exploring(investigation: Investigation) -> None:
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.AUTH_OK)
    apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)


def test_browser_crash_from_exploring() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    _to_exploring(investigation)
    apply_transition(investigation, TransitionEvent.BROWSER_CRASH, reason="browser disconnected")
    assert investigation.status == InvestigationStatus.FAILED
    assert investigation.failure_reason == "browser disconnected"
    assert investigation.checkpoint is not None
    assert investigation.checkpoint.status == InvestigationStatus.EXPLORING


def test_auth_timeout_from_auth_required() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.AUTH_REQUIRED)
    apply_transition(investigation, TransitionEvent.AUTH_TIMEOUT, reason="timeout")
    assert investigation.status == InvestigationStatus.FAILED
    assert investigation.failure_reason == "timeout"


def test_cancel_from_verifying() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    _to_exploring(investigation)
    apply_transition(investigation, TransitionEvent.CAPTURE_OBSERVATION)
    apply_transition(investigation, TransitionEvent.GENERATE_RULES)
    apply_transition(investigation, TransitionEvent.START_VERIFICATION)
    apply_transition(investigation, TransitionEvent.CANCEL, reason="user cancelled")
    assert investigation.status == InvestigationStatus.CANCELLED


def test_resume_from_failed_uses_checkpoint() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    _to_exploring(investigation)
    apply_transition(investigation, TransitionEvent.BROWSER_CRASH, reason="crash")
    apply_transition(investigation, TransitionEvent.RESUME)
    assert investigation.status == InvestigationStatus.EXPLORING
    assert investigation.failure_reason is None


def test_completed_rejects_exploring() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    _to_exploring(investigation)
    apply_transition(investigation, TransitionEvent.COMPLETE)
    try:
        apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass


def test_idempotent_retry_does_not_change_state() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    last = InvestigationTransition(
        investigation_id=investigation.id,
        from_status=InvestigationStatus.CREATED,
        to_status=InvestigationStatus.INITIALIZING,
        event=TransitionEvent.START,
    )
    result = apply_transition(
        investigation,
        TransitionEvent.START,
        last_transition=InvestigationTransition(
            investigation_id=investigation.id,
            from_status=InvestigationStatus.CREATED,
            to_status=InvestigationStatus.INITIALIZING,
            event=TransitionEvent.START,
        ),
    )
    assert result is None
    assert investigation.status == InvestigationStatus.INITIALIZING
    assert is_idempotent_retry(last, InvestigationStatus.INITIALIZING, TransitionEvent.START)
