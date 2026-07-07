## Context

The agent must be conversational, grounded, cited, cost-transparent, and compliant. Report params come from frontend widgets (not the model), so report tools are intent-only and the loop pauses to collect params. RAG answers must carry citations.

## Goals / Non-Goals

**Goals:**
- One loop serving both streaming (API) and non-streaming (evals) callers.
- Guardrails that hold after follow-ups and tool use, not just on turn 1.
- Accurate per-message + cumulative INR cost and latency.

**Non-Goals:**
- No HTTP/SSE transport (that is `api-sse-session`).
- No report param collection UI (that is the frontend); the loop only emits `report_request`.
- No answer without citations when RAG was used.

## Decisions

- **Model call:** Messages API, `thinking` disabled, tools = [rag_search, cml_report, contract_note]. Loop until the model returns no tool calls (final answer).
- **System prompt** (`prompt.py`): (1) enumerate tools + when to use each; (2) list in-scope KB categories, built once from `SELECT DISTINCT topic, section FROM qa_chunks`; (3) guardrails verbatim. Include the ≤2-clarifying-question and ticket-offer policy.
- **Report tools are intent-only:** a report tool call → yield `report_request{report_type, fields}` carrying the Anthropic `tool_use_id`, then stop the stream (turn awaits widget input). `resume_report_stream(...)` appends a `tool_result` for that `tool_use_id` (the `ReportResult` data) and re-enters the loop.
- **Streaming contract:** map Anthropic stream events to `SSEEvent`s — `status` at tool-use boundaries, `token` for text deltas, `citations` once (from the last `rag_search`), `usage` at end (`input/output` tokens → INR via `cost.py`, plus running `cumulative_cost_inr`), then `done`. Errors → `error` frame.
- **Caps:** track clarifying-question count and total message count on the session/conversation; at the cap, the assistant offers to raise a support ticket instead of continuing.
- **Cost:** `cost.py` converts Anthropic usage to INR using per-model USD rates × a configurable USD→INR rate.
- **Tracing:** root function decorated `observe(type="agent")`; sets `update_current_trace(thread_id=session id, user_id)`; RAG/tool/LLM spans nest automatically.

## Risks / Trade-offs

- Pause/resume adds a state hop (pending `tool_use_id`); kept minimal and stateless-per-request by passing `messages` + `tool_use_id` back in on resume.
- Guardrail robustness is validated by `chatbot-multiturn-evals` (P7) guardrail-probe goldens; prompt is iterated against those results.
- Citation extraction depends on the loop remembering the last `rag_search` result within the turn.
