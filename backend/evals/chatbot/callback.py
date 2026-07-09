"""Agent-adapting ``model_callback`` for DeepEval's ``ConversationSimulator``.

The simulator role-plays a user against our real agent: on each simulated user turn it calls
:func:`model_callback` with the new ``input``, the prior ``turns``, and a per-conversation
``thread_id``. The callback rebuilds the Anthropic message history from ``turns``, appends the
new user message, runs one real agent turn via :func:`~backend.agent.loop.agent_reply`, and
returns the reply as an assistant :class:`~deepeval.test_case.Turn`.

``agent_reply`` is synchronous (it drives a blocking Anthropic loop), so it is dispatched to a
worker thread to avoid blocking the simulator's event loop while conversations run concurrently.

Reflecting the reply onto ``Turn``:

- ``content`` — the agent's reply text.
- ``retrieval_context`` — ``agent_reply`` surfaces only citation *provenance*
  (``topic``/``section``/``question``) for the last ``rag_search``, not raw chunk bodies, so
  each citation is rendered to a compact string. This keeps the multi-turn RAG metrics usable
  if they are added later; the metrics wired in :mod:`.test_chatbot` do not read it.
- ``tools_called`` — one ``ToolCall`` per name in ``AgentReply.tools_called``, the tools the
  turn actually invoked (``rag_search``, any report tool, ``ask_clarifying_question``). This
  is read directly from the reply rather than inferred from citations, so report-intent and
  clarifying turns — which carry no citations — are represented faithfully. This is what makes
  the simulator's ``tools_called`` usable for category-F intent routing.

Follows ``docs/chatbot_eval/3_multi_turn_simulation.md`` (§ "Returning Rich Turns").
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from backend.agent.loop import agent_reply
from backend.contracts.models import AgentReply, Citation, Session

if TYPE_CHECKING:
    from deepeval.test_case import Turn

# A fixed, synthetic session for simulated conversations. ``rag_search`` does not read the
# session, and the report tools are intent-only in ``agent_reply`` (never executed), so a
# placeholder JWT makes no real FinX call. ``session_id`` is stable so a conversation's
# agent-side traces group under one thread id.
TEST_SESSION = Session(
    client_code="EVAL0001",
    user_id="eval-user",
    mobile_no="0000000000",
    session_token="eval.jwt.placeholder",
    session_id="chatbot-eval-thread",
)


def messages_from(turns: list[Turn] | None, input: str) -> list[dict[str, Any]]:
    """Rebuild the Anthropic message history from prior ``turns`` plus the new user ``input``.

    Contract: maps each prior :class:`~deepeval.test_case.Turn` to a
    ``{"role", "content"}`` dict (roles are already ``"user"``/``"assistant"``) and appends
    the new ``{"role": "user", "content": input}``. ``turns`` may be ``None`` or empty on the
    first turn.
    """
    messages = [{"role": turn.role, "content": turn.content} for turn in (turns or [])]
    messages.append({"role": "user", "content": input})
    return messages


def _citation_text(citation: Citation) -> str:
    """Render a citation's provenance (topic/section/question) as one compact string."""
    parts = [citation.topic, citation.section, citation.question]
    return " — ".join(part for part in parts if part)


def _retrieval_context(reply: AgentReply) -> list[str] | None:
    """Citation provenance strings for the reply, or ``None`` when RAG was not used."""
    if not reply.citations:
        return None
    return [_citation_text(citation) for citation in reply.citations]


# Human-readable descriptions for the tools a turn can invoke, attached to each ``ToolCall``
# so Confident AI renders a meaningful label. Unknown names fall back to an empty description.
_TOOL_DESCRIPTIONS = {
    "rag_search": "Search the Choice FinX customer-support knowledge base.",
    "ledger": "Signal intent for the account ledger report (intent-only).",
    "global_pnl": "Signal intent for the global P&L report (intent-only).",
    "detailed_pnl": "Signal intent for the detailed P&L report (intent-only).",
    "contract_notes": "Signal intent for the contract notes report (intent-only).",
    "tax_report": "Signal intent for the tax report (intent-only).",
    "ask_clarifying_question": "Ask the user one clarifying question for a missing detail.",
}


def _tools_called(reply: AgentReply) -> list[Any] | None:
    """One ``ToolCall`` per name the turn actually invoked (from ``AgentReply.tools_called``).

    Returns ``None`` when the turn called no tools, so a plain conversational turn carries no
    tool calls. Preserves order and repetition as recorded on the reply.
    """
    if not reply.tools_called:
        return None
    from deepeval.test_case import ToolCall

    return [
        ToolCall(name=name, description=_TOOL_DESCRIPTIONS.get(name, ""))
        for name in reply.tools_called
    ]


async def model_callback(
    input: str,
    turns: list[Turn] | None = None,
    thread_id: str | None = None,
) -> Turn:
    """Drive one real agent turn for the simulator and return it as an assistant ``Turn``.

    Contract: rebuilds history from ``turns`` + ``input`` (see :func:`messages_from`), runs
    :func:`~backend.agent.loop.agent_reply` on :data:`TEST_SESSION` in a worker thread, and
    returns ``Turn(role="assistant", content=..., retrieval_context=..., tools_called=...)``
    reflecting that reply. ``thread_id`` is accepted (the simulator passes a per-conversation
    id) but the fixed session supplies its own stable thread id for tracing.
    """
    from deepeval.test_case import Turn

    messages = messages_from(turns, input)
    reply = await asyncio.to_thread(agent_reply, TEST_SESSION, messages)
    return Turn(
        role="assistant",
        content=reply.text,
        retrieval_context=_retrieval_context(reply),
        tools_called=_tools_called(reply),
    )
