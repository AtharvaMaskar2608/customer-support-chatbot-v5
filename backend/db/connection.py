"""Read-only Postgres connection factory.

Connections are opened from ``DATABASE_URL`` (single connection string) with the
``pgvector`` adapter registered so ``vector(3072)`` columns and ``<=>`` cosine
comparisons bind correctly. The ``qa_chunks`` embeddings are already loaded — this layer
never writes, migrates, or ingests, so connections default to read-only.
"""

import psycopg
from pgvector.psycopg import register_vector

from backend.config.settings import get_settings


def connect() -> psycopg.Connection:
    """Open a new read-only connection with the pgvector adapter registered.

    Contract: returns a live ``psycopg.Connection`` in read-only mode. Callers own the
    connection and should use it as a context manager or close it explicitly.
    """
    conn = psycopg.connect(get_settings().database_url)
    conn.read_only = True
    register_vector(conn)
    return conn
