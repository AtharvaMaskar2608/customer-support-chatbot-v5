"""HTTP routes: ``POST /session``, ``POST /chat``, ``POST /report``.

The three endpoints wire the POC frontend to the agent (P4) and report tools (P2):

- ``POST /session`` — create a trimmed in-memory session (requiring the FinX middleware
  ``finxSessionId`` and ``clientCode``), return ``{session_id}``.
- ``POST /chat`` — stream one agent turn (``agent_reply_stream``) as SSE. Report intents
  end the turn with a ``report_request`` frame carrying the widget spec, then ``done``.
- ``POST /report`` — plain JSON: validate the widget-collected ``params`` against the
  report's registry steps, run the matching middleware client with the session identity
  injected server-side, and return a :class:`ReportRenderPayload`. No model call, no SSE.

Chat responses are ``text/event-stream``; ``/report`` returns a JSON body. An unknown
``session_id`` is a 404; unknown/missing report params are a 422.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.agent.loop import agent_reply_stream
from backend.agent.tools import report_param_names
from backend.api.sessions import create_session, get_session
from backend.api.sse import sse_stream
from backend.contracts.models import (
    ReportColumn,
    ReportRenderPayload,
    ReportResult,
    Session,
)
from backend.tools.finx import (
    get_contract_notes,
    get_detailed_pnl,
    get_global_pnl,
    get_ledger,
    get_tax_report,
)

router = APIRouter()

_ReportType = Literal["ledger", "global_pnl", "detailed_pnl", "contract_notes", "tax_report"]


# --------------------------------------------------------------------------------------
# Request / response models (wire contract)
# --------------------------------------------------------------------------------------


class SessionCreateRequest(BaseModel):
    """Login payload from the POC form. All string fields are trimmed server-side.

    ``finxSessionId`` (the FinX middleware SessionId) and ``clientCode`` are required and
    must be non-empty after trimming — every middleware report call needs both.
    ``sessionToken`` (legacy JWT) is accepted and stored but no longer authorizes reports.
    """

    userId: str
    mobileNo: str
    sessionToken: str
    finxSessionId: str
    clientCode: str


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


class ReportExecuteRequest(BaseModel):
    """Widget submission that runs a report and returns a render payload.

    ``params`` are the structured, widget-collected values — the only accepted parameter
    source. They are validated against the registry's step params for ``report_type``
    (e.g. ``{"group": ..., "from_date": ..., "to_date": ...}`` for ``ledger``); missing or
    unknown keys are rejected with a 422.
    """

    session_id: str
    report_type: _ReportType
    params: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Report render shaping (design D5)
# --------------------------------------------------------------------------------------

# Fixed ledger column map (documented schema).
_LEDGER_COLUMNS: tuple[ReportColumn, ...] = (
    ReportColumn(key="trd_Date", label="Date"),
    ReportColumn(key="voucher", label="Voucher"),
    ReportColumn(key="Narration", label="Description"),
    ReportColumn(key="Debit", label="Debit"),
    ReportColumn(key="Credit", label="Credit"),
    ReportColumn(key="settlement_No", label="Settlement"),
)

_REPORT_TITLES: dict[str, str] = {
    "ledger": "Ledger",
    "global_pnl": "Global P&L",
    "detailed_pnl": "Detailed P&L",
    "contract_notes": "Contract Notes",
    "tax_report": "Tax Report",
}

# Upstream "no data" reasons come back as ok=False on the envelope endpoints (Status:Fail),
# but render as an informational empty notice rather than an error (design D5).
_NO_DATA_ERRORS = {"data not found.", "data not found"}


def _title(report_type: str, params: dict[str, Any]) -> str:
    """Human-readable report title, annotated with the financial year or date range."""
    base = _REPORT_TITLES.get(report_type, "Report")
    if report_type == "tax_report":
        fin_year = params.get("fin_year")
        return f"{base} · {fin_year}" if fin_year else base
    from_date, to_date = params.get("from_date"), params.get("to_date")
    if from_date and to_date:
        return f"{base} · {from_date} → {to_date}"
    return base


def _as_rows(value: Any) -> list[dict]:
    """Coerce an upstream payload into a list of row dicts (tolerant of pending schemas)."""
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict) and value:
        return [value]
    return []


def _dynamic_columns(rows: list[dict]) -> tuple[ReportColumn, ...]:
    """Derive columns from the first row's keys (used until upstream schemas are captured)."""
    if not rows:
        return ()
    return tuple(ReportColumn(key=key, label=key) for key in rows[0])


def _shape_payload(
    report_type: str, params: dict[str, Any], result: ReportResult
) -> ReportRenderPayload:
    """Shape a :class:`ReportResult` into a :class:`ReportRenderPayload` (design D5).

    Contract: failures become ``kind="error"`` with a client-safe message, except upstream
    "no data" which becomes ``kind="empty"``. On success: tax reports become ``kind="link"``
    (the PDF URL, which rides only in this payload — never model context); ledger rows use
    the fixed column map; PNL/contract-note rows derive columns dynamically; an empty result
    (no rows / Go 204) becomes ``kind="empty"`` with the upstream message.
    """
    title = _title(report_type, params)

    if not result.ok:
        error = result.error or "Report unavailable."
        if error.strip().lower() in _NO_DATA_ERRORS:
            return ReportRenderPayload(kind="empty", title=title, message=error)
        return ReportRenderPayload(kind="error", title=title, message=error)

    data = result.data or {}

    if report_type == "tax_report":
        url = data.get("Response")
        if not url:
            return ReportRenderPayload(
                kind="empty", title=title, message="No report available."
            )
        return ReportRenderPayload(kind="link", title=title, url=url)

    if report_type == "contract_notes":
        rows = _as_rows(data.get("Body"))
        if data.get("StatusCode") == 204 or not rows:
            message = data.get("Message") or "Data not found."
            return ReportRenderPayload(kind="empty", title=title, message=message)
        return ReportRenderPayload(
            kind="table", title=title, columns=_dynamic_columns(rows), rows=tuple(rows)
        )

    # Envelope reports (ledger + PNL): rows live under "Response".
    rows = _as_rows(data.get("Response"))
    if not rows:
        return ReportRenderPayload(kind="empty", title=title, message="Data not found.")
    columns = _LEDGER_COLUMNS if report_type == "ledger" else _dynamic_columns(rows)
    return ReportRenderPayload(kind="table", title=title, columns=columns, rows=tuple(rows))


# --------------------------------------------------------------------------------------
# Report dispatch
# --------------------------------------------------------------------------------------


def _run_report(
    session: Session, report_type: str, params: dict[str, Any]
) -> ReportResult:
    """Dispatch a validated report request to its middleware client with session identity.

    Contract: ``params`` have already been validated to exactly match the registry step
    params for ``report_type``, so the keys are guaranteed present. The client is called
    with ``session`` (which supplies ``ClientId``/``SessionId`` server-side); the clients
    never raise, so a failure returns as ``ReportResult(ok=False, ...)``.
    """
    if report_type == "ledger":
        return get_ledger(session, params["group"], params["from_date"], params["to_date"])
    if report_type == "global_pnl":
        return get_global_pnl(
            session, params["group"], params["from_date"], params["to_date"]
        )
    if report_type == "detailed_pnl":
        return get_detailed_pnl(
            session, params["group"], params["from_date"], params["to_date"]
        )
    if report_type == "contract_notes":
        return get_contract_notes(session, params["from_date"], params["to_date"])
    return get_tax_report(session, params["fin_year"])


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


@router.post("/session", response_model=SessionCreateResponse)
def create_session_route(body: SessionCreateRequest) -> SessionCreateResponse:
    """Create an in-memory session from trimmed login inputs; return its ``session_id``.

    Contract: trims all inputs, requires non-empty ``finxSessionId`` and ``clientCode``
    after trimming (422 otherwise), stores the ``Session``, and returns ``{"session_id":
    ...}``. ``finxSessionId`` becomes the middleware ``authorization``/``SessionId`` and
    ``clientCode`` supplies ``ClientId`` for every report call.
    """
    if not body.finxSessionId.strip():
        raise HTTPException(status_code=422, detail="finxSessionId is required")
    if not body.clientCode.strip():
        raise HTTPException(status_code=422, detail="clientCode is required")
    session = create_session(
        user_id=body.userId,
        mobile_no=body.mobileNo,
        session_token=body.sessionToken,
        client_code=body.clientCode,
        finx_session_id=body.finxSessionId,
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
    ``status`` -> ``token`` -> ``citations`` -> ``usage`` -> ``done``, or (for a report
    intent) ``report_request`` -> ``usage`` -> ``done``, with a terminal ``error`` frame on
    failure. Every stream ends in ``done`` or ``error`` (CHO-61).
    """
    session = _require_session(body.session_id)
    events = agent_reply_stream(
        session, body.messages, prior_cost_inr=body.prior_cost_inr
    )
    return EventSourceResponse(sse_stream(events))


@router.post("/report", response_model=ReportRenderPayload)
def report_route(body: ReportExecuteRequest) -> ReportRenderPayload:
    """Run a widget-collected report and return a render payload as plain JSON.

    Contract: resolves ``session_id`` (404 if unknown), validates ``params`` against the
    registry's step params for ``report_type`` — rejecting missing or unknown keys with a
    422 (widget values are the only accepted source) — dispatches to the matching middleware
    client with session identity injected server-side, and returns a
    :class:`ReportRenderPayload` (``table`` | ``link`` | ``empty`` | ``error``). No Anthropic
    API call is made.
    """
    session = _require_session(body.session_id)
    expected = set(report_param_names(body.report_type))
    got = set(body.params)
    if got != expected:
        missing = sorted(expected - got)
        unknown = sorted(got - expected)
        raise HTTPException(
            status_code=422,
            detail=f"invalid params for {body.report_type}: "
            f"missing={missing}, unknown={unknown}",
        )
    result = _run_report(session, body.report_type, body.params)
    return _shape_payload(body.report_type, body.params, result)
