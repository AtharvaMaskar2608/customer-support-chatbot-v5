## ADDED Requirements

### Requirement: Streaming chat endpoint

The system SHALL provide `POST /chat` accepting `{session_id, messages}` and returning an SSE (`text/event-stream`) response that forwards the agent's `SSEEvent`s (`status`, `token`, `citations`, `usage`, `report_request`, `done`) each as one SSE frame, and emits a terminal `error` frame on failure rather than dropping the connection.

#### Scenario: Chat streams to completion

- **WHEN** `POST /chat` runs a normal turn
- **THEN** the client receives `status`, then `token` frames, then `usage` (with `cumulative_cost_inr`), then `done`

#### Scenario: Failure yields an error frame

- **WHEN** the agent stream raises mid-turn
- **THEN** the response ends with an `error` SSE frame

### Requirement: Report widget submit resumes the turn

The system SHALL provide `POST /report` accepting `{session_id, report_type, params, tool_use_id}`, running the matching report tool (`cml_report` or `contract_note`) with the structured `params` and the session, then streaming `resume_report_stream(...)` back over SSE to continue the paused turn.

#### Scenario: Widget submission runs the report and resumes

- **WHEN** the frontend submits `POST /report` with widget-collected params after a `report_request`
- **THEN** the server runs the report tool, feeds the `ReportResult` back into the agent, and streams the factual summary to `done`
