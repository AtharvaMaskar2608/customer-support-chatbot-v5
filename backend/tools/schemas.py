"""Anthropic tool definitions for the five FinX middleware reports (intent-only).

These are the model-visible tool schemas the agent registers. They are deliberately
**intent-only**: every ``input_schema`` exposes **no data properties**, so the model can
signal only *that* a report family is relevant — never its variant (Normal/MTF, segment,
financial year) or dates. A model tool call becomes a ``report_request`` SSE frame; a
frontend widget then collects the actual parameter values and ``POST /report`` runs the
call. This makes it structurally impossible for the model to fabricate report parameters.
"""

from typing import Any

# An empty object schema: the model may call the tool but supplies no arguments.
_INTENT_ONLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

LEDGER_TOOL: dict[str, Any] = {
    "name": "ledger",
    "description": (
        "Signal that the user wants their account ledger statement (Normal or MTF). "
        "Call this when a ledger / account statement is relevant. Do NOT supply any "
        "parameters — the variant (Normal vs MTF) and date range are collected from the "
        "user via a secure widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

GLOBAL_PNL_TOOL: dict[str, Any] = {
    "name": "global_pnl",
    "description": (
        "Signal that the user wants their global (summary) profit-and-loss report for a "
        "segment (Equity, Derivatives, or Commodity). Call this when a P&L / profit "
        "summary is relevant. Do NOT supply any parameters — the segment and date range "
        "are collected from the user via a secure widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

DETAILED_PNL_TOOL: dict[str, Any] = {
    "name": "detailed_pnl",
    "description": (
        "Signal that the user wants their detailed (scrip/transaction-level) "
        "profit-and-loss report (Standard or Commodity). Call this when a detailed P&L "
        "breakdown is relevant. Do NOT supply any parameters — the segment and date range "
        "are collected from the user via a secure widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

CONTRACT_NOTES_TOOL: dict[str, Any] = {
    "name": "contract_notes",
    "description": (
        "Signal that the user wants their contract notes for a date range. Call this when "
        "contract notes are relevant. Do NOT supply any parameters — the date range is "
        "collected from the user via a secure widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

TAX_REPORT_TOOL: dict[str, Any] = {
    "name": "tax_report",
    "description": (
        "Signal that the user wants their tax report for a financial year. Call this when "
        "a tax / capital-gains report is relevant. Do NOT supply any parameters — the "
        "financial year is collected from the user via a secure widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

# All five report tool schemas, in registry order.
REPORT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    LEDGER_TOOL,
    GLOBAL_PNL_TOOL,
    DETAILED_PNL_TOOL,
    CONTRACT_NOTES_TOOL,
    TAX_REPORT_TOOL,
]
