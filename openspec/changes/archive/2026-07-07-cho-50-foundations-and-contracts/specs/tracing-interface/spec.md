## ADDED Requirements

### Requirement: No-op-safe tracing interface

The system SHALL define a `Tracer` Protocol (in foundations) exposing `observe(type=..., name=..., metrics=..., metric_collection=...)`, `update_current_span(...)`, `update_current_trace(...)`, `configure(...)`, `get_all_traces_dict()`, and `evaluate_thread(...)`, plus a **no-op default implementation**. RAG (P1) and the agent (P4) SHALL import only this Protocol, never `deepeval` directly. The concrete DeepEval-backed implementation is provided by the `tracing-foundation` change.

#### Scenario: Tracing disabled degrades to no-op

- **WHEN** tracing is disabled (no `CONFIDENT_API_KEY` or `TRACING_ENABLED=false`) and a function is decorated with `tracer.observe(type="retriever")`
- **THEN** `observe` returns an identity decorator, `update_current_span`/`update_current_trace` do nothing, and the wrapped function runs unchanged with no error and no added latency

#### Scenario: Import surface is stable for downstream

- **WHEN** P1 or P4 imports the `Tracer` Protocol and the selected implementation from foundations
- **THEN** it can decorate functions and annotate spans/traces without importing `deepeval`, so the choice of concrete vs no-op impl is made in one place
