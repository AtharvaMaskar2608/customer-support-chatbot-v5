## 1. Project scaffold & dependencies

- [x] 1.1 Create `pyproject.toml` with the full Phase 1 dependency set and `backend` package.
- [x] 1.2 Create `.env.example` mirroring `.env` keys (no secrets): `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `CONFIDENT_API_KEY`, `FINX_CML_BASE_URL`, `FINX_CONTRACT_NOTE_BASE_URL`, `TRACING_ENABLED`.

## 2. Configuration

- [x] 2.1 `backend/config/settings.py`: `Settings` (pydantic-settings) loading all env vars, fail-fast on missing required.
- [x] 2.2 `get_settings()` cached accessor; no hardcoded connection details anywhere.

## 3. Data contracts

- [x] 3.1 `backend/contracts/models.py`: `Citation`, `RagChunk`, `RagResult`, `ReportResult`, `Session`, `Usage`, `AgentReply`.
- [x] 3.2 `backend/contracts/events.py`: `SSEEvent` discriminated union (`status|token|citations|usage|done|error`).

## 4. Database access

- [x] 4.1 `backend/db/connection.py`: connection factory from `DATABASE_URL` (psycopg v3, `pgvector` adapter registered).
- [x] 4.2 `backend/db/query.py`: read-only `fetch(sql, params) -> list[dict]`.

## 5. Tracing interface

- [x] 5.1 `backend/tracing/interface.py`: `Tracer` Protocol (`observe`, `span`, `trace(thread_id)`, `update_current_span`) + no-op default.

## 6. Done condition

- [x] 6.1 `openspec validate foundations-and-contracts --strict` passes.
- [x] 6.2 Test: `python -c "from backend.config.settings import get_settings; get_settings()"` succeeds with `.env`; `pytest backend/contracts` (model round-trip) green.
