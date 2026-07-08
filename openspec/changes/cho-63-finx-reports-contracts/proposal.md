# Proposal: finx-reports-contracts

## Why

The chatbot's report tooling is being replaced wholesale: the two legacy FinX tools (CML, old contract note) give way to five FinX middleware reports (Ledger, Global PNL, Detailed PNL, Contract Notes, Tax Report), each parameterized by deterministic frontend widgets (variant cards + date range) with **no LLM involvement** between intent and rendered result. Per our parallel-workflow rules, the shared contracts every downstream change builds against must land in `main` before fan-out — this change is that contract landing.

## What Changes

- Extend `ReportRequestEvent` with a declarative `steps` widget spec (`cards` and `date_range` step kinds) so the frontend can chain widgets without model involvement; `report_type` gains the five middleware values (`ledger`, `global_pnl`, `detailed_pnl`, `contract_notes`, `tax_report`). Legacy values (`cml`, `contract_note`) and the flat `fields` list are **retained temporarily** so this change is purely additive; `finx-middleware-tools` removes them.
- Add `ReportRenderPayload` contract (`kind: table | link | empty | error`) — the JSON shape `POST /report` will return so the frontend renders report results directly, bypassing the LLM.
- Add `Session.finx_session_id` (the FinX middleware SessionId, distinct from the legacy JWT `session_token`, which stays per user decision).
- Add `AgentReply.tools_called: tuple[str, ...] = ()` (additive) so a completed turn records which tools it invoked — `rag_search`, a report tool name, or `ask_clarifying_question`. The agentic evals (D) assert on this for intent routing (transactional report vs RAG explanation); today `AgentReply` cannot distinguish a report-intent turn from a plain answer. B populates it; the field is `()` until then.
- Add `Settings.finx_middleware_base_url` (`FINX_MIDDLEWARE_BASE_URL`, default `https://finx.choiceindia.com`). Legacy `FINX_CML_BASE_URL` / `FINX_CONTRACT_NOTE_BASE_URL` stay until `finx-middleware-tools` deletes their consumers.
- **No behavior changes** — this change only adds contract shapes; all consumers are wired in the follow-up changes.

## Capabilities

### New Capabilities

_None — this change extends existing contract capabilities._

### Modified Capabilities

- `data-contracts`: `ReportRequestEvent` gains `steps` + expanded `report_type` union; new `ReportRenderPayload` model; `Session` gains `finx_session_id`; `AgentReply` gains `tools_called`.
- `project-configuration`: new `finx_middleware_base_url` setting.

## Impact

- **Files touched (exclusively assigned to this change):** `backend/contracts/models.py`, `backend/contracts/events.py`, `backend/config/settings.py`, plus their unit tests under `backend/tests/`.
- **Downstream dependents:** `finx-middleware-tools` (B), `frontend-report-widgets` (C), `report-intent-evals` (D) all import these shapes; none may start until this lands in `main`.
- **Root config note:** `settings.py` is root-adjacent config; this change is the one explicitly assigned to touch it. No lockfile or migration changes.
- **Done condition:** `uv run pytest backend/tests` passes; models importable with old constructors unchanged (additive-only verified by existing tests staying green).
