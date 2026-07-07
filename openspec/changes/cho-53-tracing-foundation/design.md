## Context

Foundations (P0) owns the `Tracer` Protocol, a no-op default, and a `get_tracer()`/`set_tracer()` registry. To keep the dependency direction correct (P3 depends on P0, never the reverse), the concrete tracer lives here and is **registered at startup**, not imported by foundations.

## Goals / Non-Goals

**Goals:**
- A thin, faithful passthrough to DeepEval `@observe` + `trace_manager` per the tracing guides.
- Zero added request latency (async background export) and safe degradation to no-op.
- Correct multi-turn grouping by `thread_id`.

**Non-Goals:**
- No custom span storage or UI (Confident AI hosts the explorer).
- No metric definitions (those live in the eval changes).

## Decisions

- **Registration pattern:** `backend/tracing/setup.py` exposes `init_tracing(settings)` → if `settings.tracing_enabled` and `CONFIDENT_API_KEY` present, construct `DeepEvalTracer()`, call its `configure(...)`, and `set_tracer(it)`; else leave the no-op. The composition root (API `main.py` / agent bootstrap) calls `init_tracing` once.
- **Span types:** `retriever` (RAG), `tool` (report tools), `llm` (Anthropic call), `agent` (root turn). Root turn calls `update_current_trace(thread_id, user_id)` so DeepEval groups turns into one thread.
- **Nesting is automatic** from the call stack — the agent's root `agent` span contains the `retriever`/`tool`/`llm` child spans for that turn.
- **`configure`** passes `environment`, `sampling_rate` (default 1.0), and an optional PII `mask` callable.

## Risks / Trade-offs

- DeepEval import path / API drift: isolate all DeepEval imports in `deepeval_tracer.py` so a version bump touches one file.
- If `CONFIDENT_API_KEY` is absent, traces still record locally (offline) but do not export; acceptable for dev.
