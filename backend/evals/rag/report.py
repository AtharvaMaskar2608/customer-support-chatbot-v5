"""One-shot RAG retrieval eval report: judged metric means + deterministic id-recall.

Runs ``rag_search`` over the generated golden set, scores it with the three contextual
DeepEval metrics via ``evaluate(...)``, computes deterministic chunk-id recall, logs the
retrieval hyperparameters (embedding model, chunk size, k, judge model), and writes a
human-readable ``report.md`` next to this module::

    python -m backend.evals.rag.report

Requires a generated golden set plus retrieval + judge credentials (see ``test_rag``).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean

from deepeval import evaluate

from backend.evals.rag.generate_goldens import load_goldens
from backend.evals.rag.test_rag import (
    DEFAULT_TOP_K,
    build_test_case,
    chunk_id_recall,
    hyperparameters,
    retrieval_metrics,
)

REPORT_PATH = Path(__file__).parent / "report.md"


def _aggregate_scores(evaluation_result) -> dict[str, float]:
    """Mean score per metric name across all test results.

    Contract: reads ``test_results[*].metrics_data[*]`` and returns
    ``{metric_name: mean_score}``, skipping entries whose score is ``None`` (metric
    errored). Empty dict if nothing scored.
    """
    scores: dict[str, list[float]] = defaultdict(list)
    for test_result in evaluation_result.test_results:
        for metric in test_result.metrics_data or []:
            if metric.score is not None:
                scores[metric.name].append(metric.score)
    return {name: mean(values) for name, values in scores.items() if values}


def _render(
    params: dict[str, object], metric_means: dict[str, float], id_recall: float, n: int
) -> str:
    """Render the aggregated results as a Markdown report."""
    lines = [
        "# RAG Retrieval Eval Report",
        "",
        f"Goldens evaluated: **{n}**",
        "",
        "## Hyperparameters",
        "",
    ]
    lines += [f"- **{key}**: {value}" for key, value in params.items()]
    lines += [
        "",
        "## Judged retrieval metrics (mean score)",
        "",
    ]
    if metric_means:
        lines += [
            f"- **{name}**: {score:.3f}" for name, score in sorted(metric_means.items())
        ]
    else:
        lines.append("- _(no judged scores)_")
    lines += [
        "",
        "## Deterministic chunk-id recall",
        "",
        f"- **id_recall@{DEFAULT_TOP_K}**: {id_recall:.3f} "
        "(fraction of goldens whose source chunk is in top-k; judge-free)",
        "",
    ]
    return "\n".join(lines)


def build_report(path: Path = REPORT_PATH) -> Path:
    """Score the golden set, log hyperparameters, and write the Markdown report.

    Contract: loads the golden set (raising if empty — nothing to report), builds one
    ``LLMTestCase`` per golden, runs ``evaluate`` with the three contextual metrics and the
    logged hyperparameters, aggregates mean metric scores plus deterministic id-recall, and
    writes the report to ``path`` (returned). Prints a short summary to stdout.
    """
    goldens = load_goldens()
    if not goldens:
        raise SystemExit(
            "no goldens found — run `python -m backend.evals.rag.generate_goldens` first"
        )

    params = hyperparameters()
    test_cases = [build_test_case(golden) for golden in goldens]
    evaluation_result = evaluate(
        test_cases=test_cases,
        metrics=retrieval_metrics(),
        hyperparameters=params,
    )

    metric_means = _aggregate_scores(evaluation_result)
    id_recall = chunk_id_recall(goldens)

    report = _render(params, metric_means, id_recall, len(goldens))
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote report to {path}")
    return path


if __name__ == "__main__":
    build_report()
