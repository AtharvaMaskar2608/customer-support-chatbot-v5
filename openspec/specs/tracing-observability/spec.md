# tracing-observability Specification

## Purpose
TBD - created by archiving change cho-53-tracing-foundation. Update Purpose after archive.
## Requirements
### Requirement: DeepEval-backed tracer implementation

The system SHALL provide `DeepEvalTracer` implementing the foundations `Tracer` Protocol as a thin passthrough to DeepEval: `observe(type=...)` maps to `deepeval.tracing.observe` with span types `retriever` | `tool` | `llm` | `agent`; `update_current_span`/`update_current_trace`/`evaluate_thread`/`get_all_traces_dict` map to the same-named DeepEval functions; `configure(...)` maps to `trace_manager.configure`.

#### Scenario: Spans recorded for a traced call

- **WHEN** tracing is enabled and a function decorated with `observe(type="retriever")` runs
- **THEN** DeepEval records a `retriever` span whose input/output/`retrieval_context` are captured, retrievable via `get_all_traces_dict()`

### Requirement: Startup registration without reverse dependency

The system SHALL register `DeepEvalTracer` as the active tracer at application startup (via `init_tracing(settings)` calling foundations' `set_tracer`) when `tracing_enabled` and `CONFIDENT_API_KEY` are present, and otherwise leave the no-op default. Foundations SHALL NOT import this change.

#### Scenario: Disabled tracing keeps the no-op

- **WHEN** `init_tracing` runs with tracing disabled
- **THEN** the foundations no-op tracer remains active and instrumented functions run unchanged with no traces

### Requirement: Multi-turn traces grouped by thread

The tracer SHALL support grouping conversation turns by `thread_id` via `update_current_trace(thread_id=..., user_id=...)`, so each turn's retriever/tool/llm spans nest under the turn's `agent` span and all turns of a conversation share one thread.

#### Scenario: Turns of one conversation share a thread

- **WHEN** two turns of the same conversation set the same `thread_id`
- **THEN** their traces are grouped into a single thread in the trace store

