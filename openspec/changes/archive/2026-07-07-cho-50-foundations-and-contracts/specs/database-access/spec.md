## ADDED Requirements

### Requirement: Read-only Postgres access over qa_chunks

The system SHALL provide a read-only database helper that connects using `DATABASE_URL` and exposes a `fetch(sql, params) -> list[dict]` function, with the `pgvector` adapter registered so `vector(3072)` columns and `<=>` cosine comparisons work. It SHALL NOT perform writes, migrations, or ingestion (the `qa_chunks` embeddings are already loaded).

#### Scenario: Fetch rows from qa_chunks

- **WHEN** `fetch("SELECT id, chunk FROM qa_chunks LIMIT 1", [])` is called
- **THEN** it returns a list of dict rows from the live `qa_chunks` table without opening a write transaction

#### Scenario: Vector adapter registered

- **WHEN** a query orders by `embedding <=> %s` with a 3072-dim vector parameter
- **THEN** the helper binds the vector parameter correctly via the registered `pgvector` adapter
