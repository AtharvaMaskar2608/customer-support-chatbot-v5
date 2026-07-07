"""Tracer registration + span-capture tests.

Covers the two done-condition scenarios from the ``tracing-foundation`` change:
enabled tracing records a retrievable trace, and disabled tracing leaves the no-op default
so instrumented functions run unchanged with no traces and no error.
"""

from __future__ import annotations

import pytest

from backend.tracing import get_tracer, set_tracer
from backend.tracing.interface import NoOpTracer
from backend.tracing.setup import init_tracing


class _Settings:
    """Minimal stand-in for :class:`~backend.config.settings.Settings`.

    ``init_tracing`` only reads ``tracing_enabled`` and ``confident_api_key``, so a tiny
    object avoids constructing the real (credential-requiring) settings in tests.
    """

    def __init__(self, tracing_enabled: bool, confident_api_key: str | None) -> None:
        self.tracing_enabled = tracing_enabled
        self.confident_api_key = confident_api_key


@pytest.fixture(autouse=True)
def _reset_tracer():
    """Restore the no-op default after each test so global tracer state does not leak."""
    yield
    set_tracer(NoOpTracer())


def test_disabled_tracing_keeps_noop_and_runs_unchanged():
    """Disabled tracing: no-op stays active, instrumented fn runs, no traces recorded."""
    tracer = init_tracing(_Settings(tracing_enabled=False, confident_api_key=None))
    assert isinstance(tracer, NoOpTracer)
    assert isinstance(get_tracer(), NoOpTracer)

    @get_tracer().observe(type="retriever")
    def retrieve(query: str) -> list[str]:
        return ["doc"]

    assert retrieve("q") == ["doc"]
    assert get_tracer().get_all_traces_dict() == []


def test_enabled_without_key_keeps_noop():
    """Tracing enabled but no Confident AI key: still leaves the no-op default."""
    tracer = init_tracing(_Settings(tracing_enabled=True, confident_api_key=None))
    assert isinstance(tracer, NoOpTracer)
    assert isinstance(get_tracer(), NoOpTracer)


def test_enabled_with_key_registers_deepeval_tracer():
    """Enabled + Confident AI key: init_tracing swaps in the DeepEval-backed tracer."""
    pytest.importorskip("deepeval")

    tracer = init_tracing(
        _Settings(tracing_enabled=True, confident_api_key="test-key")
    )
    # Imported lazily to keep the no-op path free of any ``deepeval`` import.
    from backend.tracing.deepeval_tracer import DeepEvalTracer

    assert isinstance(tracer, DeepEvalTracer)
    assert get_tracer() is tracer


def test_enabled_tracing_records_retrievable_trace():
    """Enabled tracing: a decorated function produces a trace via get_all_traces_dict().

    Configured offline (no Confident AI key) so traces stay in-process. DeepEval evicts a
    trace from memory once its root span ends, so the assertion snapshots the trace while
    the root ``agent`` span is still active — after its ``retriever`` child has completed —
    which is exactly the live trace state the eval workflows read.
    """
    pytest.importorskip("deepeval")

    from backend.tracing.deepeval_tracer import DeepEvalTracer

    tracer = DeepEvalTracer()
    tracer.configure(environment="development", sampling_rate=1.0)

    captured: list[dict] = []

    @tracer.observe(type="retriever")
    def retrieve_context(query: str) -> list[str]:
        docs = ["DeepEval captures parent-child spans automatically."]
        tracer.update_current_span(retrieval_context=docs)
        return docs

    @tracer.observe(type="agent")
    def answer(query: str) -> str:
        tracer.update_current_trace(thread_id="session-123", user_id="user-1")
        result = " ".join(retrieve_context(query))
        captured.extend(tracer.get_all_traces_dict())
        return result

    assert "DeepEval" in answer("What does @observe do?")
    assert len(captured) >= 1
