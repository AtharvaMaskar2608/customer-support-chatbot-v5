"""Integration tests for hybrid retrieval against the live ``qa_chunks`` table.

These exercise the real Postgres corpus and the OpenAI embedding API, so they require
``DATABASE_URL`` and ``OPENAI_API_KEY`` to be configured; they are skipped otherwise.
"""

import pytest

from backend.config.settings import get_settings
from backend.rag.embed import embed_query
from backend.rag.schemas import RAG_SEARCH_TOOL
from backend.rag.search import _keyword_leg, _vector_leg, rag_search

# A query that is well covered by the FAQ KB and matches both legs lexically + semantically.
_QUERY = "how do I update my mobile number"


@pytest.fixture(scope="module")
def _require_env() -> None:
    """Skip the module unless DB + OpenAI credentials are available."""
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - config missing
        pytest.skip(f"settings unavailable: {exc}")
    if not settings.database_url or not settings.openai_api_key:
        pytest.skip("DATABASE_URL / OPENAI_API_KEY not configured")


def test_embed_query_returns_full_dims(_require_env: None) -> None:
    vec = embed_query(_QUERY)
    assert len(vec) == 3072
    assert all(isinstance(x, float) for x in vec[:5])


def test_vector_leg_returns_rows(_require_env: None) -> None:
    qvec = embed_query(_QUERY)
    rows = _vector_leg(qvec, cand=10)
    assert len(rows) > 0
    assert {"id", "chunk"} <= rows[0].keys()


def test_keyword_leg_returns_rows(_require_env: None) -> None:
    rows = _keyword_leg(_QUERY, cand=10)
    assert len(rows) > 0
    assert {"id", "chunk"} <= rows[0].keys()


def test_rag_search_returns_cited_chunks(_require_env: None) -> None:
    result = rag_search(_QUERY, top_k=5)
    assert result.query == _QUERY
    assert len(result.chunks) >= 1
    assert len(result.chunks) <= 5

    # Fused scores are sorted descending.
    scores = [c.score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)

    top = result.chunks[0]
    assert top.chunk
    assert top.score > 0
    # Citation is populated with at least some source metadata.
    cit = top.citation
    assert any(
        getattr(cit, field) is not None
        for field in ("topic", "section", "question", "answer_source", "source_sheet")
    )


def test_rag_search_tool_schema_is_query_only() -> None:
    assert RAG_SEARCH_TOOL["name"] == "rag_search"
    props = RAG_SEARCH_TOOL["input_schema"]["properties"]
    assert set(props) == {"query"}
    assert RAG_SEARCH_TOOL["input_schema"]["required"] == ["query"]
