# Proposal: finx-middleware-tools

## Why

The two legacy report tools (CML, old contract note) are being killed and replaced by five FinX middleware reports (per `docs/finx_api_reports_documentation.md`): Ledger (Normal/MTF), Global PNL (Equity/Derivatives/Commodity), Detailed PNL (Standard/Commodity), Contract Notes, and Tax Report. Report results now render **directly as frontend widgets, bypassing the LLM** (locked decision), which also removes the resume machinery and fixes the backend half of Linear **CHO-61** (the report-pause path ends a turn without a terminal event, leaving "Generating answer…" stuck).

## What Changes

- **BREAKING** Delete `cml_report` / `contract_note` clients, their tool schemas, the `resume_report_stream` loop entrypoint, and the legacy `cml`/`contract_note` report types + `fields` list from `ReportRequestEvent` (landed as deprecated by `finx-reports-contracts`), plus legacy `FINX_CML_BASE_URL`/`FINX_CONTRACT_NOTE_BASE_URL` settings.
- New `httpx` clients for the five middleware reports (never raise; in-band `Status`/`StatusCode` error mapping), authorized by `Session.finx_session_id`.
- Five intent-only Anthropic tool schemas (empty input schema — model signals intent, never parameters).
- Report widget registry mapping each tool to its `report_type` + `WidgetStep` chain (variant cards, date range, FinYear cards).
- Agent loop: a report tool call emits `report_request` (with `steps`) followed by `usage` and `done` — the turn ends; no resume. Fixes CHO-61's missing-terminal-event path.
- `POST /report` becomes a plain JSON endpoint: runs the mapped client with widget params + session identity, returns a `ReportRenderPayload` (table/link/empty/error). No model call.
- `POST /session` additionally accepts required `finxSessionId` and requires non-empty `clientCode` (both trimmed).

## Capabilities

### New Capabilities

_None — all changes rework existing capabilities._

### Modified Capabilities

- `finx-report-tools`: legacy CML/contract-note requirements removed; five middleware clients, intent-only schemas, widget registry, and render shaping added.
- `agentic-loop`: report pause becomes terminal (no resume); registered tool set changes.
- `chat-sse-api`: `POST /report` returns a `ReportRenderPayload` JSON body instead of resuming an SSE stream; `/chat` emits `done` after `report_request`.
- `session-auth`: `POST /session` collects `finxSessionId` (required) and requires `clientCode`.

## Impact

- **Files touched (exclusively assigned to this change):** `backend/tools/finx.py`, `backend/tools/schemas.py`, `backend/agent/tools.py`, `backend/agent/loop.py`, `backend/agent/prompt.py`, `backend/api/routes.py`, backend tests. Also **post-landing cleanup edits** to `backend/contracts/events.py` and `backend/config/settings.py` — these overlap with `finx-reports-contracts` (A), which is why B is sequenced strictly after A merges to `main`.
- **Depends on:** `finx-reports-contracts` in `main` (imports `WidgetStep`, `ReportRenderPayload`, `Session.finx_session_id`, `finx_middleware_base_url`).
- **Consumed by:** `frontend-report-widgets` (C) via the SSE/JSON contracts only — no shared files, safe to run in parallel. `report-intent-evals` (D) imports `agent_reply` and the new tool names, so D waits for B.
- **Linear:** fixes backend half of CHO-61.
- **Done condition:** `uv run pytest backend/tests` green, including mocked-httpx tests for all five clients and loop tests proving `report_request → usage → done` ordering and that no Anthropic call follows `POST /report`.
