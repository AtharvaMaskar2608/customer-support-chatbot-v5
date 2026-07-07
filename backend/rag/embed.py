"""Query embedding via OpenAI ``text-embedding-3-large``.

The ``qa_chunks.embedding`` column is ``vector(3072)`` — the full, untruncated
``text-embedding-3-large`` output — so query embeddings must match: full 3072 dims,
no Matryoshka ``dimensions`` truncation. Only the raw user query is embedded, never a
prompt template, so the query vector lives in the same space as the stored chunks.
"""

from functools import lru_cache

from openai import OpenAI

from backend.config.settings import get_settings


@lru_cache
def _client() -> OpenAI:
    """Return a cached OpenAI client built from settings (constructed on first use)."""
    return OpenAI(api_key=get_settings().openai_api_key)


def embed_query(text: str) -> list[float]:
    """Embed a raw query string into a full 3072-dim vector.

    Contract: sends ``text`` verbatim to ``text-embedding-3-large`` (model name from
    ``Settings.embedding_model``) with no ``dimensions`` override, so the returned list
    has 3072 floats matching ``qa_chunks.embedding``. Suitable to bind directly as the
    ``:qvec`` parameter for ``embedding <=> :qvec`` cosine ordering.
    """
    response = _client().embeddings.create(
        input=text,
        model=get_settings().embedding_model,
    )
    return response.data[0].embedding
