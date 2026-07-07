"""No-op-safe tracing interface.

RAG (P1) and the agent (P4) import only the :class:`Tracer` Protocol and a selected
implementation from here — never ``deepeval`` directly — so the choice of concrete vs
no-op tracing is made in one place. The concrete DeepEval-backed implementation is
provided by the ``tracing-foundation`` change; until then :class:`NoOpTracer` is the
default and adds no behavior, no latency, and no import dependency on ``deepeval``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any, Protocol, TypeVar, runtime_checkable

F = TypeVar("F", bound=Callable[..., Any])


@runtime_checkable
class Tracer(Protocol):
    """Tracing surface imported by RAG and the agent.

    Contract: ``observe`` returns a decorator that wraps a function to record a span;
    ``span``/``trace`` are context managers scoping a span or a thread-level trace;
    ``update_current_span``/``update_current_trace`` annotate the active span/trace;
    ``configure`` sets backend options; ``get_all_traces_dict`` and ``evaluate_thread``
    support eval/inspection. Every method must be safe to call when tracing is disabled.
    """

    def observe(
        self,
        type: str | None = None,
        name: str | None = None,
        metrics: list[Any] | None = None,
        metric_collection: str | None = None,
        **kwargs: Any,
    ) -> Callable[[F], F]:
        """Return a decorator recording a span for the wrapped function."""
        ...

    def span(self, name: str | None = None, **kwargs: Any) -> Any:
        """Context manager scoping a span."""
        ...

    def trace(self, thread_id: str | None = None, **kwargs: Any) -> Any:
        """Context manager scoping a thread-level trace."""
        ...

    def update_current_span(self, **kwargs: Any) -> None:
        """Annotate the currently active span (input/output/metadata)."""
        ...

    def update_current_trace(self, **kwargs: Any) -> None:
        """Annotate the currently active trace (thread_id/metadata)."""
        ...

    def configure(self, **kwargs: Any) -> None:
        """Configure the tracing backend."""
        ...

    def get_all_traces_dict(self) -> list[dict[str, Any]]:
        """Return captured traces as plain dicts (empty when disabled)."""
        ...

    def evaluate_thread(self, thread_id: str, **kwargs: Any) -> None:
        """Trigger evaluation of a completed thread."""
        ...


class NoOpTracer:
    """Default :class:`Tracer` that does nothing.

    ``observe`` returns an identity decorator, ``span``/``trace`` yield inert context
    managers, and the annotation/config methods are no-ops. Wrapped functions run
    unchanged with no added latency.
    """

    def observe(
        self,
        type: str | None = None,
        name: str | None = None,
        metrics: list[Any] | None = None,
        metric_collection: str | None = None,
        **kwargs: Any,
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            return func

        return decorator

    @contextlib.contextmanager
    def span(self, name: str | None = None, **kwargs: Any) -> Iterator[None]:
        yield

    @contextlib.contextmanager
    def trace(self, thread_id: str | None = None, **kwargs: Any) -> Iterator[None]:
        yield

    def update_current_span(self, **kwargs: Any) -> None:
        return None

    def update_current_trace(self, **kwargs: Any) -> None:
        return None

    def configure(self, **kwargs: Any) -> None:
        return None

    def get_all_traces_dict(self) -> list[dict[str, Any]]:
        return []

    def evaluate_thread(self, thread_id: str, **kwargs: Any) -> None:
        return None


_NOOP_TRACER = NoOpTracer()
_current_tracer: Tracer = _NOOP_TRACER


def set_tracer(tracer: Tracer) -> None:
    """Register the active tracer.

    ``tracing-foundation`` (P3) calls this at startup to swap in the DeepEval-backed
    implementation; foundations ships the no-op tracer as the default. This is the single
    registration point, so downstream code never imports ``deepeval`` or edits this module.
    """
    global _current_tracer
    _current_tracer = tracer


def get_tracer() -> Tracer:
    """Return the active tracer (the no-op tracer until ``set_tracer`` registers another).

    Importers call ``get_tracer()`` and use the returned object, so the impl choice lives
    in one place.
    """
    return _current_tracer
