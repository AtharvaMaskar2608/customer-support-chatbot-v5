"""DeepEval retrieval scoring of ``rag_search`` against the synthetic golden set.

For each golden, ``rag_search(golden.input)`` supplies the ``retrieval_context`` for an
``LLMTestCase`` scored by three LLM-judged contextual metrics, plus a deterministic
chunk-id recall that needs no judge. The judged metrics are **reported, not gated** (their
scores flow to the report / Confident AI but non-determinism must not break the build); the
deterministic id-recall test is the **CI gate**. Run in CI with::

    deepeval test run backend/evals/rag/test_rag.py

Requires a generated golden set (``python -m backend.evals.rag.generate_goldens``),
``DATABASE_URL`` / ``OPENAI_API_KEY`` for retrieval, and a judge model (``gpt-4o`` by
default, override with ``DEEPEVAL_JUDGE_MODEL``). Missing goldens or credentials skip the
tests.

Follows ``docs/rag_guide/3_rag_eval.md``.
"""

from __future__ import annotations

from functools import lru_cache
from statistics import mean
from typing import TYPE_CHECKING

import deepeval
import pytest

from backend.config.settings import get_settings
from backend.evals.rag.generate_goldens import judge_model, load_goldens
from backend.rag.search import _RRF_K, rag_search

if TYPE_CHECKING:
    from deepeval.dataset import Golden
    from deepeval.metrics import BaseMetric
    from deepeval.test_case import LLMTestCase

# Retriever top-k under evaluation and passing gates. ``_METRIC_THRESHOLD`` is the per-golden
# pass bar for each judged metric; ``ID_RECALL_THRESHOLD`` gates the deterministic recall.
DEFAULT_TOP_K = 5
_METRIC_THRESHOLD = 0.5
ID_RECALL_THRESHOLD = 0.5

# Cheap JSON read at import; empty until ``generate_goldens`` has been run.
_GOLDENS = load_goldens()

# Judge model for the LLM-scored metrics (``gpt-4o`` unless ``DEEPEVAL_JUDGE_MODEL`` set).
_JUDGE_MODEL = judge_model()


def hyperparameters() -> dict[str, object]:
    """Retrieval knobs behind these scores, single-sourced for CI logging and the report.

    Contract: returns the tunable retrieval hyperparameters — embedding model, chunk size
    (the corpus is pre-chunked in ``qa_chunks``), retriever ``k``, the RRF constant, and
    the judge model. Consumed by :func:`_log_hyperparameters` (``deepeval test run``) and by
    :mod:`backend.evals.rag.report` (``evaluate(hyperparameters=...)`` + written report).
    """
    return {
        "embedding model": get_settings().embedding_model,
        "chunk size": "pre-chunked (qa_chunks)",
        "k": DEFAULT_TOP_K,
        "rrf_k": _RRF_K,
        "judge model": _JUDGE_MODEL,
    }


@deepeval.log_hyperparameters
def _log_hyperparameters() -> dict[str, object]:
    """Attribute retrieval hyperparameters to the ``deepeval test run`` (CI path)."""
    return hyperparameters()


def _require_env() -> None:
    """Skip the calling test unless DB + OpenAI credentials are available."""
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - config missing
        pytest.skip(f"settings unavailable: {exc}")
    if not settings.database_url or not settings.openai_api_key:
        pytest.skip("DATABASE_URL / OPENAI_API_KEY not configured")


@lru_cache(maxsize=None)
def _retrieve(query: str):
    """Retrieve top-k chunks for ``query``, cached so metric + recall tests share one call."""
    return rag_search(query, top_k=DEFAULT_TOP_K)


def retrieval_metrics(threshold: float = _METRIC_THRESHOLD) -> list[BaseMetric]:
    """Build the three contextual retrieval metrics with a shared threshold and judge.

    Contract: returns ``[ContextualRecallMetric, ContextualPrecisionMetric,
    ContextualRelevancyMetric]``, each at ``threshold`` and using ``_JUDGE_MODEL`` (or the
    DeepEval default when unset). Imported lazily to keep DeepEval off the import path.
    """
    from deepeval.metrics import (
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        ContextualRelevancyMetric,
    )

    return [
        ContextualRecallMetric(threshold=threshold, model=_JUDGE_MODEL),
        ContextualPrecisionMetric(threshold=threshold, model=_JUDGE_MODEL),
        ContextualRelevancyMetric(threshold=threshold, model=_JUDGE_MODEL),
    ]


def build_test_case(golden: Golden) -> LLMTestCase:
    """Turn a golden into an ``LLMTestCase`` whose ``retrieval_context`` is ``rag_search``'s output.

    Contract: runs (cached) retrieval for ``golden.input`` and returns an ``LLMTestCase``
    with ``input``, ``expected_output`` (the golden's ground truth), and
    ``retrieval_context`` = the retrieved chunk texts. ``actual_output`` mirrors
    ``expected_output`` as a benign placeholder: the three contextual retrieval metrics
    score ``retrieval_context`` against ``input``/``expected_output`` and never read
    ``actual_output`` (generation quality is out of scope here).
    """
    from deepeval.test_case import LLMTestCase

    result = _retrieve(golden.input)
    expected = golden.expected_output or ""
    return LLMTestCase(
        input=golden.input,
        actual_output=expected,
        expected_output=golden.expected_output,
        retrieval_context=[chunk.chunk for chunk in result.chunks],
    )


def chunk_id_recall(
    goldens: list[Golden] | None = None, top_k: int = DEFAULT_TOP_K
) -> float:
    """Fraction of goldens whose ``source_chunk_id`` appears in ``rag_search``'s top-k.

    Contract: for each golden, retrieves top-``top_k`` and scores 1 if the source
    ``qa_chunks.id`` is among the returned chunk ids else 0; returns the mean (``0.0`` for
    an empty set). Judge-free, so it is a stable regression signal independent of any LLM.
    """
    goldens = _GOLDENS if goldens is None else goldens
    hits = []
    for golden in goldens:
        source_id = (golden.additional_metadata or {}).get("source_chunk_id")
        retrieved_ids = {chunk.id for chunk in _retrieve(golden.input).chunks}
        hits.append(1.0 if source_id in retrieved_ids else 0.0)
    return mean(hits) if hits else 0.0


@pytest.mark.xfail(
    reason=(
        "LLM-judged contextual metrics are non-deterministic and noisy on a small "
        "synthetic golden set; their scores are computed and logged (report + Confident "
        "AI) for trend tracking but do NOT gate CI. The deterministic chunk-id recall "
        "test is the regression gate."
    ),
    strict=False,
)
@pytest.mark.parametrize(
    "golden",
    _GOLDENS,
    ids=[f"golden-{i}" for i in range(len(_GOLDENS))],
)
def test_retrieval_metrics(golden: Golden) -> None:
    """Score each golden's retrieval with the three contextual metrics (report-only).

    ``assert_test`` still runs so every metric's score and reason are computed and logged;
    the ``xfail(strict=False)`` marker keeps a sub-threshold judged score from breaking the
    build (it surfaces as ``xfailed``/``xpassed``, never a hard failure).
    """
    from deepeval import assert_test

    _require_env()
    assert_test(build_test_case(golden), retrieval_metrics())


def test_chunk_id_recall() -> None:
    """Deterministic chunk-id recall clears the regression gate (the CI-blocking check)."""
    if not _GOLDENS:
        pytest.skip("no goldens generated — run backend.evals.rag.generate_goldens")
    _require_env()
    recall = chunk_id_recall()
    assert recall >= ID_RECALL_THRESHOLD, (
        f"chunk-id recall {recall:.2f} < gate {ID_RECALL_THRESHOLD:.2f}"
    )
