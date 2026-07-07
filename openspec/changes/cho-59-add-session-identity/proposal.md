## Why

The agent traces each conversation with a `thread_id` so DeepEval/Confident AI can group a session's turns and the multi-turn evals (P7) can score whole conversations. `Session` had no unique per-session id, so the agent fell back to `session.client_code` — a **per-client** identifier that is stable across every conversation a client ever has (and reused across testers). That collapses distinct conversations into one trace thread and corrupts multi-turn metrics (KnowledgeRetention, ConversationCompleteness) which operate on the grouped turns. A per-session identity fixes it.

## What Changes

- Add `session_id: str` to the `Session` contract (data-contracts) — a unique, stable identifier assigned once at session creation (default: a generated uuid; the API layer supplies its own so the store key and the trace `thread_id` match).
- The agent (agentic-loop) uses `session.session_id` as the tracing `thread_id` instead of `session.client_code`. (Implemented in `backend/agent/loop.py`.)

## Capabilities

### Modified Capabilities
- `data-contracts`: `Session` gains a unique, stable `session_id`.

## Impact

- `backend/contracts/models.py` — `Session.session_id` (additive; `default_factory` keeps existing constructions valid).
- `backend/agent/loop.py` — trace `thread_id = session.session_id` (one line, three call sites).
- Consumed by `api-sse-session` (P5) — it assigns the session store key as `session_id` so the API session and the trace thread share one id.
