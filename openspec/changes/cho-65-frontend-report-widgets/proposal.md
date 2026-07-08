# Proposal: frontend-report-widgets

## Why

The report flow becomes fully widget-driven: on a report intent the frontend chains a **card picker** (e.g. Normal vs MTF ledger) and a **date-range picker**, posts the choices to `POST /report`, and renders the returned table/link **directly — the LLM never touches parameters or results**. The login page must also collect everything identity-related up front (phone, user id, client code, FinX SessionId, legacy JWT), and the stuck "Generating answer…" indicator (Linear **CHO-61**) gets its frontend fix in the same file.

## What Changes

- **BREAKING** Replace the legacy `FIELD_META` form widget (free-form `client_id`/`mobile_no` inputs, `DD-MM-YYYY` conversion) and the report resume bridge (`handleReportPause`'s client-side `tool_use` synthesis + SSE resume) — none of it survives.
- New **card-select widget**: renders `CardStep.options` as tappable decision cards (e.g. "Normal Ledger" / "MTF Ledger"); selection is deterministic, no model round-trip.
- New **date-range widget**: two native date inputs (`YYYY-MM-DD`, no defaults per product decision), validated `from ≤ to`.
- **Step chaining**: a `report_request` frame's `steps` render in order (cards → dates), accumulate `params`, then POST `/report`; a "Never mind" cancel path remains.
- New **result renderers**: generic table (from `ReportRenderPayload.columns/rows`, horizontally scrollable), download-link card (tax PDF), and empty/error notice. After rendering, append a plain-text marker turn (e.g. `[MTF Ledger report displayed for 2026-04-01 → 2026-07-15]`) to durable history for conversational continuity.
- **Login page**: add required **FinX Session ID** field and make **Client code required**; keep phone, user id, and the legacy JWT session-token field (user decision: everything collected at the start). All inputs trimmed; sent as `{userId, mobileNo, sessionToken, finxSessionId, clientCode}`.
- **CHO-61 fix**: the assistant-message progress indicator ("Generating answer…") SHALL clear on *every* terminal condition — `done`, `error`, `report_request`-terminated turns, and unexpected stream close.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `frontend-poc`: login collects full identity; report widgets become chained card/date-range steps; results render directly from `ReportRenderPayload`; progress indicator always clears.

## Impact

- **Files touched (exclusively assigned to this change):** `frontend/index.html`, `frontend/js/app.js`, `frontend/css/` (Tailwind rebuild), `frontend/tailwind.config.js` if new utilities are needed.
- **Depends on:** `finx-reports-contracts` (A) in `main` for the `report_request.steps` and `ReportRenderPayload` shapes. Runs **in parallel with** `finx-middleware-tools` (B) — zero file overlap; both build against A's contracts. End-to-end verification of C requires B's `/report` to exist (or a stubbed response) — QA task notes this.
- **Linear:** fixes frontend half of CHO-61.
- **Done condition:** manual QA via the `/browse` daemon — login with all five fields; ledger flow shows cards → dates → table; tax flow shows year cards → download link; empty/error notices render; "Generating answer…" clears on every path. No JS console errors.
