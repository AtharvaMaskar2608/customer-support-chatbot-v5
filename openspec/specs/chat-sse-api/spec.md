# chat-sse-api Specification

## Purpose
TBD - created by archiving change cho-56-api-sse-session. Update Purpose after archive.
## Requirements
### Requirement: Streaming chat endpoint

The system SHALL provide `POST /chat` accepting `{session_id, messages}` and returning an SSE (`text/event-stream`) response that forwards the agent's `SSEEvent`s (`status`, `token`, `citations`, `usage`, `report_request`, `done`) each as one SSE frame, and emits a terminal `error` frame on failure rather than dropping the connection. **Every** `/chat` stream SHALL end with a terminal frame (`done` or `error`) on all paths, including report-request turns.

#### Scenario: Chat streams to completion

- **WHEN** `POST /chat` runs a normal turn
- **THEN** the client receives `status`, then `token` frames, then `usage` (with `cumulative_cost_inr`), then `done`

#### Scenario: Report-request turn still terminates

- **WHEN** a turn ends in a `report_request`
- **THEN** the stream still closes with `usage` then `done`, so the frontend can clear its progress indicator (CHO-61)

#### Scenario: Failure yields an error frame

- **WHEN** the agent stream raises mid-turn
- **THEN** the response ends with an `error` SSE frame

### Requirement: Report execution endpoint returns a render payload

The system SHALL provide `POST /report` accepting `{session_id, report_type, params}` as a plain JSON endpoint (no SSE): it validates the session, validates `params` against the widget registry's step params for that `report_type` (rejecting missing or unknown keys — widget values are the only accepted parameter source), dispatches to the matching middleware client with session identity injected server-side, and returns a `ReportRenderPayload` JSON body (`table` | `link` | `empty` | `error`). No Anthropic API call is made.

#### Scenario: Widget submission returns a table payload

- **WHEN** the frontend posts `{report_type:"ledger", params:{group:"MTF", from_date:"2026-04-01", to_date:"2026-07-15"}}` with a valid `session_id`
- **THEN** the server calls `get_ledger` with the session and returns `ReportRenderPayload(kind="table", ...)` as JSON

#### Scenario: Unknown params are rejected

- **WHEN** the posted `params` contain a key not defined by the registry steps for that report type (e.g. `client_id`)
- **THEN** the request fails with a 422 and no FinX call is made

#### Scenario: Upstream no-data returns an empty payload

- **WHEN** the middleware answers "Data not found."
- **THEN** the endpoint returns `kind="empty"` with that message and HTTP 200

