"""Tool registry and dispatch for the agentic loop.

Exposes the model-visible tool schemas (:data:`TOOLS`) the loop registers with the
Anthropic Messages API, and dispatch for the tools the loop actually executes inline.

Only ``rag_search`` runs inside the loop. The report tools (``cml_report``,
``contract_note``) are **intent-only**: a model call to one signals *that* a report is
wanted, never its parameters. The loop turns such a call into a ``report_request`` SSE
frame (see :data:`REPORT_TOOLS`), the frontend widget collects the parameters, and the
FinX call is made outside the loop and fed back via resume — so the model can never
fabricate ``client_id``/``mobile_no``/``contract_date`` values.
"""

from __future__ import annotations

from typing import Any

from backend.contracts.models import RagResult, Session
from backend.rag.schemas import RAG_SEARCH_TOOL
from backend.rag.search import rag_search
from backend.tools.schemas import CML_REPORT_TOOL, CONTRACT_NOTE_TOOL

# Structural marker for a clarifying question. It is intent-only (no parameters): the model
# calls it to signal it needs a missing detail, and the loop then prompts it to write the
# single question as its reply. Making the ask a tool call lets the loop count clarifying
# questions deterministically from history and hard-cap them (see backend.agent.loop).
ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
ASK_CLARIFYING_QUESTION_TOOL: dict[str, Any] = {
    "name": ASK_CLARIFYING_QUESTION,
    "description": (
        "Call this (no parameters) only when you genuinely need a missing detail from the "
        "user before you can help. After calling it you will be prompted to write the single "
        "clarifying question as your reply. Prefer answering with what you already have; you "
        "may ask at most two clarifying questions per conversation."
    ),
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
}

# The full tool list handed to the Messages API on every turn.
TOOLS: list[dict[str, Any]] = [
    RAG_SEARCH_TOOL,
    CML_REPORT_TOOL,
    CONTRACT_NOTE_TOOL,
    ASK_CLARIFYING_QUESTION_TOOL,
]


def is_clarifying_tool(name: str) -> bool:
    """Return whether ``name`` is the structural clarifying-question tool."""
    return name == ASK_CLARIFYING_QUESTION


def available_tools(allow_clarifying: bool) -> list[dict[str, Any]]:
    """Tools offered to the model this turn.

    Withholds ``ask_clarifying_question`` once the conversation has hit the clarifying-question
    cap, so the model literally cannot ask a third — the cap is a constraint, not a request.
    """
    if allow_clarifying:
        return TOOLS
    return [tool for tool in TOOLS if tool is not ASK_CLARIFYING_QUESTION_TOOL]

# Report tool name -> (report_type for the SSE frame, fields the widget must collect).
# The report_type values match ``ReportRequestEvent.report_type``; the fields mirror the
# arguments of the corresponding ``backend.tools.finx`` function the resume call invokes.
REPORT_TOOLS: dict[str, tuple[str, list[str]]] = {
    "cml_report": ("cml", ["client_id"]),
    "contract_note": ("contract_note", ["mobile_no", "contract_date"]),
}


def is_report_tool(name: str) -> bool:
    """Return whether ``name`` is an intent-only report tool (the loop must pause on it)."""
    return name in REPORT_TOOLS


def report_request_fields(name: str) -> tuple[str, list[str]]:
    """Return ``(report_type, fields)`` for a report tool. Raises ``KeyError`` if unknown."""
    return REPORT_TOOLS[name]


def dispatch_tool(name: str, tool_input: dict[str, Any], session: Session) -> RagResult:
    """Execute a non-report tool and return its result.

    Contract: dispatches ``rag_search`` (the only tool run inside the loop) with the
    model-supplied ``query``, returning a :class:`RagResult`. ``session`` is threaded in for
    future session-scoped tools and to keep a uniform dispatch signature. Report tools are
    intent-only and MUST NOT reach here — calling with a report tool name (or any unknown
    name) raises ``ValueError`` so a mis-routed report call fails loudly rather than hitting
    FinX with model-fabricated parameters.
    """
    if name == "rag_search":
        return rag_search(query=tool_input["query"])
    if is_report_tool(name):
        raise ValueError(f"{name} is intent-only and must be handled as a report_request")
    raise ValueError(f"unknown tool: {name}")
