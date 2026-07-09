# Tasks: frontend-report-widgets

**Done condition:** `/browse` QA passes the checklist in task 5 with zero console errors.
**Test command:** manual QA via `/browse` (no frontend test framework); backend stub for `/report` until finx-middleware-tools lands.
**Prerequisite:** `finx-reports-contracts` merged to `main` (contract shapes). Runs in parallel with `finx-middleware-tools` — no shared files.

## 1. Login page (frontend/index.html + app.js login handler)

- [x] 1.1 Add required "FinX Session ID" field (`type=password`) and mark client code required; keep phone, user id, legacy JWT fields
- [x] 1.2 Trim all five values; send `{userId, mobileNo, sessionToken, finxSessionId, clientCode}` to `POST /session`; inline required-field validation

## 2. Widget step renderer (frontend/js/app.js)

- [x] 2.1 Implement `renderReportSteps(steps, reportType)`: sequential step chaining, accumulated params, "Never mind" cancel on any step, unknown-`kind` guard
- [x] 2.2 Card-select step: tappable cards from `options[].label`, resolving `param` → opaque `value`
- [x] 2.3 Date-range step: two native date inputs, no defaults, `from ≤ to` validation, submit gating
- [x] 2.4 Delete legacy `FIELD_META`, `REPORT_TITLES` form flow, `toDdMmYyyy`, and `handleReportPause`'s `tool_use` synthesis + SSE resume bridge

## 3. Result rendering

- [x] 3.1 `POST /report` via fetch → JSON `ReportRenderPayload`; render by `kind`
- [x] 3.2 Table renderer: `columns`/`rows`, `overflow-x-auto`, numeric right-align, row cap with "showing N of M"
- [x] 3.3 Link renderer: download card, new tab, `rel="noopener"`, URL never copied into history text
- [x] 3.4 Empty/error notices with upstream `message`
- [x] 3.5 Append plain-text `[<title> displayed]` marker turn to durable history after rendering

## 4. CHO-61 — terminal handling

- [x] 4.1 Centralize `finalizeMessage` in one stream-teardown site covering `done`, `error`, `report_request` turn end, and stream close without a terminal frame
- [x] 4.2 Verify no path leaves "Generating answer…" showing (includes the report flow and a killed connection)

## 5. QA (via /browse)

- [x] 5.1 Stub `/report` responses (table/link/empty/error) and walk: login (5 fields, required validation) → ledger cards → dates → table; tax → year cards → link card; cancel path
- [x] 5.2 CHO-61 checks: normal answer, report turn, and forced stream drop all clear the indicator
- [ ] 5.3 After finx-middleware-tools lands: joint end-to-end pass against the real backend; Tailwind rebuild committed
