from webtwin_core.models.investigation import InvestigationStatus, TransitionEvent
from webtwin_core.investigation.state_machine import InvalidTransitionError, apply_transition, next_status
from webtwin_core.models import Investigation


def test_happy_path_transitions() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    assert investigation.status == InvestigationStatus.CREATED

    apply_transition(investigation, TransitionEvent.START)
    assert investigation.status == InvestigationStatus.INITIALIZING

    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    assert investigation.status == InvestigationStatus.AUTH_CHECK

    apply_transition(investigation, TransitionEvent.AUTH_OK)
    assert investigation.status == InvestigationStatus.AUTHENTICATED

    apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
    assert investigation.status == InvestigationStatus.EXPLORING

    apply_transition(investigation, TransitionEvent.CAPTURE_OBSERVATION)
    assert investigation.status == InvestigationStatus.OBSERVING

    apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
    assert investigation.status == InvestigationStatus.EXPLORING

    apply_transition(investigation, TransitionEvent.CAPTURE_OBSERVATION)
    assert investigation.status == InvestigationStatus.OBSERVING

    apply_transition(investigation, TransitionEvent.GENERATE_RULES)
    assert investigation.status == InvestigationStatus.GENERATING_RULE

    apply_transition(investigation, TransitionEvent.START_VERIFICATION)
    assert investigation.status == InvestigationStatus.VERIFYING

    apply_transition(investigation, TransitionEvent.COMPLETE)
    assert investigation.status == InvestigationStatus.COMPLETED


def test_auth_required_flow() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.AUTH_REQUIRED)
    assert investigation.status == InvestigationStatus.AUTH_REQUIRED

    apply_transition(investigation, TransitionEvent.AUTH_COMPLETED)
    assert investigation.status == InvestigationStatus.AUTHENTICATED


def test_invalid_transition_raises() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    try:
        apply_transition(investigation, TransitionEvent.COMPLETE)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass


def test_fail_from_observing() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.AUTH_OK)
    apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
    apply_transition(investigation, TransitionEvent.CAPTURE_OBSERVATION)
    apply_transition(investigation, TransitionEvent.FAIL, reason="timeout")
    assert investigation.status == InvestigationStatus.FAILED


def test_block_from_auth_check() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.BLOCK, reason="captcha")
    assert investigation.status == InvestigationStatus.BLOCKED
    assert investigation.blocked_reason == "captcha"


def test_terminal_state_rejects_transitions() -> None:
    investigation = Investigation(goal="test", target_url="https://example.com")
    apply_transition(investigation, TransitionEvent.START)
    apply_transition(investigation, TransitionEvent.INIT_COMPLETE)
    apply_transition(investigation, TransitionEvent.AUTH_OK)
    apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
    apply_transition(investigation, TransitionEvent.COMPLETE)
    assert investigation.status == InvestigationStatus.COMPLETED

    try:
        apply_transition(investigation, TransitionEvent.BEGIN_EXPLORATION)
        raise AssertionError("Expected InvalidTransitionError")
    except InvalidTransitionError:
        pass
