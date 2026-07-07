"""Per-message cost accounting in INR from Anthropic token usage.

The agent loop reports cost in rupees. Anthropic bills per input/output token in USD at
per-model rates; this module converts a call's token counts to INR using a per-model USD
rate table times a configurable USD->INR rate (``USD_INR_RATE`` env var, default below).
:func:`build_usage` folds a single message's cost into a running cumulative total so the
``usage`` SSE frame can carry both the per-message ``cost_inr`` and ``cumulative_cost_inr``.
"""

from __future__ import annotations

import os

from backend.contracts.models import Usage

# Per-model Anthropic list price in USD per 1M tokens as ``(input, output)``. Kept as a
# small, overridable table; an unknown model falls back to the Sonnet tier so cost is
# always an estimate rather than zero. Prices are public list prices, not secrets.
_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_USD_PER_MTOK: tuple[float, float] = (3.0, 15.0)

# Fallback USD->INR conversion when ``USD_INR_RATE`` is unset. A rate, not a secret.
_DEFAULT_USD_INR = 88.0


def usd_inr_rate() -> float:
    """Return the active USD->INR rate (``USD_INR_RATE`` env override, else the default).

    Read at call time so a deployment can tune the rate without a code change; a malformed
    value falls back to the default rather than raising mid-turn.
    """
    raw = os.environ.get("USD_INR_RATE")
    if not raw:
        return _DEFAULT_USD_INR
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_USD_INR


def message_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in INR for one message's ``input_tokens``/``output_tokens`` under ``model``.

    Contract: ``(input_tokens * in_rate + output_tokens * out_rate) / 1e6 * usd_inr_rate()``,
    where the per-model USD/MTok rates come from :data:`_USD_PER_MTOK` (Sonnet tier for an
    unknown model). Always non-negative; zero tokens yield ``0.0``.
    """
    in_rate, out_rate = _USD_PER_MTOK.get(model, _DEFAULT_USD_PER_MTOK)
    usd = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return usd * usd_inr_rate()


def build_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    prior_cost_inr: float = 0.0,
) -> Usage:
    """Assemble a :class:`Usage` for one message and roll it into the running total.

    Contract: computes this message's ``cost_inr`` via :func:`message_cost_inr` and sets
    ``cumulative_cost_inr = prior_cost_inr + cost_inr``. ``prior_cost_inr`` is the
    conversation's cumulative cost before this message (0 on the first turn); the caller
    threads the returned ``cumulative_cost_inr`` back in as ``prior_cost_inr`` next turn.
    """
    cost = message_cost_inr(model, input_tokens, output_tokens)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_inr=cost,
        latency_ms=latency_ms,
        cumulative_cost_inr=prior_cost_inr + cost,
    )
