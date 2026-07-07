## 1. Concrete tracer

- [x] 1.1 `backend/tracing/deepeval_tracer.py`: `DeepEvalTracer` implementing the `Tracer` Protocol as passthroughs to `deepeval.tracing` (`observe`, `update_current_span`, `update_current_trace`, `evaluate_thread`, `get_all_traces_dict`) and `trace_manager.configure`.

## 2. Startup registration

- [x] 2.1 `backend/tracing/setup.py`: `init_tracing(settings)` registers `DeepEvalTracer` via `set_tracer(...)` when enabled, else leaves the no-op default.

## 3. Multi-turn grouping

- [x] 3.1 Ensure the tracer supports `update_current_trace(thread_id=..., user_id=...)` so agent turns group into one thread.

## 4. Done condition

- [x] 4.1 `openspec validate tracing-foundation --strict` passes.
- [x] 4.2 Test: with tracing enabled, a decorated dummy function produces a trace retrievable via `get_all_traces_dict()`; with tracing disabled, `init_tracing` leaves the no-op and the same function runs with no traces and no error. `pytest backend/tracing`.
