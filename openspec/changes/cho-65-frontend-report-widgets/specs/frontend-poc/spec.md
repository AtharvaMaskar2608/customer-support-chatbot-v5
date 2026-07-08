# frontend-poc — delta for frontend-report-widgets

## MODIFIED Requirements

### Requirement: Login with trimmed inputs

The frontend SHALL present a login page collecting phone number, user id, legacy session token (JWT), **FinX Session ID**, and **client code** — the latter two required — trim all inputs, call `POST /session` with `{userId, mobileNo, sessionToken, finxSessionId, clientCode}`, and retain the returned `session_id`. All identity needed by any report SHALL be collected here; report widgets never re-ask for identity.

#### Scenario: Tester logs in with full identity

- **WHEN** the tester submits all five fields (with stray whitespace)
- **THEN** the values are trimmed, `POST /session` is called with the five keys, and the `session_id` is stored for subsequent calls

#### Scenario: Missing required identity blocks submission

- **WHEN** the FinX Session ID or client code field is empty
- **THEN** the form blocks submission with an inline required-field message and no request is sent

### Requirement: Structured report widgets

On a `report_request` frame the frontend SHALL render the frame's `steps` in order as chained widgets: a `cards` step as tappable decision cards (one per `option`, showing `label`, resolving the step's `param` to the opaque `value`), and a `date_range` step as two native date inputs emitting `YYYY-MM-DD` with **no default values** and `from ≤ to` validation. Accumulated params are submitted via `POST /report` as `{session_id, report_type, params}`. Report params SHALL NOT be entered as free text routed through the model, and identity fields never appear in widgets. A cancel ("Never mind") action on any step SHALL abandon the whole chain. An unrecognized step `kind` SHALL render an error notice and cancel.

#### Scenario: Ledger flow chains cards then dates

- **WHEN** a `report_request` for `ledger` arrives with the group card step and date-range step
- **THEN** the UI shows "Normal Ledger" / "MTF Ledger" cards; after a tap it shows the date-range picker; on submit it posts `{group:"MTF", from_date:"2026-04-01", to_date:"2026-07-15"}` — with no model involvement

#### Scenario: Tax report is cards-only

- **WHEN** a `report_request` for `tax_report` arrives with only a FinYear card step
- **THEN** tapping a year card immediately submits `{fin_year:"2025-2026"}` with no date step

## ADDED Requirements

### Requirement: Report results render directly from the payload

The frontend SHALL render the `POST /report` JSON `ReportRenderPayload` without any model round-trip: `table` as a horizontally scrollable table built from `columns`/`rows` (row-capped with a "showing N of M" note for large results); `link` as a download card opening the URL in a new tab (`rel="noopener"`), never echoing the URL into chat history text; `empty`/`error` as an informational notice showing `message`. After rendering, the frontend SHALL append a plain-text marker turn (e.g. `[MTF Ledger report displayed]`) to durable history for conversational continuity.

#### Scenario: Ledger table renders and history gets a marker

- **WHEN** `/report` returns `kind="table"` with ledger columns and rows
- **THEN** the table renders in the chat, and the durable history gains a `[<title> displayed]` marker turn instead of raw report data

#### Scenario: Tax PDF renders as a download card

- **WHEN** `/report` returns `kind="link"` with a PDF URL
- **THEN** a download card renders with the report title; the URL appears only in the anchor, not in history or any model-bound text

### Requirement: Progress indicator always clears

The frontend SHALL clear the assistant progress indicator ("Generating answer…") and finalize the message on every terminal condition: `done`, `error`, a `report_request`-terminated turn, and an unexpected stream close without a terminal frame. Terminal handling SHALL be centralized so no stream path can bypass it.

#### Scenario: Indicator clears after a normal answer

- **WHEN** a turn completes with `done`
- **THEN** the "Generating answer…" indicator is removed and the message finalizes (CHO-61)

#### Scenario: Indicator clears when the stream drops

- **WHEN** the SSE connection closes without a `done` or `error` frame
- **THEN** the indicator still clears and the message is marked failed rather than spinning forever
