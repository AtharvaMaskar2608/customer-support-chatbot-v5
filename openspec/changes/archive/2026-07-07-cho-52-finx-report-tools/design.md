## Context

Two FinX MIS endpoints on **different hosts** (`finxomne...` for CML, `finx...` for Contract Note), both authenticated with the per-session JWT the tester enters on the login form. Contracts confirmed by the project owner (`docs/project_context.md` §4 for the Contract Note; CML endpoint/body provided directly).

Decision (confirmed): **all report parameters are collected via structured frontend widgets** (date-picker for `contractDate`, fields for `client_id`/`mobile_no`, mobile/user-id prefillable from session). The agent decides *when* a report is relevant; it never fabricates or free-text-parses parameter values.

## Goals / Non-Goals

**Goals:**
- Two thin, well-typed clients (`cml_report`, `contract_note`) returning `ReportResult` from structured params.
- Anthropic tool schemas that let the model **signal intent only** — no data params in the model-visible schema.
- Total isolation of upstream failures from the agent loop.

**Non-Goals:**
- No other Reports APIs (Phase 1 = CML + Contract Note only).
- No token generation/refresh — the JWT is supplied per session by the login form.
- No LLM free-text date/param parsing — params come from widgets.

## Decisions

- **Two base URLs** as separate settings; never concatenate a single base.
- **Header block** `{"Authorization": session.session_token, "authType": "jwt", "source": "FINX_WEB"}` shared by both.
- **Non-raising contract:** on any exception or non-2xx, return `ReportResult(ok=False, error=<short reason>)`; on success `ReportResult(ok=True, data=<parsed json>)`.
- **Client functions take structured params** (`client_id`; `mobile_no`, `contract_date`) that originate from the frontend widget submission (via the API layer), not from the model.
- **Model-visible tool schemas are intent-only:** `CML_REPORT_TOOL` and `CONTRACT_NOTE_TOOL` expose **no data properties**. A model tool call signals "a report is relevant"; the agent loop turns it into a `report_request` SSE frame and the frontend collects the params.
- **Defensive validation** still applies server-side: `contract_date` is checked against `DD-MM-YYYY` before the call even though the widget guarantees the format.

## Risks / Trade-offs

- Upstream response schema is not fully documented; we return parsed JSON as opaque `data` and let the agent summarize, rather than over-modeling it now.
- JWTs expire; an expired token surfaces as `ok=False` with the upstream message, which the agent relays as "please re-enter your session token."
- The intent-only-schema approach means the actual FinX call is executed by the API layer (`POST /report`) after widget submit, then fed back into the agent turn — a small pause/resume in the loop (owned by `agentic-loop`/`api-sse-session`), not by this change.
