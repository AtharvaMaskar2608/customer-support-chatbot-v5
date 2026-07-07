## Why

The agent's primary tool is retrieval over the FAQ knowledge base (`qa_chunks`, 1102 rows, already embedded). Answers must be grounded and cited. This change implements hybrid retrieval (dense + keyword) and exposes it as the `rag_search` tool.

## What Changes

- Add `rag_search(query, top_k) -> RagResult`:
  1. Embed the raw query with OpenAI `text-embedding-3-large` (full 3072 dims, no truncation).
  2. **Vector search:** `ORDER BY embedding <=> :qvec` (cosine), exact/sequential scan (no ANN index — ~1.1k rows).
  3. **Keyword search:** `websearch_to_tsquery('english', :q)` matched against the generated `qa_chunks.fts` column, ranked by `ts_rank` (GIN-indexed).
  4. **Fuse** the two ranked lists with Reciprocal Rank Fusion (RRF, `k=60`).
  5. Return top-`k` `RagChunk`s with `Citation`s populated from `qa_chunks` metadata.
- Add the Anthropic `RAG_SEARCH_TOOL` schema (model-visible input `{query}`).
- Instrument the retriever with the foundations tracing interface (`observe(type="retriever")`, attach `retrieval_context`).

Follows `docs/rag_guide/1_building_rag_pt1.md` for embeddings + vector search; the FTS SQL and RRF fusion are design additions mandated by `docs/project_context.md` (§3.2 hybrid retrieval + citations) and enabled by the existing `qa_chunks.fts` GIN index.

## Capabilities

### New Capabilities
- `rag-hybrid-retrieval`: hybrid (vector + FTS + RRF) retrieval over `qa_chunks` with citations, exposed as the `rag_search` tool.

## Impact

- New: `backend/rag/search.py` (retrieval), `backend/rag/embed.py` (query embedding), `backend/rag/schemas.py` (`RAG_SEARCH_TOOL`), `backend/rag/__init__.py`.
- Imports `Settings`, `db.fetch`, `RagChunk`/`RagResult`/`Citation`, and the `Tracer` Protocol from foundations. Adds no root dependencies.
- Consumed by `agentic-loop` (tool call) and `rag-evals` (scored against goldens).
