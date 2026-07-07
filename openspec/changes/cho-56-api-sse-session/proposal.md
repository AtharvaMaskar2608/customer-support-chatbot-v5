## Why

The frontend needs an HTTP surface: a login/session endpoint and a streaming chat endpoint that fronts the agent, plus a report-submit endpoint that feeds widget-collected params back into the conversation.

## What Changes

- Add a FastAPI app (`backend/main.py`) with CORS for the POC frontend.
- `POST /session`: accept `{userId, mobileNo, sessionToken}` (and optional `clientCode`), **trim/strip all inputs**, create an in-memory `Session`, return `{session_id}`.
- `POST /chat`: accept `{session_id, messages}`, open an SSE (`text/event-stream`) stream from `agent_reply_stream`, forwarding `status` → `token` → `citations` → `usage` → (`report_request`) → `done`; emit an `error` frame on failure.
- `POST /report`: accept `{session_id, report_type, params}` from the widget submission, run the matching P2 report tool (`cml_report`/`contract_note`) with the **structured** params + the session, then resume the paused turn via `resume_report_stream`, streaming the summary back over SSE.

Follows `docs/project_context.md` §3.1 (login) and §3.5/§3.1 (streaming).

## Capabilities

### New Capabilities
- `session-auth`: in-memory session creation from trimmed login inputs (phone + user id + session token).
- `chat-sse-api`: SSE chat endpoint over the agent stream, plus the `/report` widget-submit → resume path.

## Impact

- New: `backend/main.py`, `backend/api/routes.py`, `backend/api/sse.py`, `backend/api/sessions.py`.
- Imports foundations (`Session`, `SSEEvent`, `Settings`), P4 (`agent_reply_stream`, `resume_report_stream`), P2 (report tools). Calls `init_tracing(settings)` at startup.
- `backend/main.py` is owned solely by this change. Consumed by the frontend (P8).
