"""HTTP routes: ``POST /session``, ``POST /chat``, ``POST /report``.

The three endpoints wire the POC frontend to the agent (P4) and report tools (P2):

- ``POST /session`` — create a trimmed in-memory session, return ``{session_id}``.
- ``POST /chat`` — stream one agent turn (``agent_reply_stream``) as SSE.
- ``POST /report`` — run the widget-collected report tool, then resume the paused turn
  (``resume_report_stream``) and stream the summary as SSE.

All request bodies carry the ``session_id`` returned by ``/session``; an unknown id is a
404. Chat/report responses are ``text/event-stream`` (see :mod:`backend.api.sse`); any
error inside a stream becomes a terminal ``error`` frame rather than a dropped connection.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.agent.loop import agent_reply_stream, resume_report_stream
from backend.api.sessions import create_session, get_session
from backend.api.sse import sse_stream
from backend.contracts.models import ReportResult, Session
from backend.tools.finx import cml_report, contract_note

router = APIRouter()


# --------------------------------------------------------------------------------------
# Request / response models (wire contract)
# --------------------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    """Login payload from the POC form. All string fields are trimmed server-side."""

    userId: str
    mobileNo: str
    sessionToken: str
    clientCode: str | None = None


class SessionCreateResponse(BaseModel):
    """Response to ``POST /session``: the id the client echoes on every later call."""

    session_id: str


class ChatRequest(BaseModel):
    """Chat turn: the session id plus the full Anthropic ``messages`` history.

    ``prior_cost_inr`` is the conversation's cumulative cost before this turn (0 on the
    first turn); the client reads it from the previous ``usage`` frame and passes it back so
    ``cumulative_cost_inr`` keeps accruing across turns.
    """

    session_id: str
    messages: list[dict[str, Any]]
    prior_cost_inr: float = 0.0


class ReportRequest(BaseModel):
    """Widget submission that resumes a turn paused on a ``report_request``.

    ``params`` are the structured, widget-collected values for the report tool
    (``{"client_id": ...}`` for CML; ``{"mobile_no": ..., "contract_date": ...}`` for a
    contract note). ``tool_use_id`` and ``messages`` are the pending Anthropic tool-use id
    and history the client retained from the pause.
    """

    session_id: str
    report_type: Literal["cml", "contract_note"]
    params: dict[str, Any] = Field(default_factory=dict)
    tool_use_id: str
    messages: list[dict[str, Any]]
    prior_cost_inr: float = 0.0


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


@router.post("/session", response_model=SessionCreateResponse)
def create_session_route(body: SessionCreateRequest) -> SessionCreateResponse:
    """Create an in-memory session from trimmed login inputs; return its ``session_id``.

    Contract: trims all inputs (see :func:`~backend.api.sessions.create_session`), stores
    the ``Session``, and returns ``{"session_id": ...}``. The ``sessionToken`` (JWT) is
    retained for downstream FinX report calls.
    """
    session = create_session(
        user_id=body.userId,
        mobile_no=body.mobileNo,
        session_token=body.sessionToken,
        client_code=body.clientCode,
    )
    return SessionCreateResponse(session_id=session.session_id)


def _require_session(session_id: str) -> Session:
    """Look up a stored session or raise ``404`` for an unknown ``session_id``."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session_id")
    return session


@router.post("/chat")
def chat_route(body: ChatRequest) -> EventSourceResponse:
    """Stream one agent turn over SSE.

    Contract: resolves ``session_id`` (404 if unknown), then returns an
    ``EventSourceResponse`` over ``agent_reply_stream(session, messages)`` — forwarding
    ``status`` -> ``token`` -> ``citations`` -> ``usage`` -> (``report_request``) ->
    ``done``, with a terminal ``error`` frame on failure.
    """
    session = _require_session(body.session_id)
    events = agent_reply_stream(
        session, body.messages, prior_cost_inr=body.prior_cost_inr
    )
    return EventSourceResponse(sse_stream(events))


def _run_report(session: Session, report_type: str, params: dict[str, Any]) -> ReportResult:
    """Dispatch a report type to its FinX tool with the structured widget ``params``.

    Contract: ``cml`` -> ``cml_report(session, client_id)``; ``contract_note`` ->
    ``contract_note(session, mobile_no, contract_date)``. The report tools never raise —
    a failure comes back as ``ReportResult(ok=False, error=...)``. A missing required param
    surfaces as a ``400`` rather than a ``KeyError``.
    """
    try:
        if report_type == "cml":
            return cml_report(session, params["client_id"])
        return contract_note(session, params["mobile_no"], params["contract_date"])
    except KeyError as exc:
        raise HTTPException(
            status_code=400, detail=f"missing report param: {exc.args[0]}"
        ) from exc


@router.post("/report")
def report_route(body: ReportRequest) -> EventSourceResponse:
    """Run the widget-collected report tool, then resume the paused turn as SSE.

    Contract: resolves ``session_id`` (404 if unknown), runs the matching report tool with
    the structured ``params`` and the session (getting a ``ReportResult``), then returns an
    ``EventSourceResponse`` over ``resume_report_stream(session, messages, tool_use_id,
    report_result)`` — streaming the factual summary through to ``done`` (or a terminal
    ``error`` frame on failure).
    """
    session = _require_session(body.session_id)
    result = _run_report(session, body.report_type, body.params)
    events = resume_report_stream(
        session,
        body.messages,
        body.tool_use_id,
        result,
        prior_cost_inr=body.prior_cost_inr,
    )
    return EventSourceResponse(sse_stream(events))
