"""Read-only query helper over ``qa_chunks``."""

from collections.abc import Mapping, Sequence
from typing import Any

from psycopg.rows import dict_row

from backend.db.connection import connect

Params = Sequence[Any] | Mapping[str, Any]


def fetch(sql: str, params: Params = ()) -> list[dict[str, Any]]:
    """Run a read-only ``SELECT`` and return rows as dicts.

    Contract: opens a read-only connection (pgvector adapter registered), executes
    ``sql`` with ``params`` (positional sequence or named mapping), and returns a list of
    ``dict`` rows. The connection is closed before returning. No write transaction is
    opened. Vector parameters may be passed as a Python list for ``embedding <=> %s``
    ordering thanks to the registered adapter.
    """
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
