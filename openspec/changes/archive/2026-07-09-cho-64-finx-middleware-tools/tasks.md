# Tasks: finx-middleware-tools

**Done condition:** `uv run pytest backend/tests` green — mocked-httpx tests pin exact request bodies/headers for all five clients; loop tests prove `report_request → usage → done`; `/report` tests prove no Anthropic call. Grep confirms no references to `cml_report`, `contract_note`, `resume_report_stream`, `FINX_CML_BASE_URL`, `FINX_CONTRACT_NOTE_BASE_URL` remain.
**Test command:** `uv run pytest backend/tests`
**Prerequisite:** `finx-reports-contracts` merged to `main`.

## 1. Middleware clients (backend/tools/finx.py — rewrite)

- [x] 1.1 Add `_middleware_post(session, path, body, *, with_from_header=False)` with `authorization`/`origin` (+optional `from:`) headers, timeout, and never-raise error containment
- [x] 1.2 Add `YYYY-MM-DD` date validation helper (local rejection, no network call)
- [x] 1.3 Implement `get_ledger` (LoginId "JIFFY", Group ∈ Group1|MTF) and envelope `Status`/`Reason` mapping
- [x] 1.4 Implement `get_global_pnl` (UserId=ClientId, With_Exp=1, Group ∈ Cash|Derv|Comm)
- [x] 1.5 Implement `get_detailed_pnl` (UserId="neuron", `from:` header, Group ∈ Group1|Group23)
- [x] 1.6 Implement `get_contract_notes` (snake_case body, `from:` header, StatusCode mapping incl. 204→empty success)
- [x] 1.7 Implement `get_tax_report` (FinYear ∈ three supported years, RequestFor=2, FileFormat=1; data carries the URL)
- [x] 1.8 Delete `cml_report`, `contract_note`, and their helpers

## 2. Tool schemas + widget registry

- [x] 2.1 Replace `backend/tools/schemas.py` contents with five intent-only tool definitions (empty input schema; descriptions state params come from widgets)
- [x] 2.2 In `backend/agent/tools.py`: register the five tools in `TOOLS`; replace `REPORT_TOOLS` with `REPORT_WIDGETS` registry (tool name → report_type + `WidgetStep` chain per design D3, no date defaults)

## 3. Agent loop (backend/agent/loop.py) + prompt

- [x] 3.1 On report tool call: emit `report_request` (registry `report_type` + `steps` + `tool_use_id`), then `usage`, then `done` — terminal on every path (CHO-61 backend fix)
- [x] 3.2 Delete `resume_report_stream` and its imports/tests
- [x] 3.3 Update `backend/agent/prompt.py`: system prompt names the five report tools and states results render in the UI (the assistant must not promise a summary or supply parameters)
- [x] 3.4 Populate `AgentReply.tools_called` (and the non-streaming `agent_reply`) with the tool names invoked in the turn — `rag_search`, report tool name, `ask_clarifying_question` — so evals assert intent routing without inferring from citations

## 4. API (backend/api/routes.py)

- [x] 4.1 Rework `POST /report`: plain JSON, `{session_id, report_type, params}` → registry param validation (422 on unknown/missing keys) → client dispatch → `ReportRenderPayload` response; no SSE, no Anthropic call
- [x] 4.2 Implement render shaping per design D5 (fixed ledger columns; dynamic columns for PNL/contract notes; `link` for tax; `empty`/`error` mapping); keep tax URL out of prompts and traces
- [x] 4.3 `POST /session`: accept + trim `finxSessionId`, require non-empty `finxSessionId` and `clientCode`; thread into `Session`

## 5. Legacy cleanup (files landed by finx-reports-contracts — sequenced after A merges)

- [x] 5.1 `backend/contracts/events.py`: drop `cml`/`contract_note` from `report_type` and remove the `fields` list
- [x] 5.2 `backend/config/settings.py`: remove `finx_cml_base_url` / `finx_contract_note_base_url`; update `.env.example` if present

## 6. Tests

- [x] 6.1 Mocked-httpx tests per client: exact endpoint, headers (incl. `from:` where required), body fields, and in-band error/204/invalid-date mappings
- [x] 6.2 Loop tests: `ledger` call → `report_request(steps)` → `usage` → `done` ordering; no resume path exists
- [x] 6.3 `/report` endpoint tests: happy table/link/empty/error payloads; 422 on unknown params; assert zero Anthropic client invocations
- [x] 6.4 `/session` tests: required `finxSessionId`/`clientCode`; trimming
- [x] 6.5 Full suite green: `uv run pytest backend` (73 passed; evals excluded — require live API keys)

## 7. Follow-up flag (not blocking)

- [ ] 7.1 Re-capture the MTF ledger request with the MTF tab active and confirm `Group:"MTF"` against the live API; correct the registry value if it differs
      _Deferred (non-blocking) at archive on 2026-07-09 — requires a live FinX capture. Carried forward as a follow-up; the `Group:"MTF"` registry value remains as-implemented until confirmed._
