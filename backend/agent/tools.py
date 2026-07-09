"""Tool registry and dispatch for the agentic loop.

Exposes the model-visible tool schemas (:data:`TOOLS`) the loop registers with the
Anthropic Messages API, and dispatch for the tools the loop actually executes inline.

Only ``rag_search`` runs inside the loop. The five report tools (``ledger``,
``global_pnl``, ``detailed_pnl``, ``contract_notes``, ``tax_report``) are **intent-only**:
a model call to one signals *that* a report family is wanted, never its parameters. The
loop turns such a call into a terminal ``report_request`` SSE frame carrying the tool's
widget spec (see :data:`REPORT_WIDGETS`); the frontend collects the variant/date values and
runs the report via ``POST /report`` — entirely outside the model — so the model can never
fabricate report parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.contracts.events import CardOption, CardStep, DateRangeStep, WidgetStep
from backend.contracts.models import RagResult, Session
from backend.rag.schemas import RAG_SEARCH_TOOL
from backend.rag.search import rag_search
from backend.tools.schemas import REPORT_TOOL_SCHEMAS

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
    *REPORT_TOOL_SCHEMAS,
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


# --------------------------------------------------------------------------------------
# Report widget registry
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportWidgetSpec:
    """A report tool's ``report_type`` and the ordered widget steps its params come from.

    ``steps`` is the declarative widget chain the frontend renders (a card picker, a date
    range, …); its step params are the *only* accepted source of report parameters — the
    API validates ``POST /report`` params against exactly these names.
    """

    report_type: str
    steps: tuple[WidgetStep, ...]


# Report tool name -> its widget spec. The tool name doubles as the ``report_type``.
# Date-range steps carry no defaults (product decision): the user always picks a range.
REPORT_WIDGETS: dict[str, ReportWidgetSpec] = {
    "ledger": ReportWidgetSpec(
        "ledger",
        (
            CardStep(
                param="group",
                options=(
                    CardOption(label="Normal Ledger", value="Group1"),
                    CardOption(label="MTF Ledger", value="MTF"),
                ),
            ),
            DateRangeStep(),
        ),
    ),
    "global_pnl": ReportWidgetSpec(
        "global_pnl",
        (
            CardStep(
                param="group",
                options=(
                    CardOption(label="Equity", value="Cash"),
                    CardOption(label="Derivatives", value="Derv"),
                    CardOption(label="Commodity", value="Comm"),
                ),
            ),
            DateRangeStep(),
        ),
    ),
    "detailed_pnl": ReportWidgetSpec(
        "detailed_pnl",
        (
            CardStep(
                param="group",
                options=(
                    CardOption(label="Standard", value="Group1"),
                    CardOption(label="Commodity", value="Group23"),
                ),
            ),
            DateRangeStep(),
        ),
    ),
    "contract_notes": ReportWidgetSpec(
        "contract_notes",
        (DateRangeStep(),),
    ),
    "tax_report": ReportWidgetSpec(
        "tax_report",
        (
            CardStep(
                param="fin_year",
                options=(
                    CardOption(label="2024-2025", value="2024-2025"),
                    CardOption(label="2025-2026", value="2025-2026"),
                    CardOption(label="2026-2027", value="2026-2027"),
                ),
            ),
        ),
    ),
}


def is_report_tool(name: str) -> bool:
    """Return whether ``name`` is an intent-only report tool (the loop pauses on it)."""
    return name in REPORT_WIDGETS


def report_widget_spec(name: str) -> ReportWidgetSpec:
    """Return the :class:`ReportWidgetSpec` for a report tool. Raises ``KeyError`` if unknown."""
    return REPORT_WIDGETS[name]


def report_param_names(report_type: str) -> list[str]:
    """Return the param names the registry's widget steps collect for ``report_type``.

    These are the only keys ``POST /report`` accepts for that report type — a card step
    contributes its ``param``; a date-range step contributes its ``from_param``/``to_param``.
    Raises ``KeyError`` for an unknown report type.
    """
    names: list[str] = []
    for step in REPORT_WIDGETS[report_type].steps:
        if isinstance(step, CardStep):
            names.append(step.param)
        elif isinstance(step, DateRangeStep):
            names.extend([step.from_param, step.to_param])
    return names


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
