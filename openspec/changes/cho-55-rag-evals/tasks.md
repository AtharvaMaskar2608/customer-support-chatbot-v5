## 1. Golden generation

- [ ] 1.1 `backend/evals/rag/generate_goldens.py`: sample `qa_chunks`, call `Synthesizer.generate_goldens_from_contexts(...)`, persist goldens with `source_chunk_id` in metadata.

## 2. Retrieval scoring

- [ ] 2.1 `backend/evals/rag/test_rag.py`: for each golden, run `rag_search`, build `LLMTestCase(input, actual_output, expected_output, retrieval_context=[chunk texts])`.
- [ ] 2.2 Score with `ContextualRecallMetric`, `ContextualPrecisionMetric`, `ContextualRelevancyMetric`; `@pytest.mark.parametrize` + `assert_test` for `deepeval test run`.
- [ ] 2.3 Deterministic chunk-id recall: fraction of goldens whose `source_chunk_id` is in `rag_search` top-k.

## 3. Report

- [ ] 3.1 `backend/evals/rag/report.py`: aggregate metric scores + id-recall into a written report; `log_hyperparameters(embedding model, chunk size, k, judge model)`.

## 4. Done condition

- [ ] 4.1 `openspec validate rag-evals --strict` passes.
- [ ] 4.2 Test command: `deepeval test run backend/evals/rag/test_rag.py` completes and produces metric scores + id-recall over a small golden sample.
