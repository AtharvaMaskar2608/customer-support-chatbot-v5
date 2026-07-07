"""Startup registration of the concrete tracer — the composition root's single call.

``init_tracing(settings)`` is called once at application startup (API ``main.py`` / agent
bootstrap). When tracing is enabled and a Confident AI key is present, it constructs the
DeepEval-backed tracer, configures it, and registers it via foundations' ``set_tracer``;
otherwise the no-op default stays in place. Keeping registration here (never in
foundations) preserves the dependency direction P3 → P0. The ``deepeval`` import is
deferred into the enabled branch so the no-op path never imports ``deepeval``.
"""

from __future__ import annotations

from backend.config.settings import Settings
from backend.tracing.interface import Tracer, set_tracer


def init_tracing(settings: Settings) -> Tracer:
    """Register the active tracer from settings and return it.

    Contract: if ``settings.tracing_enabled`` is true **and** ``settings.confident_api_key``
    is set, construct a :class:`~backend.tracing.deepeval_tracer.DeepEvalTracer`, call
    ``configure(...)`` on it, register it via ``set_tracer``, and return it. Otherwise leave
    the foundations no-op tracer active and return it unchanged. Idempotent — safe to call
    once at startup. Never raises for a disabled/unconfigured setup.
    """
    if not (settings.tracing_enabled and settings.confident_api_key):
        return _current_tracer()

    # Deferred import: the no-op path above must not import ``deepeval``.
    from backend.tracing.deepeval_tracer import DeepEvalTracer

    tracer = DeepEvalTracer()
    tracer.configure(
        confident_api_key=settings.confident_api_key,
        environment="development",
        sampling_rate=1.0,
    )
    set_tracer(tracer)
    return tracer


def _current_tracer() -> Tracer:
    """Return the currently registered tracer (the no-op default unless swapped)."""
    from backend.tracing.interface import get_tracer

    return get_tracer()
