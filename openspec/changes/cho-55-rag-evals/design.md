## Context

The KB is already in `qa_chunks`. DeepEval's `Synthesizer` can build goldens directly from contexts we supply (chunk texts), skipping document loading/chunking. Retrieval metrics need `retrieval_context` (list of chunk texts) and, for precision/recall, an `expected_output`.

## Goals / Non-Goals

**Goals:**
- A reproducible golden set traceable back to source chunk ids.
- Retrieval quality scored with standard DeepEval retriever metrics + a deterministic id-recall backstop.
- CI-friendly run (`deepeval test run`) plus a human-readable report.

**Non-Goals:**
- No generation-quality scoring of the full agent (that is `chatbot-multiturn-evals`).
- No reranker tuning; RRF-only retrieval is what we measure.

## Decisions

- **Golden source:** `generate_goldens_from_contexts(contexts=[[chunk_text], ...])`, sampling `qa_chunks`; persist each golden with its `source_chunk_id` in `additional_metadata`.
- **Metrics:** `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric` (LLM-judged) with configurable thresholds; `retrieval_context` = the chunk texts returned by `rag_search(golden.input, top_k)`.
- **Deterministic id recall:** `hits = mean(1 if source_chunk_id in {c.id for c in rag_search(...)} else 0)` — reported alongside the LLM metrics.
- **Run modes:** `evaluate(test_cases, metrics)` for a one-shot report; `test_rag.py` with `@pytest.mark.parametrize` + `assert_test` for CI via `deepeval test run`.
- **Synthesis/eval model:** configurable (defaults to the DeepEval-configured judge); the eval judge model is logged via `log_hyperparameters` alongside `embedding model`, `chunk size`, `k`.

## Risks / Trade-offs

- LLM-judged metrics are non-deterministic across runs; the id-recall metric gives a stable regression signal.
- Synthetic goldens may not match real user phrasing; treated as a first-pass signal, refined with real queries later.
