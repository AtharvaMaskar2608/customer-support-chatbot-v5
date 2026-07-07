## 1. Query embedding

- [x] 1.1 `backend/rag/embed.py`: `embed_query(text) -> list[float]` via OpenAI `text-embedding-3-large`, full 3072 dims, raw query only.

## 2. Hybrid retrieval

- [x] 2.1 `backend/rag/search.py`: vector leg (`embedding <=> :qvec`, exact scan, candidate pool).
- [x] 2.2 Keyword leg (`websearch_to_tsquery`/`ts_rank` over `qa_chunks.fts`).
- [x] 2.3 RRF fusion (`k=60`), sort, take `top_k`.
- [x] 2.4 Build `RagChunk` + `Citation` from `qa_chunks` metadata; return `RagResult`.
- [x] 2.5 `rag_search(query, top_k=5) -> RagResult` public entry point.

## 3. Tool schema + tracing

- [x] 3.1 `backend/rag/schemas.py`: `RAG_SEARCH_TOOL` (model-visible input `{query}`).
- [x] 3.2 Wrap retriever with `tracer.observe(type="retriever")` + `update_current_span(retrieval_context=...)`.

## 4. Done condition

- [x] 4.1 `openspec validate rag-hybrid-retrieval --strict` passes.
- [x] 4.2 Test: `rag_search("how do I ...", top_k=5)` against the live `qa_chunks` returns ≥1 chunk with a populated `Citation`; vector-only and keyword-only legs each return rows. `pytest backend/rag`.
