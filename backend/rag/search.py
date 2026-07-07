"""Hybrid retrieval over ``qa_chunks`` (dense vector + FTS keyword, fused with RRF).

``rag_search`` embeds the raw query, runs two independent ranked retrievals — a cosine
vector search (``embedding <=> qvec``, exact sequential scan; no ANN index at ~1.1k rows)
and a keyword search (``websearch_to_tsquery``/``ts_rank`` over the generated
``qa_chunks.fts`` column) — then fuses them with Reciprocal Rank Fusion (``k=60``) and
returns the top-``top_k`` chunks, each carrying a :class:`Citation` from ``qa_chunks``
metadata. Retrieval is wrapped in a ``retriever`` tracing span carrying
``retrieval_context``.
"""

from typing import Any

from pgvector import Vector

from backend.contracts.models import Citation, RagChunk, RagResult
from backend.db.query import fetch
from backend.rag.embed import embed_query
from backend.tracing.interface import get_tracer

# RRF constant and candidate-pool size. ``k=60`` is the common RRF default; the candidate
# pool per leg is kept comfortably larger than any realistic ``top_k`` so fusion has room.
_RRF_K = 60
_CANDIDATE_POOL = 20

# Columns pulled from every leg: identity + text for the chunk, plus citation metadata.
_SELECT_COLS = (
    "id, chunk, topic, section, question, answer_source, source_sheet, source_row"
)


def _vector_leg(qvec: list[float], cand: int) -> list[dict[str, Any]]:
    """Rank candidates by cosine distance via an exact scan (closest first).

    Contract: returns up to ``cand`` rows ordered by ``embedding <=> qvec`` ascending
    (nearest first). No approximate index is used, so ranking is deterministic and
    full-recall at corpus scale.
    """
    sql = (
        f"SELECT {_SELECT_COLS} FROM qa_chunks "
        "ORDER BY embedding <=> %(qvec)s LIMIT %(cand)s"
    )
    # Wrap the raw list in ``pgvector.Vector`` so the registered psycopg adapter binds it
    # as ``vector`` (a bare list would be sent as ``double precision[]`` and fail to match
    # the ``<=>`` operator).
    return fetch(sql, {"qvec": Vector(qvec), "cand": cand})


def _keyword_leg(query: str, cand: int) -> list[dict[str, Any]]:
    """Rank candidates by ``ts_rank`` over the FTS column (best match first).

    Contract: returns up to ``cand`` rows matching ``websearch_to_tsquery('english', q)``
    against ``qa_chunks.fts`` (GIN-indexed), ordered by ``ts_rank`` descending. Returns an
    empty list when the query has no lexical matches.
    """
    sql = (
        f"SELECT {_SELECT_COLS} FROM qa_chunks "
        "WHERE fts @@ websearch_to_tsquery('english', %(q)s) "
        "ORDER BY ts_rank(fts, websearch_to_tsquery('english', %(q)s)) DESC "
        "LIMIT %(cand)s"
    )
    return fetch(sql, {"q": query, "cand": cand})


def _citation(row: dict[str, Any]) -> Citation:
    """Build a :class:`Citation` from a ``qa_chunks`` row's metadata."""
    return Citation(
        topic=row["topic"],
        section=row["section"],
        question=row["question"],
        answer_source=row["answer_source"],
        source_sheet=row["source_sheet"],
        source_row=row["source_row"],
    )


def _fuse(
    vector_rows: list[dict[str, Any]],
    keyword_rows: list[dict[str, Any]],
    top_k: int,
) -> list[RagChunk]:
    """Fuse two ranked lists with Reciprocal Rank Fusion and take the top ``top_k``.

    Contract: for each leg a document at 1-based rank ``r`` contributes ``1/(k + r)`` to
    its fused score (``k=60``); scores sum across legs. Documents are sorted by fused
    score descending and the first ``top_k`` are returned as :class:`RagChunk`s. Row
    payloads (chunk text, metadata) are taken from whichever leg first surfaced the id.
    """
    scores: dict[int, float] = {}
    rows_by_id: dict[int, dict[str, Any]] = {}

    for leg in (vector_rows, keyword_rows):
        for rank, row in enumerate(leg, start=1):
            doc_id = row["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank)
            rows_by_id.setdefault(doc_id, row)

    ranked_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:top_k]
    return [
        RagChunk(
            id=doc_id,
            chunk=rows_by_id[doc_id]["chunk"],
            score=scores[doc_id],
            citation=_citation(rows_by_id[doc_id]),
        )
        for doc_id in ranked_ids
    ]


def _retrieve(query: str, top_k: int) -> RagResult:
    """Run both legs, fuse, and assemble the :class:`RagResult` (untraced core)."""
    qvec = embed_query(query)
    cand = max(_CANDIDATE_POOL, top_k)
    vector_rows = _vector_leg(qvec, cand)
    keyword_rows = _keyword_leg(query, cand)
    chunks = _fuse(vector_rows, keyword_rows, top_k)
    return RagResult(query=query, chunks=tuple(chunks))


def rag_search(query: str, top_k: int = 5) -> RagResult:
    """Hybrid-retrieve the top ``top_k`` chunks for ``query`` with citations.

    Contract: embeds the raw ``query`` (full 3072 dims), runs the vector and keyword legs
    over a candidate pool of ``max(20, top_k)``, fuses them with RRF (``k=60``), and
    returns a :class:`RagResult` whose ``chunks`` are ordered by fused score descending
    (length ``≤ top_k``). Retrieval runs inside a ``retriever`` span with
    ``retrieval_context`` set to the retrieved chunk texts; with tracing disabled the
    active tracer is the no-op tracer and behaviour is unchanged. The active tracer is
    resolved at call time, so runtime ``set_tracer`` swaps take effect.
    """
    tracer = get_tracer()

    @tracer.observe(type="retriever", name="rag_search")
    def _traced() -> RagResult:
        result = _retrieve(query, top_k)
        tracer.update_current_span(
            input=query,
            retrieval_context=[chunk.chunk for chunk in result.chunks],
        )
        return result

    return _traced()
