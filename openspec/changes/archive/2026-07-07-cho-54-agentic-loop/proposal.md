## Why

The core of the product: an Anthropic tool-use loop that answers FAQ questions from RAG and runs reports, while holding SEBI/scope guardrails and streaming progress. It ties together RAG (P1), the report tools (P2), and tracing (P3).

## What Changes

- Add the agentic loop over the Anthropic Messages API (`settings.anthropic_model`, default `claude-sonnet-4-5`, **thinking disabled**): call model → run tool calls → feed results back → repeat until final answer.
- Register tools: `RAG_SEARCH_TOOL` (P1), `CML_REPORT_TOOL` / `CONTRACT_NOTE_TOOL` (P2, intent-only).
- Build the **system prompt**: the available tool list + the in-scope KB categories (derived from `qa_chunks.topic`/`section`) + the guardrails.
- **Streaming API:** `agent_reply_stream(session, messages)` yields `SSEEvent`s: `status` (e.g. "Looking up the knowledge base…", "Generating the answer…") → `token`s → `citations` (when RAG was used) → `usage` (per-message cost/latency + `cumulative_cost_inr`) → `done`. Non-streaming `agent_reply(session, messages) -> AgentReply` for evals.
- **Report flow:** when the model calls a report intent tool, emit a `report_request` frame (report_type + fields) and pause; `resume_report_stream(session, messages, tool_use_id, report_result)` injects the tool result and continues to a compliant summary.
- **Caps:** ≤2 clarifying questions per conversation; ≤10 total messages; at the cap, offer to raise a support ticket.
- **Cost:** compute per-message INR from Anthropic token usage; maintain a running cumulative total.
- Instrument with tracing: root `agent` span + `update_current_trace(thread_id, user_id)`; `llm`/`tool`/`retriever` child spans.

Follows `docs/project_context.md` §3.4 (loop) and §5 (guardrails).

## Capabilities

### New Capabilities
- `agentic-loop`: the Anthropic tool-use loop, tool registration, system prompt, streaming/non-streaming entry points, report pause/resume, caps, and cost/latency accounting.
- `conversation-guardrails`: SEBI (no advice/opinions) and scope (Choice FinX only) guardrails enforced across the whole conversation.

## Impact

- New: `backend/agent/loop.py`, `backend/agent/prompt.py`, `backend/agent/tools.py` (registry/dispatch), `backend/agent/cost.py`, `backend/agent/__init__.py`.
- Imports from foundations (contracts/config/`Tracer`), P1 (`rag_search`, `RAG_SEARCH_TOOL`), P2 (report tools + intent schemas). Emits P0 `SSEEvent`s.
- Consumed by `api-sse-session` (transport) and `chatbot-multiturn-evals` (`agent_reply` as the model callback).
