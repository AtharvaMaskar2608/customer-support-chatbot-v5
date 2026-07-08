"""Server-Sent Event contract.

``SSEEvent`` is a discriminated union (on the ``type`` field) of every frame the API
streams to the frontend. ``usage`` frames carry a running ``cumulative_cost_inr``;
``report_request`` frames name the report and the fields the frontend widget must
collect, so the model never supplies report parameter values itself.
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.models import Citation, Usage


class CardOption(BaseModel):
    """One selectable card in a ``CardStep``.

    ``value`` is an opaque FinX API token (e.g. ``"MTF"``, ``"Group1"``,
    ``"2025-2026"``) that the backend maps to an upstream parameter; the frontend
    never interprets it, only echoes it back on selection.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class CardStep(BaseModel):
    """A widget step presenting a set of variant cards for ``param``."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["cards"] = "cards"
    param: str
    options: tuple[CardOption, ...]


class DateRangeStep(BaseModel):
    """A widget step collecting a ``from``/``to`` date range (``YYYY-MM-DD``)."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["date_range"] = "date_range"
    from_param: str = "from_date"
    to_param: str = "to_date"


WidgetStep = Annotated[Union[CardStep, DateRangeStep], Field(discriminator="kind")]


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
    parameter values, which are fed back via a separate resume call. ``steps`` is the
    declarative widget spec the frontend chains in order (a card picker, then a date
    range, etc.). ``fields`` is the legacy flat path, retained defaulted to ``[]`` until
    ``finx-middleware-tools`` removes it.
    """

    type: Literal["report_request"] = "report_request"
    report_type: Literal[
        "ledger",
        "global_pnl",
        "detailed_pnl",
        "contract_notes",
        "tax_report",
        "cml",  # legacy; removed by finx-middleware-tools
        "contract_note",  # legacy; removed by finx-middleware-tools
    ]
    steps: list[WidgetStep] = []
    fields: list[str] = []  # legacy; removed by finx-middleware-tools
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
