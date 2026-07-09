"""API tests over an httpx ASGI client, with the Anthropic loop and FinX call mocked.

These exercise the HTTP surface end to end without network: ``POST /session`` trims its
inputs, ``POST /chat`` yields an SSE sequence that ends in ``done`` (or ``error``), and
``POST /report`` runs the report tool and streams a resumed summary to ``done``. The
Anthropic client is faked exactly as in ``backend.agent.test_agent`` (so no model is
called); the async streams are driven with ``asyncio.run`` since the project configures no
pytest-asyncio mode.
"""

from __future__ import annotations

# Required settings must exist before importing ``backend.main`` (it builds the app, which
# reads settings, at import time). Per-test overrides go through the autouse fixture below.
import os

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from backend.agent import loop
from backend.api import routes, sessions
from backend.config.settings import get_settings
from backend.contracts.models import Citation, RagChunk, RagResult, ReportResult
from backend.main import create_app


# --------------------------------------------------------------------------------------
# Fixtures & fakes
# --------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    """Required settings env; caches cleared and the session store reset around each test."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    get_settings.cache_clear()
    sessions.clear_sessions()
    yield
    get_settings.cache_clear()
    sessions.clear_sessions()


@pytest.fixture
def app():
    """A freshly built app (picks up the per-test settings env)."""
    return create_app()


_RAG_RESULT = RagResult(
    query="update mobile number",
    chunks=(
        RagChunk(
            id=1,
            chunk="To update your mobile number, go to Profile > Contact.",
            score=0.9,
            citation=Citation(topic="Account", section="Profile", question="update mobile"),
        ),
    ),
)


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_block(id: str, name: str, input: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input or {})


def _message(content: list[Any], input_tokens: int = 10, output_tokens: int = 20):
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="text_delta", text=text),
    )


class _FakeStream:
    """Async context manager mimicking ``client.messages.stream(...)``."""

    def __init__(self, events: list[Any], final: Any):
        self._events = events
        self._final = final

    async def __aenter__(self) -> "_FakeStream":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def __aiter__(self):
        async def _gen():
            for event in self._events:
                yield event

        return _gen()

    async def get_final_message(self):
        return self._final


class _FakeAsyncMessages:
    def __init__(self, script: list[dict[str, Any]]):
        self._script = script
        self._i = 0

    def stream(self, **kwargs: Any) -> _FakeStream:
        turn = self._script[self._i]
        self._i += 1
        return _FakeStream(turn["events"], turn["final"])


class _FakeAsyncClient:
    def __init__(self, script: list[dict[str, Any]]):
        self.messages = _FakeAsyncMessages(script)


def _patch_stream(monkeypatch, script: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(loop, "_client", lambda: _FakeAsyncClient(script))
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(loop, "dispatch_tool", lambda name, inp, sess: _RAG_RESULT)


def _sse_frames(body: str) -> list[tuple[str, str]]:
    """Parse an SSE response body into ``[(event, data), ...]`` frames.

    Each frame is a block of ``event:``/``data:`` lines separated by a blank line; comment
    lines (``:`` pings) are ignored.
    """
    frames: list[tuple[str, str]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith(":") or not line.strip():
                continue
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            frames.append((event, "\n".join(data_lines)))
    return frames


def _post_sse(app, path: str, payload: dict) -> list[tuple[str, str]]:
    """POST ``payload`` to ``path`` and return the parsed SSE frames (drives ASGI async)."""

    async def _run() -> list[tuple[str, str]]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            async with client.stream("POST", path, json=payload) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                body = "".join([chunk async for chunk in response.aiter_text()])
        return _sse_frames(body)

    return asyncio.run(_run())


def _post_json(app, path: str, payload: dict) -> httpx.Response:
    """POST ``payload`` to ``path`` and return the (non-streaming) JSON response."""

    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(path, json=payload)

    return asyncio.run(_run())


# --------------------------------------------------------------------------------------
# POST /session
# --------------------------------------------------------------------------------------


def _login_body(**overrides) -> dict:
    """A complete, valid login payload; override individual fields per test."""
    body = {
        "userId": "u1",
        "mobileNo": "9920885615",
        "sessionToken": "jwt.abc.def",
        "finxSessionId": "SESSION_ABC",
        "clientCode": "X130627",
    }
    body.update(overrides)
    return body


def _new_session(app) -> str:
    """Create a valid session and return its id."""
    return _post_json(app, "/session", _login_body()).json()["session_id"]


def test_session_trims_inputs(app):
    response = _post_json(
        app,
        "/session",
        _login_body(
            userId="  u1  ",
            mobileNo=" 9920885615 ",
            sessionToken="  jwt.abc.def  ",
            finxSessionId="  SESSION_ABC  ",
            clientCode="  X130627 ",
        ),
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert session_id

    stored = sessions.get_session(session_id)
    assert stored is not None
    assert stored.user_id == "u1"
    assert stored.mobile_no == "9920885615"
    assert stored.session_token == "jwt.abc.def"
    assert stored.finx_session_id == "SESSION_ABC"
    assert stored.client_code == "X130627"


def test_session_requires_finx_session_id(app):
    response = _post_json(app, "/session", _login_body(finxSessionId="   "))
    assert response.status_code == 422


def test_session_requires_client_code(app):
    response = _post_json(app, "/session", _login_body(clientCode=""))
    assert response.status_code == 422


def test_session_missing_finx_session_id_field_is_422(app):
    body = _login_body()
    del body["finxSessionId"]
    response = _post_json(app, "/session", body)
    assert response.status_code == 422


# --------------------------------------------------------------------------------------
# POST /chat
# --------------------------------------------------------------------------------------


def test_chat_streams_to_done(app, monkeypatch):
    script = [
        {"events": [], "final": _message([_tool_block("tu_1", "rag_search", {"query": "q"})])},
        {
            "events": [_delta("Go to "), _delta("Profile > Contact.")],
            "final": _message([_text_block("Go to Profile > Contact.")]),
        },
    ]
    _patch_stream(monkeypatch, script)

    session_id = _new_session(app)

    frames = _post_sse(
        app,
        "/chat",
        {
            "session_id": session_id,
            "messages": [{"role": "user", "content": "How do I update my mobile number?"}],
        },
    )
    events = [event for event, _ in frames]

    assert "status" in events
    assert "token" in events
    assert events.index("citations") < events.index("usage") < events.index("done")
    assert events[-1] == "done"

    tokens = "".join(
        __import__("json").loads(data)["text"]
        for event, data in frames
        if event == "token"
    )
    assert tokens == "Go to Profile > Contact."


def test_chat_unknown_session_is_404(app):
    response = _post_json(
        app, "/chat", {"session_id": "nope", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 404


def test_chat_failure_yields_error_frame(app, monkeypatch):
    # A stream that raises mid-turn must end with a terminal ``error`` frame.
    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(routes, "agent_reply_stream", _boom)

    session_id = _new_session(app)

    frames = _post_sse(
        app,
        "/chat",
        {"session_id": session_id, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert frames[-1][0] == "error"


# --------------------------------------------------------------------------------------
# POST /report — plain JSON render payload; no SSE, no Anthropic call
# --------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_anthropic(monkeypatch):
    """Fail loudly if any /report path constructs an Anthropic client (design D5)."""

    def _boom(*args, **kwargs):
        raise AssertionError("/report must not call the Anthropic API")

    monkeypatch.setattr(loop, "_client", _boom)
    monkeypatch.setattr(loop, "_sync_client", _boom)


def test_report_ledger_returns_table_payload(app, monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_get_ledger(session, group, from_date, to_date, **kwargs):
        captured.update(group=group, from_date=from_date, to_date=to_date)
        return ReportResult(
            ok=True,
            data={
                "Status": "Success",
                "Response": [
                    {"trd_Date": "2026-04-01T00:00:00", "voucher": "OPENING", "Debit": 0.0}
                ],
                "Reason": "",
            },
        )

    monkeypatch.setattr(routes, "get_ledger", _fake_get_ledger)

    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "ledger",
            "params": {
                "group": "MTF",
                "from_date": "2026-04-01",
                "to_date": "2026-07-15",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "table"
    assert captured == {"group": "MTF", "from_date": "2026-04-01", "to_date": "2026-07-15"}
    # Fixed ledger column map.
    labels = {c["key"]: c["label"] for c in body["columns"]}
    assert labels["trd_Date"] == "Date" and labels["Narration"] == "Description"
    assert body["rows"][0]["voucher"] == "OPENING"


def test_report_tax_returns_link_payload(app, monkeypatch):
    url = "https://client-report.choiceindia.com/PDFReports/TaxReport_1_X130627.pdf"
    monkeypatch.setattr(
        routes,
        "get_tax_report",
        lambda session, fin_year, **kwargs: ReportResult(
            ok=True, data={"Status": "Success", "Response": url, "Reason": ""}
        ),
    )

    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "tax_report",
            "params": {"fin_year": "2025-2026"},
        },
    )
    body = response.json()
    assert body["kind"] == "link"
    assert body["url"] == url


def test_report_no_data_returns_empty_payload(app, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_global_pnl",
        lambda session, group, from_date, to_date, **kwargs: ReportResult(
            ok=False, error="Data not found."
        ),
    )

    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "global_pnl",
            "params": {"group": "Cash", "from_date": "2026-04-01", "to_date": "2026-07-15"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "empty"
    assert body["message"] == "Data not found."


def test_report_upstream_error_returns_error_payload(app, monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_ledger",
        lambda *a, **k: ReportResult(ok=False, error="upstream 500"),
    )

    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "ledger",
            "params": {"group": "Group1", "from_date": "2026-04-01", "to_date": "2026-07-15"},
        },
    )
    body = response.json()
    assert body["kind"] == "error"
    assert body["message"] == "upstream 500"


def test_report_unknown_param_is_422_and_no_finx_call(app, monkeypatch):
    calls: list[Any] = []
    monkeypatch.setattr(
        routes, "get_ledger", lambda *a, **k: calls.append(a) or ReportResult(ok=True)
    )

    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "ledger",
            "params": {
                "group": "Group1",
                "from_date": "2026-04-01",
                "to_date": "2026-07-15",
                "client_id": "X130627",  # not a registry step param
            },
        },
    )
    assert response.status_code == 422
    assert calls == []


def test_report_missing_param_is_422(app):
    response = _post_json(
        app,
        "/report",
        {
            "session_id": _new_session(app),
            "report_type": "ledger",
            "params": {"group": "Group1"},  # missing from_date/to_date
        },
    )
    assert response.status_code == 422


def test_report_unknown_session_is_404(app):
    response = _post_json(
        app,
        "/report",
        {
            "session_id": "nope",
            "report_type": "tax_report",
            "params": {"fin_year": "2025-2026"},
        },
    )
    assert response.status_code == 404
