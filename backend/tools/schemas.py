"""Anthropic tool definitions for the FinX report tools (intent-only).

These are the model-visible tool schemas the agent registers. They are deliberately
**intent-only**: the ``input_schema`` exposes **no data properties**, so the model
cannot fabricate ``client_id``/``mobile_no``/``contract_date`` values. A model tool call
signals only that a report is relevant; the agent loop turns it into a ``report_request``
SSE frame and the frontend widget collects the actual parameter values.
"""

# An empty object schema: the model may call the tool but supplies no arguments.
_INTENT_ONLY_SCHEMA: dict = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CML_REPORT_TOOL: dict = {
    "name": "cml_report",
    "description": (
        "Signal that the user wants their CML (Client Master List) report. "
        "Call this when a CML report is relevant; do NOT supply any parameters — "
        "the client id is collected from the user via a frontend widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}

CONTRACT_NOTE_TOOL: dict = {
    "name": "contract_note",
    "description": (
        "Signal that the user wants a Contract Note report. "
        "Call this when a contract note is relevant; do NOT supply any parameters — "
        "the mobile number and contract date are collected from the user via a "
        "frontend widget."
    ),
    "input_schema": _INTENT_ONLY_SCHEMA,
}
