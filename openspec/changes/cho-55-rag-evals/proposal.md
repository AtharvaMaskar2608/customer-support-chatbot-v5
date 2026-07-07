## Why

Before trusting the RAG tool, we need a reproducible measure of retrieval quality. This change builds a synthetic golden set from the KB and scores `rag_search` against it with DeepEval.

## What Changes

- **Golden generation:** use DeepEval `Synthesizer.generate_goldens_from_contexts(...)` over `qa_chunks` (each context = a chunk's text), producing `Golden`s (`input`, `expected_output`) that carry the source chunk id in metadata.
- **Retrieval scoring:** for each golden, run `rag_search`, build an `LLMTestCase(input, actual_output, expected_output, retrieval_context=[chunk texts])`, and score with `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`.
- **Deterministic chunk-id recall (our addition):** since each golden is generated from a known `qa_chunks.id`, also compute the fraction of goldens whose source chunk id appears in `rag_search`'s top-k — a metric-LLM-free recall check.
- Run via `deepeval evaluate(...)` (and a `deepeval test run` pytest entry) and write a metrics report.

Follows `docs/rag_guide/2_rag_eval_synthetic_data.md` and `docs/rag_guide/3_rag_eval.md`.

## Capabilities

### New Capabilities
- `rag-evals`: synthetic golden generation from `qa_chunks` + DeepEval retrieval scoring of `rag_search`, including deterministic chunk-id recall.

## Impact

- New: `backend/evals/rag/generate_goldens.py`, `backend/evals/rag/test_rag.py`, `backend/evals/rag/report.py`, `backend/evals/rag/__init__.py`.
- Imports P1 `rag_search` and foundations (`Settings`, `db`). Read-only over `qa_chunks`. Adds no root dependencies (`deepeval` declared by foundations).
- Standalone eval — nothing else imports it.
