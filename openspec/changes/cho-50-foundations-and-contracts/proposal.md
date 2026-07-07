## Why

Every other Phase 1 change (RAG, tools, tracing, agent, API, evals, frontend) imports the same configuration, data types, database access, and tracing hooks. If each change defines these independently they will drift and conflict on merge. This change lands the shared foundation in `main` **before any parallel fan-out**, so downstream changes import a frozen contract and never redefine it.

## What Changes

- Add a typed **config loader** that reads all settings from `.env` with fail-fast validation — no hardcoded connection details. Single `DATABASE_URL`. Model string is configurable (`ANTHROPIC_MODEL`, default `claude-sonnet-4-5`).
- Add **frozen Pydantic v2 data contracts** shared across the codebase (`Citation`, `RagChunk`, `RagResult`, `ReportResult`, `Session`, `Usage`, `AgentReply`, `SSEEvent`).
- Add a **read-only database helper** over the pre-loaded `qa_chunks` table (embeddings already loaded — no ingestion/migration).
- Add a **tracing interface** (Protocol + no-op default implementation) so RAG and the agent can be instrumented without depending on the concrete DeepEval implementation (which lands in `tracing-foundation`).
- Own the **root `pyproject.toml`** with the complete Phase 1 dependency set, and `.env.example`. No downstream change modifies root config.

## Capabilities

### New Capabilities
- `project-configuration`: env-driven settings loader with fail-fast validation and no hardcoded connection details.
- `data-contracts`: shared Pydantic v2 models used as the interface between all modules.
- `database-access`: read-only Postgres access helper over `qa_chunks`.
- `tracing-interface`: no-op-safe tracing Protocol imported by RAG and agent; concrete impl provided later by `tracing-foundation`.

## Impact

- New: `backend/config/`, `backend/contracts/`, `backend/db/`, `backend/tracing/interface.py`, `pyproject.toml`, `.env.example`.
- Downstream changes (`rag-hybrid-retrieval`, `finx-report-tools`, `tracing-foundation`, `agentic-loop`, `api-sse-session`, `rag-evals`, `chatbot-multiturn-evals`) import from here and add **zero** root dependencies.
- Dependencies declared here: `anthropic`, `openai`, `psycopg[binary]`, `pgvector`, `httpx`, `fastapi`, `uvicorn`, `sse-starlette`, `pydantic`, `pydantic-settings`, `deepeval`, `python-dotenv`.
