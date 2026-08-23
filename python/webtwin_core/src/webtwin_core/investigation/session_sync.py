from webtwin_core.models.auth import AuthState, SessionStatus
from webtwin_core.models.investigation import InvestigationStatus


def session_status_for_investigation(status: InvestigationStatus) -> SessionStatus:
    if status == InvestigationStatus.AUTH_REQUIRED:
        return SessionStatus.AUTH_REQUIRED
    if status == InvestigationStatus.AUTHENTICATED:
        return SessionStatus.AUTHENTICATED
    if status == InvestigationStatus.FAILED:
        return SessionStatus.FAILED
    if status == InvestigationStatus.BLOCKED:
        return SessionStatus.FAILED
    return SessionStatus.NOT_STARTED


def sync_session_from_investigation(session, investigation) -> None:
    session.session_status = session_status_for_investigation(investigation.status)
    if investigation.status == InvestigationStatus.AUTH_REQUIRED:
        session.auth_state = AuthState.REQUIRED
    elif investigation.status == InvestigationStatus.AUTHENTICATED:
        session.auth_state = AuthState.AUTHENTICATED
        session.auth_verified_at = session.auth_verified_at or session.updated_at
