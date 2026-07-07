"""Read-only FinX MIS report clients (CML report + Contract Note).

Both tools are thin authenticated ``httpx`` POST calls that take structured params
originating from the frontend widget (never the model) and return a
:class:`ReportResult`. They **never raise**: every failure — network error, timeout,
or non-2xx response — is mapped to ``ReportResult(ok=False, error=...)`` so an upstream
outage can never crash the agent loop.

The two endpoints live on **different hosts** (``FINX_CML_BASE_URL`` for CML,
``FINX_CONTRACT_NOTE_BASE_URL`` for the Contract Note), configured as separate settings.
"""

import re

import httpx

from backend.config.settings import get_settings
from backend.contracts.models import ReportResult, Session

# contractDate is DD-MM-YYYY; validated server-side even though the widget guarantees it.
_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

# Bounded so a hung upstream surfaces as ok=False rather than stalling the agent turn.
_TIMEOUT = httpx.Timeout(30.0)


def _auth_headers(session: Session) -> dict[str, str]:
    """Shared auth header block sent on every FinX call.

    Contract: ``{Authorization: <session JWT>, authType: jwt, source: FINX_WEB}``.
    The JWT is the per-session token entered on the login form; it is never hardcoded.
    """
    return {
        "Authorization": session.session_token,
        "authType": "jwt",
        "source": "FINX_WEB",
    }


def _post(
    base_url: str,
    path: str,
    *,
    session: Session,
    json: dict,
    client: httpx.Client | None = None,
) -> ReportResult:
    """POST ``json`` to ``base_url + path`` and coerce any outcome to a ReportResult.

    Contract: on a 2xx JSON response returns ``ReportResult(ok=True, data=<parsed>)``;
    on any non-2xx, network error, or timeout returns ``ReportResult(ok=False, error=...)``
    without ever raising. A caller-supplied ``client`` (e.g. one wrapping a mock
    transport) is used as-is; otherwise a short-lived client is opened and closed here.
    """
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=_TIMEOUT)
    try:
        response = client.post(base_url + path, json=json, headers=_auth_headers(session))
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


def cml_report(
    session: Session, client_id: str, *, client: httpx.Client | None = None
) -> ReportResult:
    """Generate the CML report for ``client_id``.

    Contract: ``POST {FINX_CML_BASE_URL}/mis/reports/generate`` with body
    ``{"reportType": "cml", "searchBy": "client-id", "searchValue": client_id}`` and the
    shared auth headers. ``client_id`` originates from the frontend widget, not the model.
    Returns ``ReportResult(ok=True, data=...)`` on success and never raises.
    """
    settings = get_settings()
    return _post(
        settings.finx_cml_base_url,
        "/mis/reports/generate",
        session=session,
        json={"reportType": "cml", "searchBy": "client-id", "searchValue": client_id},
        client=client,
    )


def contract_note(
    session: Session,
    mobile_no: str,
    contract_date: str,
    *,
    client: httpx.Client | None = None,
) -> ReportResult:
    """Generate the Contract Note for ``mobile_no`` on ``contract_date`` (DD-MM-YYYY).

    Contract: validates ``contract_date`` against ``DD-MM-YYYY`` first — an invalid date
    returns ``ReportResult(ok=False, error=...)`` **without a network call**. Otherwise
    ``POST {FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate`` with body
    ``{"mobileNo": mobile_no, "contractDate": contract_date}`` and the shared auth headers.
    Both params originate from the frontend widget, not the model. Never raises.
    """
    if not _DATE_RE.match(contract_date):
        return ReportResult(ok=False, error="invalid contract_date; expected DD-MM-YYYY")

    settings = get_settings()
    return _post(
        settings.finx_contract_note_base_url,
        "/mis/v2/contract-note/generate",
        session=session,
        json={"mobileNo": mobile_no, "contractDate": contract_date},
        client=client,
    )
