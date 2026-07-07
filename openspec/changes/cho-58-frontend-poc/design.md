## Context

Internal QA POC. The login is deliberately simple (phone + user id + session token) — internal validation only. The frontend is the authoritative source of report params via structured widgets, so the LLM never fabricates them.

## Goals / Non-Goals

**Goals:**
- Fast, dependency-light static UI that faithfully renders the SSE event stream.
- Clear cost/latency transparency (per-message + cumulative INR).
- Structured report widgets (date-picker) that guarantee valid params.

**Non-Goals:**
- No production auth, no framework/build pipeline requirement.
- No client-side business logic beyond rendering the stream and collecting widget inputs.

## Decisions

- **Transport:** use `fetch` + a streaming reader (or `EventSource`-style parsing) to consume `text/event-stream`; dispatch on the SSE event name (`status|token|citations|usage|report_request|done|error`).
- **Citations:** collected from the `citations` frame, rendered as a hoverable card anchored at the message end.
- **Cost card:** top-left, web-only; updated from each `usage` frame's `cumulative_cost_inr`; per-message cost+latency shown beneath the message.
- **Report widget:** `report_request` frame → modal/inline widget with a native date-picker for `contract_date` (emits `DD-MM-YYYY`) and inputs for `client_id`/`mobile_no` prefilled from the session; submit `POST /report {session_id, report_type, params, tool_use_id}` and resume rendering the stream.
- **State:** keep `session_id`, the running `messages`, and any pending `tool_use_id` in memory to bridge the widget interaction.
- **Styling:** Tailwind prebuilt to a committed static `css/tailwind.css` (`frontend/tailwind.config.js`; rebuild: `npx tailwindcss@3 -c tailwind.config.js -o css/tailwind.css --minify`). Dark liquid-glass palette (deep indigo-black surfaces, electric-blue/cyan gradient accents), mobile-first breakpoints.

## Risks / Trade-offs

- Consuming SSE via `fetch` streams requires manual frame parsing; a small parser keeps it dependency-free.
- Prefilling `mobile_no`/`client_id` from session assumes the login captured them; if absent, the widget shows empty editable fields.
