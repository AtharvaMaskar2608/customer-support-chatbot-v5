## Why

QA testers need a minimal UI to exercise the agent: log in with their session token, chat with SSE streaming, see citations and cost/latency, and fill report widgets. This is the POC frontend.

## What Changes

- Static **Tailwind** app (dark liquid-glass theme with blue/cyan gradients, mobile-first; Tailwind precompiled to a committed static CSS — no build backend required at runtime).
- **Login page:** phone number + user id + session token inputs (all **trimmed**) → `POST /session`; store `session_id`.
- **Chat view:**
  - Opens SSE to `POST /chat`; renders `status` steps ("Looking up the knowledge base…", "Generating the answer…"), appends streamed `token`s.
  - Renders `citations` as a **hoverable card** at the end of a message.
  - Shows **per-message cost + latency** under each message, and a **cumulative INR cost card** in the top-left (web view).
- **Report widgets:** on a `report_request` frame, render the matching widget (a **date-picker** for the contract date + fields for `client_id`/`mobile_no`, with mobile/user-id **prefilled from session**), then `POST /report` and continue the stream. Report params are never typed as free text through the model.

Follows `docs/project_context.md` §3.1.

## Capabilities

### New Capabilities
- `frontend-poc`: static Tailwind login + streaming chat UI with citations, cost/latency, and structured report widgets.

## Impact

- New: `frontend/index.html`, `frontend/js/*`, `frontend/css/*` (or equivalent single-page static assets).
- Consumes the P5 HTTP/SSE contract (`/session`, `/chat`, `/report`) and the P0 `SSEEvent` frame shapes. No backend imports.
- Can be built against the P5 contract before P5 lands; live E2E requires P5.
