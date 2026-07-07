## ADDED Requirements

### Requirement: Login with trimmed inputs

The frontend SHALL present a login page collecting phone number, user id, and session token, trim all inputs, call `POST /session`, and retain the returned `session_id`.

#### Scenario: Tester logs in

- **WHEN** the tester submits phone, user id, and session token (with stray whitespace)
- **THEN** the values are trimmed, `POST /session` is called, and the `session_id` is stored for subsequent calls

### Requirement: Streaming chat with citations and cost

The frontend SHALL open an SSE stream to `POST /chat` and render `status` steps, streamed `token`s, a hoverable `citations` card at message end, per-message cost + latency, and a cumulative INR cost card (web view).

#### Scenario: A retrieval answer renders fully

- **WHEN** the agent answers an FAQ using RAG
- **THEN** the UI shows status step(s), streams the answer tokens, renders a hoverable citation card, updates the cumulative INR card, and shows that message's cost + latency

### Requirement: Structured report widgets

On a `report_request` frame the frontend SHALL render the matching widget — a date-picker for the contract date (emitting `DD-MM-YYYY`) plus `client_id`/`mobile_no` fields prefilled from the session — and submit the structured params via `POST /report`, then resume rendering the stream. Report params SHALL NOT be entered as free text routed through the model.

#### Scenario: Contract-note date collected via date-picker

- **WHEN** the agent emits a `report_request` for a contract note
- **THEN** the UI shows a date-picker (and prefilled mobile/user-id fields), and on submit posts a valid `DD-MM-YYYY` date to `POST /report`, after which the summary streams in
