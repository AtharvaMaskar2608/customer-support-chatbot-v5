## Why

The RAG path and the multi-turn agent loop must be traceable end-to-end (retrieval, tool, LLM, and agent spans; turns grouped per conversation) to support debugging and the eval workflows. Foundations already defines the no-op-safe `Tracer` Protocol; this change provides the concrete DeepEval / Confident AI implementation behind it.

## What Changes

- Add `DeepEvalTracer` implementing the foundations `Tracer` Protocol as a thin passthrough to DeepEval:
  - `observe(type=...)` → `deepeval.tracing.observe` (span types `retriever` | `tool` | `llm` | `agent`).
  - `update_current_span(...)` / `update_current_trace(...)` → same-named DeepEval functions.
  - `configure(...)` → `trace_manager.configure(confident_api_key, environment, sampling_rate, mask)`.
  - `evaluate_thread(...)` and `get_all_traces_dict()` passthroughs.
- Multi-turn grouping via `update_current_trace(thread_id=..., user_id=...)`.
- Register `DeepEvalTracer` as the active tracer at app startup when tracing is enabled; otherwise the no-op default stays.

Follows `docs/tracing/1_rag_tracing.md` and `docs/tracing/2_multi_turn_chat_tracing.md`.

## Capabilities

### New Capabilities
- `tracing-observability`: DeepEval-backed tracer (retriever/tool/llm/agent spans, thread-grouped multi-turn traces) implementing the foundations `Tracer` Protocol.

## Impact

- New: `backend/tracing/deepeval_tracer.py`, `backend/tracing/setup.py` (startup registration).
- Imports the `Tracer` Protocol + `set_tracer`/`get_tracer` and `Settings` from foundations. Adds no root dependencies (`deepeval` declared by foundations).
- Consumed indirectly by `rag-hybrid-retrieval` and `agentic-loop` — they call the Protocol only; wiring happens here + at the composition root.
