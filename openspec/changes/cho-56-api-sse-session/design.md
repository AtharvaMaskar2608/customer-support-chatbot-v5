## Context

POC-grade auth: the tester enters phone, user id, and session token (JWT) on a login form — acknowledged as internal-validation-only. Report params are collected by frontend widgets and submitted to `/report`, which runs the actual FinX call and resumes the agent turn.

## Goals / Non-Goals

**Goals:**
- Minimal, correct SSE transport over the agent's event stream.
- Trimmed session inputs; session token available for downstream FinX calls.
- A clean widget-submit → run-tool → resume-turn path.

**Non-Goals:**
- No production auth/user management (POC).
- No persistence — sessions and conversation state are in-memory for the POC.
- No agent/tool logic here (imported from P4/P2).

## Decisions

- **`POST /session`:** strip whitespace on `userId`, `mobileNo`, `sessionToken`; store `Session` in an in-memory dict keyed by a generated `session_id`; return `{session_id}`.
- **`POST /chat`:** `sse-starlette` `EventSourceResponse` iterating `agent_reply_stream(session, messages)`; each `SSEEvent` serialized as one SSE frame (event name = frame type). A `report_request` frame tells the client to render the widget.
- **`POST /report`:** look up session; dispatch on `report_type` to `cml_report`/`contract_note` with the structured `params`; get `ReportResult`; stream `resume_report_stream(session, messages, tool_use_id, report_result)` back as SSE. The `tool_use_id` from the earlier `report_request` is passed by the client on submit.
- **Errors:** any exception in a stream becomes a terminal `error` frame, not a dropped connection.
- **CORS:** allow the frontend origin(s) from settings.

## Risks / Trade-offs

- In-memory sessions/state won't survive restart or scale horizontally — acceptable for a single-instance POC; flagged for production.
- SSE + a resume hop means the client must retain `session_id`, `messages`, and the pending `tool_use_id` across the widget interaction.
