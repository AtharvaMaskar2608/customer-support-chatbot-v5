"""Tests for the five FinX middleware clients using a mocked httpx transport.

Each test pins the exact endpoint, headers (including the ``from:`` version header where
required), and request body per ``docs/finx_api_reports_documentation.md``, and asserts the
non-raising in-band contract: envelope ``Status != "Success"`` -> ``ok=False`` with the
``Reason``; Go ``StatusCode == 204`` -> ``ok=True`` empty; other Go codes -> ``ok=False``
with the ``Message``; a transport error/timeout -> ``ok=False`` without raising; and an
invalid date short-circuits to ``ok=False`` with **no** network request.
"""

import httpx
import pytest

from backend.config.settings import get_settings
from backend.contracts.models import Session
from backend.tools.finx import (
    _headers,
    get_contract_notes,
    get_detailed_pnl,
    get_global_pnl,
    get_ledger,
    get_tax_report,
)

_BASE = "https://mw.example.com"


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    """Provide the required settings env so ``get_settings()`` constructs cleanly."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FINX_MIDDLEWARE_BASE_URL", _BASE)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_SESSION = Session(
    client_code="X493657",
    user_id="u1",
    mobile_no="9920885615",
    session_token="jwt.abc.def",
    finx_session_id="SESSION_ABC",
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _envelope_handler(expected_url, expected_body, *, from_header, response_json):
    """Build a MockTransport handler asserting URL/headers/body and returning ``response_json``."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        assert str(request.url) == _BASE + expected_url
        assert request.headers["authorization"] == "SESSION_ABC"
        assert request.headers["origin"] == "https://finx.choiceindia.com"
        if from_header:
            assert request.headers["from"] == "Web_finx.choiceindia.com_V_4.6.0.4"
        else:
            assert "from" not in request.headers
        assert json.loads(request.content) == expected_body
        return httpx.Response(200, json=response_json)

    return handler


# --------------------------------------------------------------------------------------
# get_ledger
# --------------------------------------------------------------------------------------


def test_ledger_request_body_and_success():
    handler = _envelope_handler(
        "/api/middleware/GetLedgerDetails",
        {
            "LoginId": "JIFFY",
            "ClientId": "X493657",
            "Group": "MTF",
            "FromDate": "2026-04-01",
            "ToDate": "2026-07-15",
            "SessionId": "SESSION_ABC",
        },
        from_header=False,
        response_json={
            "Status": "Success",
            "Response": [{"voucher": "OPENING", "Debit": 0.0}],
            "Reason": "",
        },
    )
    with _client(handler) as client:
        result = get_ledger(_SESSION, "MTF", "2026-04-01", "2026-07-15", client=client)

    assert result.ok is True
    assert result.data["Response"] == [{"voucher": "OPENING", "Debit": 0.0}]


def test_ledger_in_band_failure_maps_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Status": "Fail", "Response": None, "Reason": "Data not found."}
        )

    with _client(handler) as client:
        result = get_ledger(_SESSION, "Group1", "2026-04-01", "2026-07-15", client=client)

    assert result.ok is False
    assert result.error == "Data not found."


def test_ledger_invalid_date_makes_no_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with _client(handler) as client:
        result = get_ledger(_SESSION, "Group1", "15-04-2026", "2026-07-15", client=client)

    assert result.ok is False
    assert "expected YYYY-MM-DD" in result.error
    assert calls == []


# --------------------------------------------------------------------------------------
# get_global_pnl
# --------------------------------------------------------------------------------------


def test_global_pnl_request_body_and_success():
    handler = _envelope_handler(
        "/api/middleware/GetGlobalPNLNew",
        {
            "UserId": "X493657",
            "ClientId": "X493657",
            "Group": "Cash",
            "FromDate": "2026-04-01",
            "ToDate": "2026-07-15",
            "With_Exp": 1,
            "SessionId": "SESSION_ABC",
        },
        from_header=False,
        response_json={"Status": "Success", "Response": [{"pnl": 100}], "Reason": ""},
    )
    with _client(handler) as client:
        result = get_global_pnl(_SESSION, "Cash", "2026-04-01", "2026-07-15", client=client)

    assert result.ok is True
    assert result.data["Response"] == [{"pnl": 100}]


def test_global_pnl_no_data_is_contained():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Status": "Fail", "Response": None, "Reason": "Data not found."}
        )

    with _client(handler) as client:
        result = get_global_pnl(_SESSION, "Derv", "2026-04-01", "2026-07-15", client=client)

    assert result.ok is False
    assert result.error == "Data not found."


# --------------------------------------------------------------------------------------
# get_detailed_pnl
# --------------------------------------------------------------------------------------


def test_detailed_pnl_uses_neuron_user_and_from_header():
    handler = _envelope_handler(
        "/api/middleware/GetDetailedPNL",
        {
            "UserId": "neuron",
            "ClientId": "X493657",
            "Group": "Group23",
            "FromDate": "2026-04-01",
            "ToDate": "2026-07-15",
            "SessionId": "SESSION_ABC",
        },
        from_header=True,
        response_json={"Status": "Success", "Response": [{"scrip": "X"}], "Reason": ""},
    )
    with _client(handler) as client:
        result = get_detailed_pnl(
            _SESSION, "Group23", "2026-04-01", "2026-07-15", client=client
        )

    assert result.ok is True


# --------------------------------------------------------------------------------------
# get_contract_notes (Go middleware)
# --------------------------------------------------------------------------------------


def test_contract_notes_snake_case_body_and_from_header():
    handler = _envelope_handler(
        "/middleware-go/report/contract",
        {"client_id": "X493657", "from_date": "2026-07-01", "to_date": "2026-07-08"},
        from_header=True,
        response_json={"StatusCode": 200, "Message": "ok", "Body": [{"note": "n1"}]},
    )
    with _client(handler) as client:
        result = get_contract_notes(_SESSION, "2026-07-01", "2026-07-08", client=client)

    assert result.ok is True
    assert result.data["Body"] == [{"note": "n1"}]


def test_contract_notes_204_is_empty_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "StatusCode": 204,
                "Message": "No valid contract notes found...",
                "Body": {},
            },
        )

    with _client(handler) as client:
        result = get_contract_notes(_SESSION, "2026-07-01", "2026-07-08", client=client)

    assert result.ok is True
    assert result.data["StatusCode"] == 204


def test_contract_notes_other_status_code_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"StatusCode": 500, "Message": "boom", "Body": {}}
        )

    with _client(handler) as client:
        result = get_contract_notes(_SESSION, "2026-07-01", "2026-07-08", client=client)

    assert result.ok is False
    assert result.error == "boom"


def test_contract_notes_timeout_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with _client(handler) as client:
        result = get_contract_notes(_SESSION, "2026-07-01", "2026-07-08", client=client)

    assert result.ok is False
    assert result.error is not None


# --------------------------------------------------------------------------------------
# get_tax_report
# --------------------------------------------------------------------------------------


def test_tax_report_body_and_url_in_data():
    url = "https://client-report.choiceindia.com/PDFReports/TaxReport_1_X493657.pdf"
    handler = _envelope_handler(
        "/api/middleware/GetTaxReportPDF",
        {
            "ClientId": "X493657",
            "FinYear": "2025-2026",
            "RequestFor": 2,
            "FileFormat": 1,
            "SessionId": "SESSION_ABC",
        },
        from_header=True,
        response_json={"Status": "Success", "Response": url, "Reason": ""},
    )
    with _client(handler) as client:
        result = get_tax_report(_SESSION, "2025-2026", client=client)

    assert result.ok is True
    assert result.data["Response"] == url


def test_tax_report_upstream_500_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _client(handler) as client:
        result = get_tax_report(_SESSION, "2025-2026", client=client)

    assert result.ok is False
    assert "500" in result.error


# --------------------------------------------------------------------------------------
# Headers
# --------------------------------------------------------------------------------------


def test_headers_shape_without_from():
    assert _headers(_SESSION) == {
        "authorization": "SESSION_ABC",
        "origin": "https://finx.choiceindia.com",
    }


def test_headers_shape_with_from():
    headers = _headers(_SESSION, with_from_header=True)
    assert headers["from"] == "Web_finx.choiceindia.com_V_4.6.0.4"
