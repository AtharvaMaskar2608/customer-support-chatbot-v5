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


def test_session_trims_inputs(app):
    response = _post_json(
        app,
        "/session",
        {
            "userId": "  u1  ",
            "mobileNo": " 9920885615 ",
            "sessionToken": "  jwt.abc.def  ",
            "clientCode": "  X130627 ",
        },
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert session_id

    stored = sessions.get_session(session_id)
    assert stored is not None
    assert stored.user_id == "u1"
    assert stored.mobile_no == "9920885615"
    assert stored.session_token == "jwt.abc.def"
    assert stored.client_code == "X130627"


def test_session_defaults_optional_client_code(app):
    response = _post_json(
        app,
        "/session",
        {"userId": "u1", "mobileNo": "9920885615", "sessionToken": "jwt.x"},
    )
    session_id = response.json()["session_id"]
    assert sessions.get_session(session_id).client_code == ""


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

    session_id = _post_json(
        app, "/session", {"userId": "u1", "mobileNo": "9", "sessionToken": "jwt.x"}
    ).json()["session_id"]

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

    session_id = _post_json(
        app, "/session", {"userId": "u1", "mobileNo": "9", "sessionToken": "jwt.x"}
    ).json()["session_id"]

    frames = _post_sse(
        app,
        "/chat",
        {"session_id": session_id, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert frames[-1][0] == "error"


# --------------------------------------------------------------------------------------
# POST /report
# --------------------------------------------------------------------------------------


def test_report_runs_tool_and_streams_summary(app, monkeypatch):
    # The resume turn streams a factual summary from the (mocked) report result.
    script = [
        {
            "events": [_delta("Your contract note "), _delta("has 3 trades.")],
            "final": _message([_text_block("Your contract note has 3 trades.")]),
        },
    ]
    _patch_stream(monkeypatch, script)

    captured: dict[str, Any] = {}

    def _fake_contract_note(session, mobile_no, contract_date, **kwargs):
        captured["mobile_no"] = mobile_no
        captured["contract_date"] = contract_date
        return ReportResult(ok=True, data={"trades": 3})

    monkeypatch.setattr(routes, "contract_note", _fake_contract_note)

    session_id = _post_json(
        app, "/session", {"userId": "u1", "mobileNo": "9", "sessionToken": "jwt.x"}
    ).json()["session_id"]

    paused = [
        {"role": "user", "content": "my contract note"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_cn", "name": "contract_note", "input": {}}
            ],
        },
    ]
    frames = _post_sse(
        app,
        "/report",
        {
            "session_id": session_id,
            "report_type": "contract_note",
            "params": {"mobile_no": "9920885615", "contract_date": "01-07-2024"},
            "tool_use_id": "tu_cn",
            "messages": paused,
        },
    )
    events = [event for event, _ in frames]

    assert captured == {"mobile_no": "9920885615", "contract_date": "01-07-2024"}
    assert events[-1] == "done"
    tokens = "".join(
        __import__("json").loads(data)["text"]
        for event, data in frames
        if event == "token"
    )
    assert tokens == "Your contract note has 3 trades."


def test_report_missing_param_is_400(app):
    session_id = _post_json(
        app, "/session", {"userId": "u1", "mobileNo": "9", "sessionToken": "jwt.x"}
    ).json()["session_id"]

    response = _post_json(
        app,
        "/report",
        {
            "session_id": session_id,
            "report_type": "cml",
            "params": {},  # missing client_id
            "tool_use_id": "tu_cml",
            "messages": [],
        },
    )
    assert response.status_code == 400
