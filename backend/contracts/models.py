"""Shared, frozen Pydantic v2 data contracts.

These models are the interface between all modules (RAG, tools, agent, API, evals).
Downstream code imports them rather than redefining equivalent shapes, so the contract
stays single-sourced. Models are ``frozen`` (immutable, hashable) and kept minimal and
additive so freezing them early does not force edits later.
"""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """Provenance for a retrieved chunk, derived from ``qa_chunks`` metadata."""

    model_config = ConfigDict(frozen=True)

    topic: str | None = None
    section: str | None = None
    question: str | None = None
    answer_source: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None


class RagChunk(BaseModel):
    """A single retrieved chunk with its relevance score and citation."""

    model_config = ConfigDict(frozen=True)

    id: int
    chunk: str
    score: float
    citation: Citation


class RagResult(BaseModel):
    """The result of a retrieval call: the query and its ranked chunks."""

    model_config = ConfigDict(frozen=True)

    query: str
    chunks: tuple[RagChunk, ...] = ()


class ReportResult(BaseModel):
    """Outcome of a FinX report tool call.

    Report tools are read-only and never raise; a failure is represented as
    ``ReportResult(ok=False, data=None, error=<message>)``.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    data: dict | None = None
    error: str | None = None


class ReportColumn(BaseModel):
    """One column of a tabular report: the row-dict ``key`` and its header ``label``."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str


class ReportRenderPayload(BaseModel):
    """The JSON body ``POST /report`` returns for the frontend to render directly.

    Report results bypass the LLM entirely, so the backend shapes rows/columns
    server-side and the frontend renderer stays a generic switch on ``kind``:
    ``table`` (``columns`` + ``rows``), ``link`` (``url``), or ``empty``/``error``
    (``message``). The ``url`` (e.g. a tax-report PDF) rides only in this payload and
    MUST NEVER enter model context — generated report URLs are unauthenticated.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["table", "link", "empty", "error"]
    title: str
    columns: tuple[ReportColumn, ...] = ()
    rows: tuple[dict, ...] = ()
    url: str | None = None
    message: str | None = None


class Session(BaseModel):
    """Authenticated user/session identity supplied by the POC login form.

    ``session_token`` is a per-session FinX JWT; the API layer trims sensitive fields
    before echoing session state to the frontend. ``session_id`` uniquely identifies this
    session/conversation (distinct from the per-client ``client_code``) and is used as the
    tracing ``thread_id`` so a conversation's turns group together. It defaults to a
    generated id; the API layer supplies its own so the session store key and the trace
    thread id match, and it must stay stable for the session's lifetime.

    ``finx_session_id`` is the FinX middleware SessionId used to authorize report calls —
    distinct from the legacy JWT ``session_token`` (both are collected by the login form).
    It defaults to ``""`` so existing constructors stay valid; requiredness is enforced at
    the API boundary in ``finx-middleware-tools``.
    """

    model_config = ConfigDict(frozen=True)

    client_code: str
    user_id: str
    mobile_no: str
    session_token: str
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    finx_session_id: str = ""


class Usage(BaseModel):
    """Per-message token/cost/latency accounting with a running cumulative cost."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cost_inr: float = 0.0
    latency_ms: float = 0.0
    cumulative_cost_inr: float = 0.0


class AgentReply(BaseModel):
    """A completed agent turn: reply text plus its citations and usage.

    ``tools_called`` records the tool names invoked during the turn (e.g. ``rag_search``,
    a report tool name, or ``ask_clarifying_question``), so agentic intent-routing evals
    can assert transactional-report vs RAG-explanation routing deterministically. It
    defaults to ``()`` until the agent loop populates it in ``finx-middleware-tools``.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    citations: tuple[Citation, ...] = ()
    usage: Usage | None = None
    tools_called: tuple[str, ...] = ()
