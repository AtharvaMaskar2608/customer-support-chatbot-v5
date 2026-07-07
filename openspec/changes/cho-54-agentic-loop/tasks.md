## 1. Tool registry & system prompt

- [x] 1.1 `backend/agent/tools.py`: register `rag_search`, `cml_report`, `contract_note` (schemas + dispatch to impls); inject `session` into report/RAG calls.
- [x] 1.2 `backend/agent/prompt.py`: build system prompt = tool list + in-scope KB categories (`SELECT DISTINCT topic, section FROM qa_chunks`) + guardrails + caps policy.

## 2. Loop

- [x] 2.1 `backend/agent/loop.py`: `agent_reply(session, messages) -> AgentReply` (non-streaming) running call→tools→repeat until final; attaches citations when RAG used.
- [x] 2.2 `agent_reply_stream(session, messages) -> AsyncIterator[SSEEvent]`: status → token → citations → usage → done.
- [x] 2.3 Report pause: on a report tool call, yield `report_request{report_type, fields, tool_use_id}` and stop.
- [x] 2.4 `resume_report_stream(session, messages, tool_use_id, report_result)`: append `tool_result`, continue to final compliant summary.

## 3. Caps & cost

- [x] 3.1 Enforce ≤2 clarifying questions and ≤10 total messages; at cap, offer to raise a support ticket.
- [x] 3.2 `backend/agent/cost.py`: per-message INR from Anthropic usage + running `cumulative_cost_inr`; per-message latency.

## 4. Guardrails & tracing

- [x] 4.1 Encode SEBI (no advice/opinions/recommendations) + scope (Choice FinX only; redirect off-topic) in the system prompt; hold across turns.
- [x] 4.2 Decorate the root turn `observe(type="agent")`; `update_current_trace(thread_id, user_id)`.

## 5. Done condition

- [x] 5.1 `openspec validate agentic-loop --strict` passes.
- [x] 5.2 Test: an FAQ query returns an answer with citations; an off-topic/advice-seeking query is refused/redirected; report intent yields a `report_request` then a summary after resume; cost/latency populated. `pytest backend/agent`.
