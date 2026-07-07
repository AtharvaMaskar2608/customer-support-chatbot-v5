"""Generate a synthetic golden set from ``qa_chunks`` for RAG retrieval evaluation.

Each golden is synthesized from a single ``qa_chunks`` row — its ``chunk`` text is passed
as the sole context to DeepEval's ``Synthesizer.generate_goldens_from_contexts`` — and the
source ``qa_chunks.id`` is persisted in the golden's ``additional_metadata`` so retrieval
can later be checked deterministically (see :mod:`backend.evals.rag.test_rag`).

Goldens are serialized to ``goldens.json`` alongside this module; ``test_rag.py`` and
``report.py`` read them back. Run standalone to (re)build the golden set::

    python -m backend.evals.rag.generate_goldens --sample 10

Follows ``docs/rag_guide/2_rag_eval_synthetic_data.md``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.db.query import fetch

if TYPE_CHECKING:  # avoid importing deepeval on the hot path / for type hints only
    from deepeval.dataset import Golden

# Persisted golden set consumed by ``test_rag.py`` and ``report.py``.
GOLDENS_PATH = Path(__file__).parent / "goldens.json"

# Default number of ``qa_chunks`` rows to synthesize goldens from. Kept small so LLM
# synthesis and the judged eval stay CI-affordable; override with ``--sample``.
DEFAULT_SAMPLE_SIZE = 10


# DeepEval's built-in default judge (``gpt-5.4``) is not enabled on this OpenAI project,
# so the eval pins an accessible model instead. Overridable via ``DEEPEVAL_JUDGE_MODEL``.
DEFAULT_JUDGE_MODEL = "gpt-4o"


def judge_model() -> str:
    """DeepEval synthesis/judge model name for the eval.

    Contract: returns ``DEEPEVAL_JUDGE_MODEL`` if set, else ``DEFAULT_JUDGE_MODEL``
    (``gpt-4o``). Never returns ``None`` — DeepEval's built-in default is not accessible
    here — so synthesis and scoring always run on the same, project-enabled judge. Shared
    by :mod:`.generate_goldens`, :mod:`.test_rag`, and :mod:`.report`.
    """
    return os.environ.get("DEEPEVAL_JUDGE_MODEL") or DEFAULT_JUDGE_MODEL


def _sample_chunks(sample_size: int) -> list[dict[str, Any]]:
    """Sample ``sample_size`` ``qa_chunks`` rows (id + text), deterministically ordered.

    Contract: returns up to ``sample_size`` rows ``{"id": int, "chunk": str}`` from
    ``qa_chunks``, ordered by ``id`` (not ``RANDOM()``) so a regenerated golden set is
    reproducible across runs given the same corpus and sample size.
    """
    sql = "SELECT id, chunk FROM qa_chunks ORDER BY id LIMIT %(n)s"
    return fetch(sql, {"n": sample_size})


def generate_goldens(sample_size: int = DEFAULT_SAMPLE_SIZE) -> list[Golden]:
    """Synthesize one golden per sampled ``qa_chunks`` row, tagged with its source id.

    Contract: for each of ``sample_size`` sampled chunks, calls
    ``generate_goldens_from_contexts([[chunk_text]], max_goldens_per_context=1)`` and
    stamps ``additional_metadata["source_chunk_id"]`` on every returned golden. A chunk
    the synthesizer rejects (low context quality) simply contributes no goldens, so the
    result length is ``<= sample_size``. Requires ``DATABASE_URL`` (sampling) and a
    DeepEval-configured synthesis model.
    """
    # Deferred: importing deepeval pulls in the synthesis LLM client; keep it off the
    # module import path so ``load_goldens`` callers that only read JSON stay light.
    from deepeval.synthesizer import Synthesizer

    synthesizer = Synthesizer(model=judge_model())
    goldens: list[Golden] = []
    for row in _sample_chunks(sample_size):
        generated = synthesizer.generate_goldens_from_contexts(
            contexts=[[row["chunk"]]],
            max_goldens_per_context=1,
        )
        for golden in generated:
            golden.additional_metadata = {
                **(golden.additional_metadata or {}),
                "source_chunk_id": row["id"],
            }
            goldens.append(golden)
    return goldens


def save_goldens(goldens: list[Golden], path: Path = GOLDENS_PATH) -> Path:
    """Serialize goldens (input, expected_output, context, source_chunk_id) to JSON.

    Contract: writes a JSON array to ``path`` and returns it. Only the fields the eval
    needs are persisted; ``source_chunk_id`` is lifted out of ``additional_metadata`` into
    a top-level key for readability.
    """
    records = [
        {
            "input": golden.input,
            "expected_output": golden.expected_output,
            "context": golden.context,
            "source_chunk_id": (golden.additional_metadata or {}).get("source_chunk_id"),
        }
        for golden in goldens
    ]
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_goldens(path: Path = GOLDENS_PATH) -> list[Golden]:
    """Load persisted goldens as DeepEval ``Golden``s, restoring ``source_chunk_id``.

    Contract: returns ``[]`` if ``path`` does not exist (golden set not yet generated),
    otherwise one ``Golden`` per record with ``additional_metadata["source_chunk_id"]``
    restored so id-recall can look it up. Reads JSON only — no DB or LLM access.
    """
    if not path.exists():
        return []
    from deepeval.dataset import Golden

    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        Golden(
            input=record["input"],
            expected_output=record.get("expected_output"),
            context=record.get("context"),
            additional_metadata={"source_chunk_id": record.get("source_chunk_id")},
        )
        for record in records
    ]


def main() -> None:
    """CLI entry point: sample chunks, synthesize goldens, persist them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"number of qa_chunks rows to sample (default {DEFAULT_SAMPLE_SIZE})",
    )
    args = parser.parse_args()

    goldens = generate_goldens(args.sample)
    path = save_goldens(goldens)
    print(f"Wrote {len(goldens)} goldens to {path}")


if __name__ == "__main__":
    main()
