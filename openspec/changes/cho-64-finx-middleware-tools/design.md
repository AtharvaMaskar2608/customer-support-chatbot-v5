# Design: finx-middleware-tools

## Context

`backend/tools/finx.py` currently holds two clients (CML, contract note) on two hosts with JWT auth. The new suite lives on one middleware host (`finx.choiceindia.com`) with SessionId auth, in-band errors (HTTP 200 always), and two body dialects: PascalCase `/api/middleware/*` (SessionId repeated in body) and snake_case `/middleware-go/*` (header-only auth). The agent loop pauses on report tools and resumes via `resume_report_stream`; that resume path dies because results now render as widgets without the LLM.

## Goals / Non-Goals

**Goals:**
- Five never-raising middleware clients with correct per-endpoint identity injection.
- Deterministic intent → widget → result pipeline with zero model-supplied parameters and zero post-result model calls.
- Turn always ends with a terminal SSE event (CHO-61 backend fix).

**Non-Goals:**
- Frontend rendering (change C). Eval coverage (change D). MTF request re-capture (Group `"MTF"` per product decision; doc's verification flag noted below). No persistence of report data.

## Decisions

### D1 — Client functions and API structure (contracts)

All: `(session: Session, ...) -> ReportResult`, `POST`, JSON, header `authorization: session.finx_session_id`, `origin: https://finx.choiceindia.com`; never raise. `_FROM_HEADER = "Web_finx.choiceindia.com_V_4.6.0.4"` is a module constant sent where noted.

| Function | Endpoint (on `finx_middleware_base_url`) | Body | Notes |
|---|---|---|---|
| `get_ledger(session, group, from_date, to_date)` | `/api/middleware/GetLedgerDetails` | `{LoginId:"JIFFY", ClientId, Group, FromDate, ToDate, SessionId}` | `group ∈ {"Group1","MTF"}` (Normal / MTF) |
| `get_global_pnl(session, group, from_date, to_date)` | `/api/middleware/GetGlobalPNLNew` | `{UserId:ClientId, ClientId, Group, FromDate, ToDate, With_Exp:1, SessionId}` | `group ∈ {"Cash","Derv","Comm"}` |
| `get_detailed_pnl(session, group, from_date, to_date)` | `/api/middleware/GetDetailedPNL` | `{UserId:"neuron", ClientId, Group, FromDate, ToDate, SessionId}` | `group ∈ {"Group1","Group23"}`; sends `from:` header |
| `get_contract_notes(session, from_date, to_date)` | `/middleware-go/report/contract` | `{client_id, from_date, to_date}` | snake_case; header-only auth; sends `from:` header; body `StatusCode` semantics |
| `get_tax_report(session, fin_year)` | `/api/middleware/GetTaxReportPDF` | `{ClientId, FinYear, RequestFor:2, FileFormat:1, SessionId}` | `fin_year ∈ {"2024-2025","2025-2026","2026-2027"}`; `Response` is a URL string |

`ClientId = session.client_code`; dates are `YYYY-MM-DD` (validated by regex before any network call — invalid → `ReportResult(ok=False)` locally). In-band mapping: envelope `Status != "Success"` → `ok=False, error=Reason`; Go `StatusCode == 204` → `ok=True` with empty data (a real "no rows", not an error); other non-200 `StatusCode` → `ok=False, error=Message`. Shared plumbing: `_middleware_post(session, path, body, *, with_from_header=False)`.

### D2 — Intent-only tool schemas × 5

Same pattern as today: `input_schema = {"type":"object","properties":{},"additionalProperties":false}` with descriptions steering intent ("Call when the user wants their ledger / MTF ledger statement; variant and dates are collected by a widget — do NOT supply parameters"). One tool per report family (`ledger`, `global_pnl`, `detailed_pnl`, `contract_notes`, `tax_report`) — the *variant* (MTF vs Normal, segment, FinYear) is a card the user picks, never a model argument. Alternative — separate `ledger` and `mtf_ledger` tools — rejected: the user's "Ledger → suggest MTF or Normal cards" flow puts variant choice in the widget by design.

### D3 — Widget registry (in `backend/agent/tools.py`)

`REPORT_WIDGETS: dict[str, ReportWidgetSpec]` maps tool name → `(report_type, steps)` using contract types from A:

- `ledger` → cards(`group`: Normal Ledger=`Group1`, MTF Ledger=`MTF`) + date_range
- `global_pnl` → cards(`group`: Equity=`Cash`, Derivatives=`Derv`, Commodity=`Comm`) + date_range
- `detailed_pnl` → cards(`group`: Standard=`Group1`, Commodity=`Group23`) + date_range
- `contract_notes` → date_range only
- `tax_report` → cards(`fin_year`: the three supported years); no dates

No date defaults (product decision): `DateRangeStep` carries param names only.

### D4 — Report pause is terminal; resume machinery deleted

Loop behavior on a report tool call: emit `StatusEvent`, `ReportRequestEvent(report_type, steps, tool_use_id)`, then `UsageEvent` (tokens spent this turn) and `DoneEvent`. The pending `tool_use` block is never persisted and never gets a `tool_result` — the turn's server-side Anthropic history is discarded as usual. `tool_use_id` stays on the event purely for tracing correlation. `resume_report_stream` is deleted. This closes CHO-61's backend gap: every `/chat` stream now ends in `done` or `error` on all paths.

### D5 — `POST /report` returns `ReportRenderPayload` JSON (no SSE, no model)

`ReportExecuteRequest {session_id, report_type, params: dict}` → validate session, validate `params` against the registry's step params (reject unknown/missing keys — widget values are the only accepted source), dispatch to the client, shape the result:

- **Ledger** → `kind="table"` with a fixed column map (`trd_Date`→Date, `voucher`→Voucher, `Narration`→Description, `Debit`, `Credit`, `settlement_No`→Settlement) — documented schema.
- **Global/Detailed PNL, Contract notes** → success schemas are flagged "pending capture" in the docs → derive `columns` dynamically from the first row's keys (tables stay generic); revisit with fixed maps once captured.
- **Tax report** → `kind="link"` with the PDF URL. The URL is unauthenticated once generated — it goes only into this payload, never into any model prompt or trace body.
- `ok=True` + no rows / Go 204 → `kind="empty"` with the upstream message ("Data not found."); `ok=False` → `kind="error"` with a client-safe message.

Conversation continuity is the frontend's job (C): it appends a plain-text marker turn (e.g. "[Ledger report displayed]") to its durable history so later turns have context without tool-block synthesis.

### D6 — Legacy cleanup rides in this change

Removing `cml`/`contract_note` literals + `fields` from `contracts/events.py` and the two legacy URL settings happens here, in the same commit that deletes their last consumers. These files belong to change A, so B is hard-sequenced after A merges (stated in the parallelization plan).

## Risks / Trade-offs

- [MTF `Group:"MTF"` is unverified against the live API — docs captured an identical request to Normal] → product decision to ship it; clients surface upstream `Reason` verbatim so a wrong group value fails loudly; re-capture task noted in tasks.
- [PNL/contract-note success schemas unknown] → dynamic column derivation keeps rendering functional for any row shape; fixed maps are a later additive tweak.
- [Two body dialects on one host] → isolated in `_middleware_post` + per-client builders; tests pin exact bodies per the docs.
- [Model may mention a report it can no longer summarize] → system prompt (`prompt.py`) updated: after signaling a report tool, the report renders in the UI; the assistant should not promise a summary.
