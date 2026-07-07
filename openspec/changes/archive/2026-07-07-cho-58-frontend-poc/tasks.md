## 1. Login

- [x] 1.1 `frontend/index.html` + login view: phone, user id, session token inputs; trim all; `POST /session`; store `session_id`.

## 2. Chat + SSE rendering

- [x] 2.1 SSE client: consume `POST /chat` stream, dispatch on event name.
- [x] 2.2 Render `status` steps; append `token`s to the active message.
- [x] 2.3 Render `citations` as a hoverable card at message end.
- [x] 2.4 Cumulative INR cost card (top-left, web); per-message cost + latency from `usage`.

## 3. Report widgets

- [x] 3.1 On `report_request`, render the widget (date-picker for `contract_date` → `DD-MM-YYYY`; `client_id`/`mobile_no` fields prefilled from session).
- [x] 3.2 Submit `POST /report {session_id, report_type, params, tool_use_id}`; resume rendering the stream.

## 4. Styling

- [x] 4.1 Tailwind theme (precompiled static CSS), mobile-first responsive. Restyled per user direction to a dark liquid-glass theme (blue/cyan gradients) via a builder/critic agent loop; critic APPROVED after 2 rounds.

## 5. Done condition

- [x] 5.1 `openspec validate frontend-poc --strict` passes.
- [x] 5.2 Test: against a running backend, a tester can log in, ask an FAQ (see status → tokens → citations → cost), and complete a report via the date-picker widget. Manual QA checklist in the change; automated smoke via the `/browse` skill optional.
