"""RAG retrieval evaluation.

Synthesizes a golden set from ``qa_chunks`` (:mod:`.generate_goldens`), scores
``rag_search`` against it with DeepEval's contextual metrics plus a deterministic
chunk-id recall (:mod:`.test_rag`), and writes a report (:mod:`.report`). Read-only over
``qa_chunks``; nothing in the app imports this package.
"""
