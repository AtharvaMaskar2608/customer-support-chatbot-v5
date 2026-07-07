"""Server-Sent Event contract.

``SSEEvent`` is a discriminated union (on the ``type`` field) of every frame the API
streams to the frontend. ``usage`` frames carry a running ``cumulative_cost_inr``;
``report_request`` frames name the report and the fields the frontend widget must
collect, so the model never supplies report parameter values itself.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from backend.contracts.models import Citation, Usage


class StatusEvent(BaseModel):
    """Human-readable progress marker (e.g. "searching knowledge base")."""

    type: Literal["status"] = "status"
    message: str


class TokenEvent(BaseModel):
    """A streamed fragment of the assistant's reply text."""

    type: Literal["token"] = "token"
    text: str


class CitationsEvent(BaseModel):
    """The citations backing the reply, emitted once retrieval resolves."""

    type: Literal["citations"] = "citations"
    citations: list[Citation] = Field(default_factory=list)


class UsageEvent(BaseModel):
    """Per-message usage accounting, including running ``cumulative_cost_inr``."""

    type: Literal["usage"] = "usage"
    usage: Usage


class ReportRequestEvent(BaseModel):
    """Signals the frontend to collect report parameters via a structured widget.

    The agent only decides *when* a report is relevant; the widget supplies the
    parameter values, which are fed back via a separate resume call.
    """

    type: Literal["report_request"] = "report_request"
    report_type: Literal["cml", "contract_note"]
    fields: list[str]
    tool_use_id: str


class DoneEvent(BaseModel):
    """Terminal frame: the turn completed successfully."""

    type: Literal["done"] = "done"
    stop_reason: str | None = None


class ErrorEvent(BaseModel):
    """Terminal frame: the turn failed with a client-safe message."""

    type: Literal["error"] = "error"
    message: str


SSEEvent = Annotated[
    Union[
        StatusEvent,
        TokenEvent,
        CitationsEvent,
        UsageEvent,
        ReportRequestEvent,
        DoneEvent,
        ErrorEvent,
    ],
    Field(discriminator="type"),
]
