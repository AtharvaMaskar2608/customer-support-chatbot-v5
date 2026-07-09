"""Unit tests for the agentic loop with the Anthropic client and RAG dispatch mocked.

The Anthropic Messages API and ``rag_search`` are faked so these run offline and
deterministically. They cover the spec scenarios: a grounded+cited FAQ answer, the report
intent pause and its resume summary, the conversation cap offering a ticket, cost/latency
accounting, and the guardrail/category content of the system prompt.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from backend.agent import cost, loop, prompt
from backend.agent.loop import (
    agent_reply,
    agent_reply_stream,
    clarifying_question_count,
    conversation_message_count,
)
from backend.agent.tools import ASK_CLARIFYING_QUESTION, available_tools
from backend.config.settings import get_settings
from backend.contracts.models import Citation, RagChunk, RagResult, Session


# --------------------------------------------------------------------------------------
# Fixtures & fakes
# --------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    """Required settings env so ``get_settings()`` constructs; caches cleared around test."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_SESSION = Session(
    client_code="X130627", user_id="u1", mobile_no="9920885615", session_token="jwt.x"
)

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
        self.tools_seen: list[Any] = []  # the `tools` kwarg passed on each call

    def stream(self, **kwargs: Any) -> _FakeStream:
        self.tools_seen.append(kwargs.get("tools"))
        turn = self._script[self._i]
        self._i += 1
        return _FakeStream(turn["events"], turn["final"])


class _FakeAsyncClient:
    def __init__(self, script: list[dict[str, Any]]):
        self.messages = _FakeAsyncMessages(script)


class _FakeSyncMessages:
    def __init__(self, script: list[Any]):
        self._script = script
        self._i = 0
        self.tools_seen: list[Any] = []  # the `tools` kwarg passed on each call

    def create(self, **kwargs: Any):
        self.tools_seen.append(kwargs.get("tools"))
        message = self._script[self._i]
        self._i += 1
        return message


class _FakeSyncClient:
    def __init__(self, script: list[Any]):
        self.messages = _FakeSyncMessages(script)


def _patch_stream(monkeypatch, script: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(loop, "_client", lambda: _FakeAsyncClient(script))
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(loop, "dispatch_tool", lambda name, inp, sess: _RAG_RESULT)


def _collect(agen) -> list[Any]:
    async def _run() -> list[Any]:
        return [event async for event in agen]

    return asyncio.run(_run())


# --------------------------------------------------------------------------------------
# FAQ answer is grounded and cited (streaming)
# --------------------------------------------------------------------------------------


def test_faq_answer_streams_tokens_citations_and_usage(monkeypatch):
    script = [
        {"events": [], "final": _message([_tool_block("tu_1", "rag_search", {"query": "q"})])},
        {
            "events": [_delta("Go to "), _delta("Profile > Contact.")],
            "final": _message([_text_block("Go to Profile > Contact.")]),
        },
    ]
    _patch_stream(monkeypatch, script)

    messages = [{"role": "user", "content": "How do I update my mobile number?"}]
    events = _collect(agent_reply_stream(_SESSION, messages))
    types = [e.type for e in events]

    assert "status" in types
    assert "token" in types
    # Citations frame appears once RAG was used, before usage/done.
    assert types.index("citations") < types.index("usage") < types.index("done")

    tokens = "".join(e.text for e in events if e.type == "token")
    assert tokens == "Go to Profile > Contact."

    citations_event = next(e for e in events if e.type == "citations")
    assert citations_event.citations[0].topic == "Account"

    usage_event = next(e for e in events if e.type == "usage")
    assert usage_event.usage.cost_inr > 0
    assert usage_event.usage.cumulative_cost_inr > 0
    # Two model calls' tokens are aggregated into one usage frame.
    assert usage_event.usage.input_tokens == 20
    assert usage_event.usage.output_tokens == 40


def test_faq_answer_non_streaming_has_citations_and_usage(monkeypatch):
    script = [
        _message([_tool_block("tu_1", "rag_search", {"query": "q"})]),
        _message([_text_block("Go to Profile > Contact.")]),
    ]
    monkeypatch.setattr(loop, "_sync_client", lambda: _FakeSyncClient(script))
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(loop, "dispatch_tool", lambda name, inp, sess: _RAG_RESULT)

    reply = agent_reply(_SESSION, [{"role": "user", "content": "update mobile?"}])

    assert reply.text == "Go to Profile > Contact."
    assert reply.citations and reply.citations[0].section == "Profile"
    assert reply.usage is not None
    assert reply.usage.cost_inr > 0
    assert reply.usage.latency_ms >= 0


# --------------------------------------------------------------------------------------
# Report intent is terminal (CHO-61): report_request -> usage -> done
# --------------------------------------------------------------------------------------


def test_report_tool_emits_report_request_then_usage_then_done(monkeypatch):
    script = [
        {"events": [], "final": _message([_tool_block("tu_led", "ledger", {})])},
    ]
    _patch_stream(monkeypatch, script)

    events = _collect(
        agent_reply_stream(_SESSION, [{"role": "user", "content": "my ledger"}])
    )
    types = [e.type for e in events]

    report = next(e for e in events if e.type == "report_request")
    assert report.report_type == "ledger"
    assert report.tool_use_id == "tu_led"
    # The widget spec carries the group card step (Normal/MTF) then the date-range step.
    assert report.steps[0].kind == "cards"
    assert report.steps[0].param == "group"
    assert {o.value for o in report.steps[0].options} == {"Group1", "MTF"}
    assert report.steps[1].kind == "date_range"
    # The turn terminates: report_request is followed by usage then done (CHO-61).
    assert types.index("report_request") < types.index("usage") < types.index("done")
    assert types[-1] == "done"
    done = next(e for e in events if e.type == "done")
    assert done.stop_reason == "report_request"


def test_report_tool_records_intent_in_tools_called_non_streaming(monkeypatch):
    # The non-streaming eval path feeds a neutral tool result and continues to a final
    # answer, recording the report tool name in tools_called for intent-routing evals.
    script = [
        _message([_tool_block("tu_pnl", "global_pnl", {})]),
        _message([_text_block("Use the report widget to view your P&L.")]),
    ]
    monkeypatch.setattr(loop, "_sync_client", lambda: _FakeSyncClient(script))
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")

    reply = agent_reply(_SESSION, [{"role": "user", "content": "my p&l"}])

    assert reply.tools_called == ("global_pnl",)
    assert reply.citations == ()


def test_rag_intent_recorded_in_tools_called(monkeypatch):
    script = [
        _message([_tool_block("tu_1", "rag_search", {"query": "q"})]),
        _message([_text_block("Go to Profile > Contact.")]),
    ]
    monkeypatch.setattr(loop, "_sync_client", lambda: _FakeSyncClient(script))
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")
    monkeypatch.setattr(loop, "dispatch_tool", lambda name, inp, sess: _RAG_RESULT)

    reply = agent_reply(_SESSION, [{"role": "user", "content": "update mobile?"}])

    assert reply.tools_called == ("rag_search",)


# --------------------------------------------------------------------------------------
# Conversation caps
# --------------------------------------------------------------------------------------


def test_message_cap_offers_ticket_without_model_call(monkeypatch):
    def _boom():
        raise AssertionError("model must not be called at the cap")

    monkeypatch.setattr(loop, "_client", _boom)
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")

    # 10 conversational messages already exchanged.
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(10)
    ]
    events = _collect(agent_reply_stream(_SESSION, messages))

    token = next(e for e in events if e.type == "token")
    assert "support ticket" in token.text.lower()
    done = next(e for e in events if e.type == "done")
    assert done.stop_reason == "cap_reached"


def test_conversation_message_count_excludes_tool_plumbing():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "rag_search", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "{}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "answer"}]},
    ]
    # Only the real user turn and the final assistant text count.
    assert conversation_message_count(messages) == 2


# --------------------------------------------------------------------------------------
# Cost accounting
# --------------------------------------------------------------------------------------


def test_message_cost_and_cumulative(monkeypatch):
    monkeypatch.setenv("USD_INR_RATE", "80")
    # Sonnet tier: $3/MTok in, $15/MTok out. 1M in + 1M out => (3 + 15) * 80 = 1440 INR.
    c = cost.message_cost_inr("claude-sonnet-4-5", 1_000_000, 1_000_000)
    assert c == pytest.approx(1440.0)

    usage = cost.build_usage("claude-sonnet-4-5", 1_000_000, 0, 12.5, prior_cost_inr=100.0)
    assert usage.cost_inr == pytest.approx(240.0)  # 3 * 80
    assert usage.cumulative_cost_inr == pytest.approx(340.0)
    assert usage.latency_ms == 12.5


def test_unknown_model_falls_back_to_sonnet_tier(monkeypatch):
    monkeypatch.setenv("USD_INR_RATE", "80")
    assert cost.message_cost_inr("some-future-model", 1_000_000, 0) == pytest.approx(240.0)


# --------------------------------------------------------------------------------------
# System prompt: guardrails + tools + in-scope categories
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# Clarifying-question cap (code-enforced) + session identity
# --------------------------------------------------------------------------------------


def _clarify_tool_use(id: str = "cq") -> dict[str, Any]:
    return {"type": "tool_use", "id": id, "name": ASK_CLARIFYING_QUESTION, "input": {}}


def _two_clarifying_asked() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "help"},
        {"role": "assistant", "content": [_clarify_tool_use("c1")]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ask"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Which product?"}]},
        {"role": "user", "content": "the app"},
        {"role": "assistant", "content": [_clarify_tool_use("c2")]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c2", "content": "ask"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Which screen?"}]},
    ]


def test_clarifying_question_count_and_gate():
    assert clarifying_question_count([{"role": "user", "content": "hi"}]) == 0
    assert clarifying_question_count(_two_clarifying_asked()) == 2

    allowed = {t["name"] for t in available_tools(True)}
    capped = {t["name"] for t in available_tools(False)}
    assert ASK_CLARIFYING_QUESTION in allowed
    assert ASK_CLARIFYING_QUESTION not in capped  # withheld at the cap
    assert "rag_search" in capped  # other tools still offered


def test_clarifying_question_streams_as_text(monkeypatch):
    # Turn 1: model calls ask_clarifying_question. Turn 2: it poses the question as text.
    script = [
        {"events": [], "final": _message([_tool_block("cq", ASK_CLARIFYING_QUESTION, {})])},
        {
            "events": [_delta("What is your "), _delta("client code?")],
            "final": _message([_text_block("What is your client code?")]),
        },
    ]
    client = _FakeAsyncClient(script)
    monkeypatch.setattr(loop, "_client", lambda: client)
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")

    events = _collect(agent_reply_stream(_SESSION, [{"role": "user", "content": "help me"}]))
    tokens = "".join(e.text for e in events if e.type == "token")
    assert tokens == "What is your client code?"
    assert events[-1].type == "done"
    # The clarifying tool was offered on the first turn (under the cap).
    assert any(t["name"] == ASK_CLARIFYING_QUESTION for t in client.messages.tools_seen[0])


def test_clarifying_cap_withholds_tool_after_two(monkeypatch):
    history = _two_clarifying_asked() + [{"role": "user", "content": "the reports screen"}]
    script = [
        {"events": [_delta("Here's how.")], "final": _message([_text_block("Here's how.")])},
    ]
    client = _FakeAsyncClient(script)
    monkeypatch.setattr(loop, "_client", lambda: client)
    monkeypatch.setattr(loop, "build_system_prompt", lambda: "SYSTEM")

    _collect(agent_reply_stream(_SESSION, history))
    # The 3rd clarifying question is impossible: the tool was not offered to the model.
    offered = client.messages.tools_seen[0]
    assert all(t["name"] != ASK_CLARIFYING_QUESTION for t in offered)


def test_session_has_stable_unique_id():
    s1 = Session(client_code="X", user_id="u", mobile_no="9", session_token="jwt")
    s2 = Session(client_code="X", user_id="u", mobile_no="9", session_token="jwt")
    assert s1.session_id  # populated
    assert s1.session_id == s1.session_id  # stable for the object
    assert s1.session_id != s2.session_id  # unique per construction
    # An explicit id is preserved (the API layer supplies its own store key).
    assert Session(
        client_code="X", user_id="u", mobile_no="9", session_token="jwt", session_id="sess-1"
    ).session_id == "sess-1"


def test_system_prompt_has_tools_categories_and_guardrails(monkeypatch):
    monkeypatch.setattr(
        prompt,
        "fetch",
        lambda sql, params=(): [
            {"topic": "Account", "section": "Profile"},
            {"topic": "Reports", "section": "CML"},
        ],
    )
    prompt._kb_categories.cache_clear()

    text = prompt.build_system_prompt()

    # Tools listed: rag_search + the five report tools.
    assert "rag_search" in text
    for tool in ("ledger", "global_pnl", "detailed_pnl", "contract_notes", "tax_report"):
        assert tool in text
    # The prompt states report results render in the UI (not via the assistant).
    assert "renders directly in the UI" in text
    # In-scope categories derived from qa_chunks.
    assert "Account" in text and "Profile" in text
    assert "Reports" in text and "CML" in text
    # Guardrails: SEBI (no advice) + scope (Choice FinX only).
    assert "SEBI" in text
    assert "advice" in text.lower()
    assert "Choice FinX" in text
    # Caps policy present.
    assert "clarifying question" in text.lower()
    prompt._kb_categories.cache_clear()
