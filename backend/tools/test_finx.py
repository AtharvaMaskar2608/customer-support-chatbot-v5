"""Tests for the FinX report clients using a mocked httpx transport.

Assert the non-raising contract: success maps to ``ok=True``; an upstream 500 or a
timeout maps to ``ok=False`` without raising; and a bad ``contract_date`` short-circuits
to ``ok=False`` with **no** network request issued.
"""

import httpx
import pytest

from backend.config.settings import get_settings
from backend.contracts.models import Session
from backend.tools.finx import _auth_headers, cml_report, contract_note


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    """Provide the required settings env so ``get_settings()`` constructs cleanly."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("FINX_CML_BASE_URL", "https://cml.example.com")
    monkeypatch.setenv("FINX_CONTRACT_NOTE_BASE_URL", "https://cn.example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_SESSION = Session(
    client_code="X130627", user_id="u1", mobile_no="9920885615", session_token="jwt.abc.def"
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_cml_report_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://cml.example.com/mis/reports/generate"
        assert request.headers["Authorization"] == "jwt.abc.def"
        assert request.headers["authType"] == "jwt"
        assert request.headers["source"] == "FINX_WEB"
        return httpx.Response(200, json={"report": "cml-data"})

    with _client(handler) as client:
        result = cml_report(_SESSION, "X130627", client=client)

    assert result.ok is True
    assert result.data == {"report": "cml-data"}
    assert result.error is None


def test_contract_note_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://cn.example.com/mis/v2/contract-note/generate"
        return httpx.Response(200, json={"note": "ok"})

    with _client(handler) as client:
        result = contract_note(_SESSION, "9920885615", "01-07-2024", client=client)

    assert result.ok is True
    assert result.data == {"note": "ok"}


def test_cml_report_upstream_500_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _client(handler) as client:
        result = cml_report(_SESSION, "X130627", client=client)

    assert result.ok is False
    assert result.data is None
    assert "500" in result.error


def test_contract_note_timeout_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with _client(handler) as client:
        result = contract_note(_SESSION, "9920885615", "01-07-2024", client=client)

    assert result.ok is False
    assert result.error is not None


def test_contract_note_bad_date_makes_no_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    with _client(handler) as client:
        result = contract_note(_SESSION, "9920885615", "2024-07-01", client=client)

    assert result.ok is False
    assert "DD-MM-YYYY" in result.error
    assert calls == []


def test_auth_headers_shape():
    assert _auth_headers(_SESSION) == {
        "Authorization": "jwt.abc.def",
        "authType": "jwt",
        "source": "FINX_WEB",
    }
