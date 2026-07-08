# Design: frontend-report-widgets

## Context

`frontend/js/app.js` (vanilla JS + Tailwind, no framework/build) currently renders one report widget: a `FIELD_META`-driven form, plus a resume bridge that synthesizes the paused `tool_use` block client-side and re-opens an SSE stream on `/report`. With results now rendered directly (no LLM), the widget layer is rebuilt around the declarative `steps` spec from change A, and `/report` becomes a plain `fetch` → JSON → render.

## Goals / Non-Goals

**Goals:**
- Deterministic intent → cards → dates → table pipeline with zero model involvement.
- All identity collected at login; widgets never re-ask for identity.
- Progress indicator provably clears on every terminal path (CHO-61).

**Non-Goals:**
- No framework adoption, no build-step change, no backend edits, no styling overhaul beyond the new components (the current dark liquid-glass theme holds; Tailwind stays precompiled — rebuild via `npx tailwindcss@3 -c tailwind.config.js -o css/tailwind.css --minify` from `frontend/`).

## Decisions

### D1 — Widget step renderer is a `kind` switch

`renderReportSteps(steps, reportType)` walks `steps` in order, awaiting each step's Promise:

- `cards` → a horizontal card group; each card shows `option.label`; click resolves `{[step.param]: option.value}`. Values are opaque FinX tokens ("MTF", "Cash", "2025-2026") — never interpreted, never edited.
- `date_range` → two native `<input type="date">` (already emit `YYYY-MM-DD` — the old `toDdMmYyyy` converter is deleted), no prefilled values, submit disabled until both set and `from ≤ to`.

Accumulated params → `POST /report {session_id, report_type, params}`. A "Never mind" link on any step cancels the whole chain (mirrors today's cancel path). Unknown `kind` → error notice + cancel (forward-compat guard).

### D2 — Result renderers keyed on `ReportRenderPayload.kind`

- `table` → header row from `columns[].label`, body from `rows[][column.key]`; wrapped in `overflow-x-auto`; numeric-looking cells right-aligned; row cap with "showing N of M" if rows > 200 (a full-FY ledger can be huge).
- `link` → download card with the report title and an anchor (`target="_blank" rel="noopener"`); the URL is sensitive (unauthenticated) — rendered only, never echoed into chat history text.
- `empty` / `error` → informational notice with the upstream `message`.

After rendering, push a plain-text assistant marker into durable history — `[<title> displayed]` — so follow-up turns have context without tool-block synthesis. `handleReportPause`'s synthesis machinery is deleted.

### D3 — Login: five fields, all trimmed, one page

`index.html` adds **FinX Session ID** (required, `type=password`) and marks **Client code** required; phone, user id, and legacy JWT stay. Payload: `{userId, mobileNo, sessionToken, finxSessionId, clientCode}`. Client-side required-validation mirrors the server's non-empty checks so 422s are rare. Rationale: user decision — everything identity-related collected up front; widgets stay parameter-only (variant + dates).

### D4 — CHO-61: centralize terminal handling

One `finalizeMessage(handle)` is invoked from a single stream-teardown site — on `done`, `error`, `report_request` (turn ends there under the new contract), *and* on `EventSource`/fetch-stream close without a terminal frame (network drop). It clears the status line, stops the typing indicator, and flushes usage if present. Root cause today: the report-pause path ends the stream with no terminal frame and the frontend only clears on `done`; B guarantees `done` on all paths, C stops trusting that guarantee.

## Risks / Trade-offs

- [C's E2E path needs B's `/report`] → contracts from A suffice to build; QA uses a stubbed JSON response until B lands, then a joint QA pass (task 5.3).
- [Huge ledger tables in a POC DOM] → row cap + scroll container; no virtualization (POC scope).
- [Dynamic columns for PNL/contract notes (schemas pending)] → the generic table renderer already handles arbitrary columns; nothing to change on capture.
