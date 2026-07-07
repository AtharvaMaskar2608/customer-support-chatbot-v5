"""Shared, frozen Pydantic v2 data contracts.

These models are the interface between all modules (RAG, tools, agent, API, evals).
Downstream code imports them rather than redefining equivalent shapes, so the contract
stays single-sourced. Models are ``frozen`` (immutable, hashable) and kept minimal and
additive so freezing them early does not force edits later.
"""

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


class Session(BaseModel):
    """Authenticated user/session identity supplied by the POC login form.

    ``session_token`` is a per-session FinX JWT; the API layer trims sensitive fields
    before echoing session state to the frontend.
    """

    model_config = ConfigDict(frozen=True)

    client_code: str
    user_id: str
    mobile_no: str
    session_token: str


class Usage(BaseModel):
    """Per-message token/cost/latency accounting with a running cumulative cost."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cost_inr: float = 0.0
    latency_ms: float = 0.0
    cumulative_cost_inr: float = 0.0


class AgentReply(BaseModel):
    """A completed agent turn: reply text plus its citations and usage."""

    model_config = ConfigDict(frozen=True)

    text: str
    citations: tuple[Citation, ...] = ()
    usage: Usage | None = None
