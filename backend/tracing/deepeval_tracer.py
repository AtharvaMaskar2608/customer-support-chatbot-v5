"""DeepEval-backed :class:`~backend.tracing.interface.Tracer` implementation.

This is the single module that imports ``deepeval``. It is a thin, faithful passthrough
to DeepEval's tracing primitives (``@observe`` + ``trace_manager``) per
``docs/tracing/1_rag_tracing.md`` and ``docs/tracing/2_multi_turn_chat_tracing.md``.
Downstream code (RAG, agent) never imports this module directly — it goes through
``get_tracer()``; ``backend.tracing.setup`` swaps this in at startup when tracing is
enabled. Isolating every DeepEval import here means an upstream API/version drift touches
one file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from deepeval.tracing import (
    evaluate_thread as _evaluate_thread,
    observe as _observe,
    trace as _trace,
    trace_manager as _trace_manager,
    update_current_span as _update_current_span,
    update_current_trace as _update_current_trace,
)

F = TypeVar("F", bound=Callable[..., Any])


class DeepEvalTracer:
    """Concrete :class:`~backend.tracing.interface.Tracer` delegating to DeepEval.

    Every method forwards verbatim to the same-named ``deepeval.tracing`` primitive so the
    tracer adds no behavior of its own. Span types used by the app are ``retriever`` (RAG),
    ``tool`` (report tools), ``llm`` (Anthropic call), and ``agent`` (root turn); multi-turn
    grouping is done by the caller via ``update_current_trace(thread_id=..., user_id=...)``.
    """

    def observe(
        self,
        type: str | None = None,
        name: str | None = None,
        metrics: list[Any] | None = None,
        metric_collection: str | None = None,
        **kwargs: Any,
    ) -> Callable[[F], F]:
        """Return DeepEval's ``@observe`` decorator recording a span for the function.

        Only forwards the optional args the caller actually set: DeepEval derives the span
        ``name`` from the wrapped function when it is omitted, and passing ``name=None``
        explicitly would defeat that (agent spans require a non-null name).
        """
        if name is not None:
            kwargs["name"] = name
        if metrics is not None:
            kwargs["metrics"] = metrics
        if metric_collection is not None:
            kwargs["metric_collection"] = metric_collection
        return _observe(type=type, **kwargs)

    def span(self, name: str | None = None, **kwargs: Any) -> Any:
        """Context manager scoping a span.

        DeepEval builds its span tree from the ``@observe`` call stack rather than an
        explicit span context manager, so this maps to DeepEval's ``trace`` context
        manager (a span within the active trace). Prefer ``observe`` for instrumentation.
        """
        return _trace(name=name, **kwargs)

    def trace(self, thread_id: str | None = None, **kwargs: Any) -> Any:
        """Context manager scoping a thread-level trace (DeepEval ``trace``)."""
        return _trace(thread_id=thread_id, **kwargs)

    def update_current_span(self, **kwargs: Any) -> None:
        """Annotate the active span (input/output/``retrieval_context``/metadata)."""
        _update_current_span(**kwargs)

    def update_current_trace(self, **kwargs: Any) -> None:
        """Annotate the active trace (``thread_id``/``user_id``/tags/metadata)."""
        _update_current_trace(**kwargs)

    def configure(self, **kwargs: Any) -> None:
        """Configure the DeepEval trace manager (api key, environment, sampling, mask)."""
        _trace_manager.configure(**kwargs)

    def get_all_traces_dict(self) -> list[dict[str, Any]]:
        """Return every trace captured in this process as plain dicts."""
        return _trace_manager.get_all_traces_dict()

    def evaluate_thread(self, thread_id: str, **kwargs: Any) -> None:
        """Trigger asynchronous evaluation of a completed thread (requires Confident AI)."""
        _evaluate_thread(thread_id=thread_id, **kwargs)
