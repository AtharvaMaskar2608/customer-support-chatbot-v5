"""Serialize the agent's ``SSEEvent`` stream into ``sse-starlette`` frames.

Each :class:`~backend.contracts.events.SSEEvent` becomes one SSE frame whose **event name
is the frame's ``type``** (``status``, ``token``, ``citations``, ``usage``,
``report_request``, ``done``, ``error``) and whose ``data`` is the event's JSON body. The
:func:`sse_stream` adapter also guarantees the connection ends with a terminal ``error``
frame if the underlying agent iterator raises, rather than dropping mid-stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from backend.contracts.events import ErrorEvent


def to_sse_frame(event: Any) -> dict[str, str]:
    """Serialize one ``SSEEvent`` into an ``sse-starlette`` frame dict.

    Contract: returns ``{"event": <event.type>, "data": <event.model_dump_json()>}`` — the
    SSE event name mirrors the discriminator so the client can dispatch on frame type, and
    the payload is the full event JSON.
    """
    return {"event": event.type, "data": event.model_dump_json()}


async def sse_stream(events: AsyncIterator[Any]) -> AsyncIterator[dict[str, str]]:
    """Adapt an ``SSEEvent`` async iterator into a stream of ``sse-starlette`` frames.

    Contract: yields one frame per event via :func:`to_sse_frame`. If iterating ``events``
    raises, emits a single terminal ``error`` frame (client-safe message) instead of
    letting the exception drop the connection — so every stream ends with a ``done`` or an
    ``error`` frame.
    """
    try:
        async for event in events:
            yield to_sse_frame(event)
    except Exception as exc:  # defensive: never leak a raw disconnect to the client
        yield to_sse_frame(ErrorEvent(message=f"stream failed: {exc.__class__.__name__}"))
