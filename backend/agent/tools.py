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

# The full tool list handed to the Messages API on every turn.
TOOLS: list[dict[str, Any]] = [RAG_SEARCH_TOOL, CML_REPORT_TOOL, CONTRACT_NOTE_TOOL]

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
