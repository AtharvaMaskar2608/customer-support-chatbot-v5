# rag-evals Specification

## Purpose
TBD - created by archiving change cho-55-rag-evals. Update Purpose after archive.
## Requirements
### Requirement: Synthetic golden set from qa_chunks

The system SHALL generate a golden set with DeepEval's `Synthesizer` from `qa_chunks` contexts, persisting each golden's source `qa_chunks.id` in its metadata so retrieval can be checked deterministically.

#### Scenario: Goldens carry their source chunk id

- **WHEN** goldens are generated from sampled `qa_chunks` rows
- **THEN** each golden records its `source_chunk_id` alongside its `input` and `expected_output`

### Requirement: Retrieval scoring of rag_search

The system SHALL score `rag_search` against the goldens using `ContextualRecallMetric`, `ContextualPrecisionMetric`, and `ContextualRelevancyMetric`, passing the chunk texts returned by `rag_search` as `retrieval_context`.

#### Scenario: Retrieval metrics computed per golden

- **WHEN** the eval runs for a golden
- **THEN** `rag_search(golden.input)` provides the `retrieval_context` for an `LLMTestCase` and the three contextual metrics produce scores

### Requirement: Deterministic chunk-id recall

The system SHALL report the fraction of goldens whose `source_chunk_id` appears in `rag_search`'s top-k, independent of any LLM judge.

#### Scenario: Id recall is a stable signal

- **WHEN** the eval completes
- **THEN** it reports a deterministic id-recall score that does not depend on an LLM judge, usable as a regression gate

