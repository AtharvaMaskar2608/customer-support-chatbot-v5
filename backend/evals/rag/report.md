# RAG Retrieval Eval Report

Goldens evaluated: **3**

## Hyperparameters

- **embedding model**: text-embedding-3-large
- **chunk size**: pre-chunked (qa_chunks)
- **k**: 5
- **rrf_k**: 60
- **judge model**: gpt-4o

## Judged retrieval metrics (mean score)

- **Contextual Precision**: 0.733
- **Contextual Recall**: 0.833
- **Contextual Relevancy**: 0.603

## Deterministic chunk-id recall

- **id_recall@5**: 0.667 (fraction of goldens whose source chunk is in top-k; judge-free)
