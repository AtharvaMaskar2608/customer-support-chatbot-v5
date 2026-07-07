## 1. App & session

- [ ] 1.1 `backend/main.py`: FastAPI app, CORS, `init_tracing(settings)` on startup.
- [ ] 1.2 `backend/api/sessions.py`: in-memory session store; `create_session(userId, mobileNo, sessionToken, clientCode?)` trimming all inputs → `session_id`.
- [ ] 1.3 `POST /session` route returning `{session_id}`.

## 2. Chat SSE

- [ ] 2.1 `backend/api/sse.py`: serialize `SSEEvent` → SSE frames (event name = type).
- [ ] 2.2 `POST /chat` route: `EventSourceResponse` over `agent_reply_stream(session, messages)`; terminal `error` frame on failure.

## 3. Report submit → resume

- [ ] 3.1 `POST /report` route: dispatch `report_type` to `cml_report`/`contract_note` with structured `params` + session → `ReportResult`; stream `resume_report_stream(...)` back as SSE.

## 4. Done condition

- [ ] 4.1 `openspec validate api-sse-session --strict` passes.
- [ ] 4.2 Test: `POST /session` trims inputs; `POST /chat` yields an SSE sequence ending in `done` (or `error`); `POST /report` runs the tool and streams a summary. `pytest backend/api` (httpx ASGI client).
