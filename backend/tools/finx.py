"""Read-only FinX middleware report clients.

Five thin authenticated ``httpx`` POST calls, all on a single middleware host
(``settings.finx_middleware_base_url``). Every parameter originates from a frontend
widget (never the model) and each call returns a :class:`ReportResult`. They **never
raise**: a network error, timeout, or in-band upstream failure is mapped to
``ReportResult(ok=False, error=...)`` so an upstream outage can never crash the agent.

Errors are in-band — the HTTP status is ``200`` even on failure — and two body dialects
share the host:

- ``/api/middleware/*`` — PascalCase, the SessionId is repeated in the JSON body. Success
  is ``Status == "Success"``; otherwise ``ok=False`` carries the upstream ``Reason``.
- ``/middleware-go/*`` — snake_case, header-only auth. The body carries an HTTP-style
  ``StatusCode``: ``204`` is a successful *empty* result (``ok=True``, no rows), any other
  non-``200`` is a failure carrying the upstream ``Message``.
"""

import re

import httpx

from backend.config.settings import get_settings
from backend.contracts.models import ReportResult, Session

# Middleware dates are YYYY-MM-DD; validated locally before any network call so a bad
# widget value fails fast without a round-trip.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Bounded so a hung upstream surfaces as ok=False rather than stalling the agent turn.
_TIMEOUT = httpx.Timeout(30.0)

# Fixed platform origin sent on every middleware call.
_ORIGIN = "https://finx.choiceindia.com"

# Client-version header required by a subset of endpoints (Detailed PNL, Contract Notes,
# Tax Report). A fixed platform constant, not per-session.
_FROM_HEADER = "Web_finx.choiceindia.com_V_4.6.0.4"


def _headers(session: Session, *, with_from_header: bool = False) -> dict[str, str]:
    """Auth/identity headers for a middleware call.

    Contract: ``authorization`` carries ``session.finx_session_id`` (the middleware
    SessionId), ``origin`` is the fixed platform origin, and the client-version ``from``
    header is added only ``with_from_header`` (Detailed PNL, Contract Notes, Tax Report).
    """
    headers = {
        "authorization": session.finx_session_id,
        "origin": _ORIGIN,
    }
    if with_from_header:
        headers["from"] = _FROM_HEADER
    return headers


def _valid_dates(*dates: str) -> str | None:
    """Return an error message if any date is not ``YYYY-MM-DD``, else ``None``."""
    for date in dates:
        if not _DATE_RE.match(date):
            return f"invalid date '{date}'; expected YYYY-MM-DD"
    return None


def _middleware_post(
    session: Session,
    path: str,
    body: dict,
    *,
    with_from_header: bool = False,
    client: httpx.Client | None = None,
) -> ReportResult:
    """POST ``body`` to ``finx_middleware_base_url + path`` and contain every failure.

    Contract: on a 2xx JSON response returns ``ReportResult(ok=True, data=<envelope>)``
    carrying the parsed body verbatim — per-endpoint in-band mapping (envelope ``Status``
    vs Go ``StatusCode``) is applied by the caller, whose dialect differs. Any transport
    error, timeout, non-2xx status, or non-JSON body maps to ``ReportResult(ok=False,
    error=...)`` without ever raising. A caller-supplied ``client`` (e.g. one wrapping a
    mock transport) is used as-is; otherwise a short-lived client is opened and closed.
    """
    settings = get_settings()
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=_TIMEOUT)
    try:
        response = client.post(
            settings.finx_middleware_base_url + path,
            json=body,
            headers=_headers(session, with_from_header=with_from_header),
        )
        if response.is_success:
            return ReportResult(ok=True, data=response.json())
        return ReportResult(ok=False, error=f"upstream {response.status_code}")
    except httpx.HTTPError as exc:
        return ReportResult(ok=False, error=f"request failed: {exc.__class__.__name__}")
    except ValueError:
        # 2xx but the body was not valid JSON.
        return ReportResult(ok=False, error="invalid response body")
    finally:
        if owns_client:
            client.close()


def _map_envelope(result: ReportResult) -> ReportResult:
    """Map a transport-level result through the ``/api/middleware`` envelope semantics.

    Contract: a transport failure (``ok=False``) passes through unchanged. Otherwise
    ``Status == "Success"`` stays ``ok=True`` with the envelope; any other status becomes
    ``ok=False`` carrying the upstream ``Reason`` (e.g. "Data not found.").
    """
    if not result.ok:
        return result
    envelope = result.data or {}
    if envelope.get("Status") == "Success":
        return ReportResult(ok=True, data=envelope)
    return ReportResult(ok=False, error=envelope.get("Reason") or "upstream error")


def get_ledger(
    session: Session,
    group: str,
    from_date: str,
    to_date: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Fetch ledger entries for the session's client over ``[from_date, to_date]``.

    Contract: validates the dates first (invalid → ``ok=False``, no network call), then
    ``POST /api/middleware/GetLedgerDetails`` with body ``{LoginId:"JIFFY", ClientId:
    client_code, Group, FromDate, ToDate, SessionId: finx_session_id}``. ``group`` is a
    widget value in ``{"Group1","MTF"}`` (Normal / MTF). Never raises.
    """
    err = _valid_dates(from_date, to_date)
    if err:
        return ReportResult(ok=False, error=err)
    return _map_envelope(
        _middleware_post(
            session,
            "/api/middleware/GetLedgerDetails",
            {
                "LoginId": "JIFFY",
                "ClientId": session.client_code,
                "Group": group,
                "FromDate": from_date,
                "ToDate": to_date,
                "SessionId": session.finx_session_id,
            },
            client=client,
        )
    )


def get_global_pnl(
    session: Session,
    group: str,
    from_date: str,
    to_date: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Fetch the global (summary) P&L for a segment over ``[from_date, to_date]``.

    Contract: validates the dates first, then ``POST /api/middleware/GetGlobalPNLNew``
    with body ``{UserId: client_code, ClientId: client_code, Group, FromDate, ToDate,
    With_Exp:1, SessionId}``. ``group`` is a widget value in ``{"Cash","Derv","Comm"}``
    (Equity / Derivatives / Commodity). Never raises.
    """
    err = _valid_dates(from_date, to_date)
    if err:
        return ReportResult(ok=False, error=err)
    return _map_envelope(
        _middleware_post(
            session,
            "/api/middleware/GetGlobalPNLNew",
            {
                "UserId": session.client_code,
                "ClientId": session.client_code,
                "Group": group,
                "FromDate": from_date,
                "ToDate": to_date,
                "With_Exp": 1,
                "SessionId": session.finx_session_id,
            },
            client=client,
        )
    )


def get_detailed_pnl(
    session: Session,
    group: str,
    from_date: str,
    to_date: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Fetch the detailed (scrip-level) P&L for a segment over ``[from_date, to_date]``.

    Contract: validates the dates first, then ``POST /api/middleware/GetDetailedPNL`` with
    the client-version ``from:`` header and body ``{UserId:"neuron", ClientId: client_code,
    Group, FromDate, ToDate, SessionId}`` — ``UserId`` is the fixed platform value, not the
    client code. ``group`` is a widget value in ``{"Group1","Group23"}`` (Standard /
    Commodity). Never raises.
    """
    err = _valid_dates(from_date, to_date)
    if err:
        return ReportResult(ok=False, error=err)
    return _map_envelope(
        _middleware_post(
            session,
            "/api/middleware/GetDetailedPNL",
            {
                "UserId": "neuron",
                "ClientId": session.client_code,
                "Group": group,
                "FromDate": from_date,
                "ToDate": to_date,
                "SessionId": session.finx_session_id,
            },
            with_from_header=True,
            client=client,
        )
    )


def get_contract_notes(
    session: Session,
    from_date: str,
    to_date: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Fetch contract notes for the session's client over ``[from_date, to_date]``.

    Contract: validates the dates first, then ``POST /middleware-go/report/contract`` (the
    Go middleware) with the client-version ``from:`` header and snake_case body
    ``{client_id: client_code, from_date, to_date}`` — no SessionId in the body; the
    ``authorization`` header is the only auth. Maps the body's ``StatusCode``: ``200``/``204``
    are ``ok=True`` (``204`` is a successful empty result, not an error), any other code is
    ``ok=False`` with the upstream ``Message``. Never raises.
    """
    err = _valid_dates(from_date, to_date)
    if err:
        return ReportResult(ok=False, error=err)
    result = _middleware_post(
        session,
        "/middleware-go/report/contract",
        {
            "client_id": session.client_code,
            "from_date": from_date,
            "to_date": to_date,
        },
        with_from_header=True,
        client=client,
    )
    if not result.ok:
        return result
    body = result.data or {}
    if body.get("StatusCode") in (200, 204):
        return ReportResult(ok=True, data=body)
    return ReportResult(ok=False, error=body.get("Message") or "upstream error")


def get_tax_report(
    session: Session,
    fin_year: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Generate the tax-report PDF for ``fin_year`` and return its download URL.

    Contract: ``POST /api/middleware/GetTaxReportPDF`` with the client-version ``from:``
    header and body ``{ClientId: client_code, FinYear, RequestFor:2, FileFormat:1,
    SessionId}``. ``fin_year`` is a widget value in ``{"2024-2025","2025-2026","2026-2027"}``.
    On success the envelope's ``Response`` is a download URL string (carried in ``data``,
    never surfaced to the model). Never raises.
    """
    return _map_envelope(
        _middleware_post(
            session,
            "/api/middleware/GetTaxReportPDF",
            {
                "ClientId": session.client_code,
                "FinYear": fin_year,
                "RequestFor": 2,
                "FileFormat": 1,
                "SessionId": session.finx_session_id,
            },
            with_from_header=True,
            client=client,
        )
    )
