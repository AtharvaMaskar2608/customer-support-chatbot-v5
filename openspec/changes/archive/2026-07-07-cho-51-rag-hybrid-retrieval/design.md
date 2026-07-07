## Context

`qa_chunks` is preloaded: `chunk` (embedded text), `embedding vector(3072)`, generated `fts tsvector` (GIN `qa_chunks_fts_gin`), plus metadata (`id, topic, section, question, answer, answer_source, tat, source_sheet, source_row`). No vector index → exact scan, which is correct at ~1.1k rows. The RAG build guide (`docs/rag_guide/1_building_rag_pt1.md`) is generic and specifies dense vector search only; hybrid FTS + RRF and the citation shape are our design decisions grounded in `docs/project_context.md`.

## Goals / Non-Goals

**Goals:**
- Deterministic, exact hybrid retrieval with citations, fast enough at corpus scale.
- A single `rag_search(query, top_k)` entry point usable by both the agent and the eval harness.

**Non-Goals:**
- No ANN index, no reranker/cross-encoder (out of scope, RRF-only).
- No ingestion/embedding of the corpus (already loaded).
- No answer generation (that is the agent's job).

## Decisions

- **Embedding:** OpenAI `text-embedding-3-large`, full 3072 dims (matches the column); embed the **raw user query only**, not the prompt template.
- **Vector leg:** `SELECT id, chunk, <metadata> FROM qa_chunks ORDER BY embedding <=> :qvec LIMIT :cand` (cosine), candidate pool `cand` (e.g. 20) ≥ `top_k`.
- **Keyword leg:** `WHERE fts @@ websearch_to_tsquery('english', :q) ORDER BY ts_rank(fts, websearch_to_tsquery('english', :q)) DESC LIMIT :cand`.
- **Fusion:** RRF `score(d) = Σ_leg 1/(k + rank_leg(d))`, `k=60`; sort desc; take `top_k`. `top_k` default 5 (configurable per call/eval).
- **Citations:** each returned `RagChunk` carries a `Citation` built from `topic`, `section`, `question`, `answer_source`, `source_sheet`, `source_row`, and `id` — enough for the frontend's hoverable citation card.
- **Tracing:** wrap `rag_search` with `tracer.observe(type="retriever")` and `update_current_span(retrieval_context=[chunk.text ...])` so RAG metrics attribute context to the turn.

## Risks / Trade-offs

- RRF `k=60` is the common default; retrieval quality is validated by `rag-evals` (P6) and `k`/`top_k`/candidate-pool are tunable if metrics say so.
- Exact scan cost grows with corpus; acceptable now (~1.1k) — revisit only if the KB grows by orders of magnitude.
