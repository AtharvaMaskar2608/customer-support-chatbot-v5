## Context

Fresh repo (docs + empty OpenSpec scaffold). The KB is already loaded into Postgres `qa_chunks` (1102 rows, `embedding vector(3072)`, generated `fts` tsvector + GIN index — verified against the live DB). Nine changes will fan out in parallel and must share one set of types and one config surface. Overall product spec is `docs/project_context.md`; module build details live in the `docs/rag_guide/`, `docs/chatbot_eval/`, and `docs/tracing/` guides, which downstream changes follow.

## Goals / Non-Goals

**Goals:**
- One import site for settings, data contracts, DB access, and the tracing interface.
- Fail-fast on missing/invalid config at startup, not mid-request.
- Contracts stable enough that P1–P8 build against them without edits.

**Non-Goals:**
- No retrieval, tool, agent, API, eval, or frontend logic.
- No DB writes, migrations, or ingestion (embeddings already loaded).
- No concrete tracing backend (that is `tracing-foundation`).

## Decisions

- **Single `DATABASE_URL`** (not split host/port); config via `pydantic-settings` reading `.env`.
- **`ANTHROPIC_MODEL` configurable**, default `claude-sonnet-4-5`; embedding model default `text-embedding-3-large` (3072 dims, no truncation), matching `docs/rag_guide/1_building_rag_pt1.md`.
- **Two FinX base URLs** (`FINX_CML_BASE_URL`, `FINX_CONTRACT_NOTE_BASE_URL`) — CML (`finxomne...`) and Contract Note (`finx...`) live on different hosts.
- **`SSEEvent`** is a discriminated union: `status | token | citations | usage | report_request | done | error`; `usage` frames carry `cumulative_cost_inr`; `report_request` frames name the `report_type` and the fields the frontend widget must collect (report params are widget-supplied, never model-fabricated).
- **`Session`** holds `client_code`, `user_id`, `mobile_no`, `session_token` (JWT); trimmed by the API layer.
- **Tracing interface** is a `Protocol` with a no-op default so importers never hard-depend on DeepEval; the concrete `@observe`-based impl lands in `tracing-foundation` per `docs/tracing/`.
- **DB helper** exposes read-only `fetch(sql, params)`; vector compared with `<=>` (cosine), `fts` ranked with `ts_rank`.

## Risks / Trade-offs

- Freezing contracts early risks a late change forcing edits here; mitigated by keeping models minimal and additive.
- `psycopg` v3 (`psycopg[binary]`) chosen over `asyncpg` to serve both sync evals and the async API with one driver + the `pgvector` adapter.
