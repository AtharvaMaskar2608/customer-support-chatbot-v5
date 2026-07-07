## ADDED Requirements

### Requirement: Hybrid retrieval over qa_chunks

The system SHALL provide `rag_search(query, top_k) -> RagResult` that embeds the raw query with `text-embedding-3-large` (full 3072 dims), runs a dense vector search (`embedding <=> qvec`, cosine, exact scan) and a keyword search (`websearch_to_tsquery`/`ts_rank` over `qa_chunks.fts`), fuses the two ranked lists with Reciprocal Rank Fusion (`k=60`), and returns the top-`k` chunks.

#### Scenario: Query returns fused, ranked chunks

- **WHEN** `rag_search("<a KB question>", top_k=5)` is called
- **THEN** it returns a `RagResult` with up to 5 `RagChunk`s ordered by fused RRF score

#### Scenario: Exact vector scan, no ANN index

- **WHEN** the vector leg runs
- **THEN** it orders by cosine distance over a sequential scan of `qa_chunks` (no approximate index), giving deterministic, full-recall ranking at corpus scale

### Requirement: Citations on retrieved chunks

Every returned `RagChunk` SHALL include a `Citation` populated from `qa_chunks` metadata (`id`, `topic`, `section`, `question`, `answer_source`, `source_sheet`, `source_row`).

#### Scenario: Retrieved chunk is citable

- **WHEN** a chunk is returned from `rag_search`
- **THEN** its `Citation` contains the source metadata sufficient to render a hoverable citation card

### Requirement: rag_search exposed as an Anthropic tool with retriever tracing

The system SHALL expose `RAG_SEARCH_TOOL` (model-visible input `{query}`) and instrument retrieval with the foundations tracing interface as a `retriever` span carrying `retrieval_context`.

#### Scenario: Retriever span records context

- **WHEN** `rag_search` runs with tracing enabled
- **THEN** a `retriever` span is recorded with `retrieval_context` set to the retrieved chunk texts; with tracing disabled the function runs unchanged
