"""In-memory session store for the POC.

``create_session`` trims every login input, builds an immutable
:class:`~backend.contracts.models.Session`, and stores it keyed by the session's own
generated ``session_id`` — so the store key and the tracing ``thread_id`` are the same
value. Sessions live only in process memory: they do not survive a restart and are not
shared across instances (acceptable for a single-instance POC; flagged for production).
"""

from __future__ import annotations

from backend.contracts.models import Session

# session_id -> Session. Process-local and unbounded; the POC runs a single instance.
_SESSIONS: dict[str, Session] = {}


def create_session(
    user_id: str,
    mobile_no: str,
    session_token: str,
    client_code: str,
    finx_session_id: str,
) -> Session:
    """Create and store a :class:`Session` from trimmed login inputs, returning it.

    Contract: strips leading/trailing whitespace on every input, constructs a ``Session``
    whose ``session_id`` doubles as the store key, and retains the ``finx_session_id`` (the
    FinX middleware SessionId) and ``client_code`` used to authorize/identify report calls.
    ``session_token`` (legacy JWT) is stored but no longer authorizes any report call.
    Requiredness of ``finx_session_id``/``client_code`` is enforced at the API boundary. The
    returned ``session_id`` is what the client passes back on ``/chat`` and ``/report``.
    """
    session = Session(
        client_code=client_code.strip(),
        user_id=user_id.strip(),
        mobile_no=mobile_no.strip(),
        session_token=session_token.strip(),
        finx_session_id=finx_session_id.strip(),
    )
    _SESSIONS[session.session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Return the stored :class:`Session` for ``session_id``, or ``None`` if unknown."""
    return _SESSIONS.get(session_id)


def clear_sessions() -> None:
    """Drop all stored sessions (used by tests; also resets state between runs)."""
    _SESSIONS.clear()
