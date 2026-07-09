"""The Anthropic tool-use loop: call model -> run tools -> feed results -> repeat.

One loop serves two callers: :func:`agent_reply` (non-streaming, for evals) and
:func:`agent_reply_stream` (streaming ``SSEEvent``s, for the API). Both register the same
tools (:data:`~backend.agent.tools.TOOLS`), use the same system prompt, disable thinking,
and loop until the model returns a final answer with no tool calls.

Report tools are intent-only: when the model calls one, the stream emits a terminal
``report_request`` frame carrying the tool's widget spec and the pending Anthropic
``tool_use_id`` (for trace correlation only), then ``usage`` and ``done`` — the turn ends.
The frontend collects the parameters and runs the report via ``POST /report``, entirely
outside the model; there is no resume. RAG-backed answers carry the citations of the last
``rag_search``.

Guardrails live in the system prompt (``backend.agent.prompt``). Both caps are enforced in
code: total messages are hard-capped (offering a support ticket at the cap), and clarifying
questions are a structural ``ask_clarifying_question`` tool that is counted from history and
withheld from the model once 2 have been asked, so a 3rd cannot be asked. The turn runs
inside a root ``agent`` trace span tagged with the session's thread/user id.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from anthropic import Anthropic, AsyncAnthropic

from backend.agent.cost import build_usage
from backend.agent.prompt import (
    MAX_CLARIFYING_QUESTIONS,
    MAX_MESSAGES,
    build_system_prompt,
)
from backend.agent.tools import (
    ASK_CLARIFYING_QUESTION,
    available_tools,
    dispatch_tool,
    is_clarifying_tool,
    is_report_tool,
    report_widget_spec,
)
from backend.config.settings import get_settings
from backend.contracts.events import (
    CitationsEvent,
    DoneEvent,
    ErrorEvent,
    ReportRequestEvent,
    SSEEvent,
    StatusEvent,
    TokenEvent,
    UsageEvent,
)
from backend.contracts.models import AgentReply, Citation, RagResult, Session
from backend.tracing.interface import get_tracer

# Upper bound on a single completion. Answers and report summaries are short; this bounds
# cost and latency without truncating realistic replies.
_MAX_TOKENS = 1024

# Offered verbatim when the conversation hits the hard message cap without resolution.
_TICKET_OFFER = (
    "We've gone back and forth several times without fully resolving this. Would you like "
    "me to raise a support ticket so a Choice FinX specialist can follow up with you?"
)

_STATUS_LOOKUP = "Looking up the knowledge base…"
_STATUS_GENERATING = "Generating the answer…"

# Fed back as the tool result when the model calls ask_clarifying_question: it turns the
# intent-only tool call into the model asking its one question as plain text on the next
# iteration, which ends the turn (awaiting the user) with clean text history.
_CLARIFY_INSTRUCTION = (
    "Ask the user this single clarifying question now, as your reply, then stop and wait for "
    "their answer. Ask only for the missing detail you need, and do not call any tools."
)


# --------------------------------------------------------------------------------------
# Message helpers
# --------------------------------------------------------------------------------------


def _serialize_content(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert Anthropic response content blocks back into message-param dicts.

    Only the block kinds the loop produces are represented (``text`` and ``tool_use``); the
    result is appended as the assistant turn so the next model call sees the full history.
    """
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.type == "text":
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return out


def _rag_tool_result(result: RagResult) -> str:
    """Serialize a :class:`RagResult` as the JSON string fed back as the tool result.

    Includes each chunk's id, text, score, and citation metadata so the model can both
    answer from and cite the retrieved passages.
    """
    return json.dumps(
        {
            "query": result.query,
            "chunks": [
                {
                    "id": chunk.id,
                    "text": chunk.chunk,
                    "score": chunk.score,
                    "topic": chunk.citation.topic,
                    "section": chunk.citation.section,
                    "question": chunk.citation.question,
                }
                for chunk in result.chunks
            ],
        }
    )


def _is_plumbing(message: dict[str, Any]) -> bool:
    """Return whether a message is pure tool plumbing (only tool_use/tool_result blocks).

    Such messages carry no conversational turn, so they are excluded from the cap count.
    """
    content = message.get("content")
    if isinstance(content, list) and content:
        types = {b.get("type") for b in content if isinstance(b, dict)}
        return bool(types) and types <= {"tool_use", "tool_result"}
    return False


def conversation_message_count(messages: list[dict[str, Any]]) -> int:
    """Count conversational (non-plumbing) messages for the ≤10-message cap."""
    return sum(1 for m in messages if not _is_plumbing(m))


def clarifying_question_count(messages: list[dict[str, Any]]) -> int:
    """Count clarifying questions already asked in the conversation.

    Reads the history deterministically — one per assistant ``ask_clarifying_question`` tool
    call — so the loop can hard-cap clarifying questions without threading an external counter.
    """
    count = 0
    for message in messages:
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == ASK_CLARIFYING_QUESTION
                ):
                    count += 1
    return count


def _citations_of(result: RagResult | None) -> tuple[Citation, ...]:
    """Citations of the last RAG result, or empty when RAG was not used this turn."""
    return tuple(chunk.citation for chunk in result.chunks) if result else ()


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _sync_client() -> Anthropic:
    return Anthropic(api_key=get_settings().anthropic_api_key)


# --------------------------------------------------------------------------------------
# Streaming
# --------------------------------------------------------------------------------------


async def _run_turn(
    session: Session,
    messages: list[dict[str, Any]],
    prior_cost_inr: float,
) -> AsyncIterator[SSEEvent]:
    """Drive one streamed turn over ``messages`` (mutated in place), yielding SSE frames.

    Contract: emits ``status`` at tool-use boundaries, ``token`` for the final answer's
    text, a ``citations`` frame when ``rag_search`` was used, a ``usage`` frame aggregating
    the turn's token cost/latency plus running ``cumulative_cost_inr``, then ``done``. On a
    report tool call it yields a terminal ``report_request`` (with the tool's widget spec
    and pending ``tool_use_id``) followed by ``usage`` and ``done`` — the report renders as
    a widget outside the model, so the turn ends (no FinX call, no resume). Any failure
    yields a single ``error`` frame.
    """
    settings = get_settings()
    system = build_system_prompt()
    client = _client()

    total_input = 0
    total_output = 0
    last_rag: RagResult | None = None
    start = time.perf_counter()

    try:
        yield StatusEvent(message=_STATUS_GENERATING)
        while True:
            allow_clarifying = (
                clarifying_question_count(messages) < MAX_CLARIFYING_QUESTIONS
            )
            async with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=_MAX_TOKENS,
                system=system,
                tools=available_tools(allow_clarifying),
                messages=messages,
            ) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                    ):
                        yield TokenEvent(text=event.delta.text)
                final = await stream.get_final_message()

            total_input += final.usage.input_tokens
            total_output += final.usage.output_tokens
            messages.append(
                {"role": "assistant", "content": _serialize_content(final.content)}
            )

            tool_uses = [b for b in final.content if b.type == "tool_use"]
            if not tool_uses:
                break

            # A report tool call ends the turn: the report renders as a widget outside the
            # model. Handle it before any other tool so no FinX call is attempted with
            # model-supplied parameters, and always close the stream with usage + done so
            # the frontend can clear its progress indicator (CHO-61).
            report_call = next(
                (b for b in tool_uses if is_report_tool(b.name)), None
            )
            if report_call is not None:
                spec = report_widget_spec(report_call.name)
                yield ReportRequestEvent(
                    report_type=spec.report_type,  # type: ignore[arg-type]
                    steps=list(spec.steps),
                    tool_use_id=report_call.id,
                )
                latency_ms = (time.perf_counter() - start) * 1000
                yield UsageEvent(
                    usage=build_usage(
                        settings.anthropic_model,
                        total_input,
                        total_output,
                        latency_ms,
                        prior_cost_inr,
                    )
                )
                yield DoneEvent(stop_reason="report_request")
                return

            tool_results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                if is_clarifying_tool(tool_use.name):
                    # Intent-only: prompt the model to pose its question as text next iteration.
                    content = _CLARIFY_INSTRUCTION
                else:
                    yield StatusEvent(message=_STATUS_LOOKUP)
                    result = dispatch_tool(tool_use.name, tool_use.input, session)
                    last_rag = result
                    content = _rag_tool_result(result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": content,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            yield StatusEvent(message=_STATUS_GENERATING)

        if last_rag is not None:
            yield CitationsEvent(citations=list(_citations_of(last_rag)))

        latency_ms = (time.perf_counter() - start) * 1000
        usage = build_usage(
            settings.anthropic_model,
            total_input,
            total_output,
            latency_ms,
            prior_cost_inr,
        )
        yield UsageEvent(usage=usage)
        yield DoneEvent(stop_reason="end_turn")
    except Exception as exc:  # pragma: no cover - defensive; surfaced as a client-safe frame
        yield ErrorEvent(message=f"agent turn failed: {exc.__class__.__name__}")


async def _ticket_offer_stream(prior_cost_inr: float) -> AsyncIterator[SSEEvent]:
    """Emit the support-ticket offer as a complete (token/usage/done) stream, no model call.

    Used when the conversation has hit the hard message cap: the assistant offers a ticket
    instead of continuing to probe. Cost is zero (no completion is generated).
    """
    yield TokenEvent(text=_TICKET_OFFER)
    yield UsageEvent(
        usage=build_usage(
            get_settings().anthropic_model, 0, 0, 0.0, prior_cost_inr
        )
    )
    yield DoneEvent(stop_reason="cap_reached")


async def agent_reply_stream(
    session: Session,
    messages: list[dict[str, Any]],
    *,
    prior_cost_inr: float = 0.0,
) -> AsyncIterator[SSEEvent]:
    """Stream one agent turn as ``SSEEvent``s (status -> token -> citations -> usage -> done).

    Contract: registers ``rag_search`` and the five intent-only report tools, disables
    thinking, and loops call->tools->repeat until a final answer, mapping the run to SSE
    frames (see :func:`_run_turn`). A report tool call yields a terminal ``report_request``
    then ``usage``/``done``. When the
    conversation is already at the ``MAX_MESSAGES`` cap, no model call is made and the
    support-ticket offer is streamed instead. ``prior_cost_inr`` is the conversation's
    cumulative cost before this turn (0 on turn 1); ``messages`` is not mutated for the
    caller (a working copy is used). The turn runs inside a root ``agent`` trace span tagged
    with the session's thread/user id.
    """
    tracer = get_tracer()

    @tracer.observe(type="agent", name="agent_reply_stream")
    async def _traced() -> AsyncIterator[SSEEvent]:
        tracer.update_current_trace(
            thread_id=session.session_id, user_id=session.user_id
        )
        if conversation_message_count(messages) >= MAX_MESSAGES:
            async for frame in _ticket_offer_stream(prior_cost_inr):
                yield frame
            return
        async for frame in _run_turn(session, list(messages), prior_cost_inr):
            yield frame

    async for frame in _traced():
        yield frame


# --------------------------------------------------------------------------------------
# Non-streaming (evals)
# --------------------------------------------------------------------------------------


def agent_reply(
    session: Session,
    messages: list[dict[str, Any]],
    *,
    prior_cost_inr: float = 0.0,
) -> AgentReply:
    """Run one agent turn to completion and return the final :class:`AgentReply`.

    Contract: same loop as the streaming path (same tools, prompt, thinking disabled) but
    returns text + citations + usage instead of frames — the model callback used by evals.
    Citations are those of the last ``rag_search`` when RAG was used. ``tools_called``
    records every tool name invoked during the turn (``rag_search``, any report tool,
    ``ask_clarifying_question``) so intent-routing evals can assert the path taken without
    inferring it from citations. If a report tool is called there is no widget to collect
    parameters, so a neutral tool result is fed back (the model is told to direct the user
    to the report widget rather than fabricate values) and the loop continues to a final
    answer. At the ``MAX_MESSAGES`` cap it returns the support-ticket offer without calling
    the model. Runs inside a root ``agent`` span.
    """
    tracer = get_tracer()

    @tracer.observe(type="agent", name="agent_reply")
    def _traced() -> AgentReply:
        tracer.update_current_trace(
            thread_id=session.session_id, user_id=session.user_id
        )
        settings = get_settings()
        model = settings.anthropic_model

        if conversation_message_count(messages) >= MAX_MESSAGES:
            return AgentReply(
                text=_TICKET_OFFER,
                usage=build_usage(model, 0, 0, 0.0, prior_cost_inr),
            )

        # A synchronous client mirrors the async streaming loop for eval callers.
        client = _sync_client()
        system = build_system_prompt()
        work = list(messages)
        total_input = 0
        total_output = 0
        last_rag: RagResult | None = None
        tools_called: list[str] = []
        start = time.perf_counter()
        final_text = ""

        while True:
            allow_clarifying = (
                clarifying_question_count(work) < MAX_CLARIFYING_QUESTIONS
            )
            response = client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                system=system,
                tools=available_tools(allow_clarifying),
                messages=work,
            )
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            work.append(
                {"role": "assistant", "content": _serialize_content(response.content)}
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                final_text = "".join(
                    b.text for b in response.content if b.type == "text"
                )
                break

            tool_results: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                tools_called.append(tool_use.name)
                if is_report_tool(tool_use.name):
                    content = (
                        "Report parameters are collected from the user via a secure "
                        "frontend widget, which is not available in this context. Tell the "
                        "user to use the report widget; do not fabricate any values."
                    )
                elif is_clarifying_tool(tool_use.name):
                    content = _CLARIFY_INSTRUCTION
                else:
                    result = dispatch_tool(tool_use.name, tool_use.input, session)
                    last_rag = result
                    content = _rag_tool_result(result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": content,
                    }
                )
            work.append({"role": "user", "content": tool_results})

        latency_ms = (time.perf_counter() - start) * 1000
        return AgentReply(
            text=final_text,
            citations=_citations_of(last_rag),
            usage=build_usage(model, total_input, total_output, latency_ms, prior_cost_inr),
            tools_called=tuple(tools_called),
        )

    return _traced()
