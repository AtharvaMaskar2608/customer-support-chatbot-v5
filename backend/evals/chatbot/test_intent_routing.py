"""Deterministic (pass/fail) intent-routing assertions for Phase 2 category F.

Unlike the LLM-judged conversational simulation in :mod:`.test_chatbot` (report-only, never
gated on judge noise), these tests are **gating**: they drive one real agent turn via
:func:`~backend.agent.loop.agent_reply` and assert the concrete tool path the turn took, read
from :attr:`AgentReply.tools_called`. That attribute is what makes routing evaluable — the
turn records every tool it invoked (``rag_search``, a report tool, ``ask_clarifying_question``)
even though report tools are intent-only and never execute.

The safety properties asserted (the change's core agentic guarantee):

- **Transactional** ("Send me my P&L") routes to the matching report tool and **not**
  ``rag_search``.
- **Explanation** ("What is a P&L?") routes to ``rag_search`` and fires **no** report tool.
- **Ambiguous / low-confidence** ("P&L", a garbled request) never guesses a report — **no**
  report tool fires and **no** parameters are fabricated. Whether the agent clarifies via the
  ``ask_clarifying_question`` tool or answers conversationally (the shipped prompt prefers
  answering) is not gated; only the safety property is.
- **No parameter hallucination**: a report-intent reply's text contains no fabricated report
  parameters (concrete dates, financial years, client/account codes) — those are collected by
  the secure widget, never invented by the model.

Requires ``ANTHROPIC_API_KEY`` (the agent) + ``OPENAI_API_KEY`` + ``DATABASE_URL`` (the
explanation cases run ``rag_search``); missing credentials skip the module. Live API calls.
"""

from __future__ import annotations

import re

import pytest

from backend.agent.tools import REPORT_WIDGETS
from backend.config.settings import get_settings
from backend.contracts.models import AgentReply
from backend.evals.chatbot.callback import TEST_SESSION

# The five intent-only report tool names.
REPORT_TOOLS = frozenset(REPORT_WIDGETS)


def _require_env() -> None:
    """Skip the calling test unless agent + retrieval credentials are available."""
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - config missing
        pytest.skip(f"settings unavailable: {exc}")
    if not (settings.anthropic_api_key and settings.openai_api_key and settings.database_url):
        pytest.skip("ANTHROPIC_API_KEY / OPENAI_API_KEY / DATABASE_URL not configured")


def _reply(message: str) -> AgentReply:
    """Drive one real agent turn on a single user ``message`` and return the reply."""
    from backend.agent.loop import agent_reply

    return agent_reply(TEST_SESSION, [{"role": "user", "content": message}])


def _report_tools_in(reply: AgentReply) -> set[str]:
    """The report tool names the reply invoked."""
    return {name for name in reply.tools_called if name in REPORT_TOOLS}


# --------------------------------------------------------------------------------------
# Transactional routing — a clear report request fires the matching report tool, not RAG.
# Inputs are deliberately parameter-free so the reply has no legitimate date/FY/code to echo
# (which the no-hallucination sweep then relies on).
# --------------------------------------------------------------------------------------

# (test_id, message, acceptable report tools) — a P&L request may map to global or detailed.
TRANSACTIONAL_CASES = [
    ("F1", "Send me my P&L", {"global_pnl", "detailed_pnl"}),
    ("F5", "I want my account ledger statement", {"ledger"}),
    ("F1-cn", "Send me my contract notes", {"contract_notes"}),
    ("F1-tax", "I need my tax report", {"tax_report"}),
]


@pytest.mark.parametrize(
    "message,expected", [(m, e) for _, m, e in TRANSACTIONAL_CASES],
    ids=[tid for tid, _, _ in TRANSACTIONAL_CASES],
)
def test_transactional_routes_to_report_tool(message: str, expected: set[str]) -> None:
    """A transactional report request fires a matching report tool and not ``rag_search``."""
    _require_env()
    reply = _reply(message)
    report_tools = _report_tools_in(reply)
    assert report_tools & expected, (
        f"{message!r} should fire one of {expected}, got tools_called={reply.tools_called}"
    )
    assert "rag_search" not in reply.tools_called, (
        f"{message!r} should not route to rag_search; got {reply.tools_called}"
    )


# --------------------------------------------------------------------------------------
# Explanation routing — a definition question fires rag_search and no report tool.
# --------------------------------------------------------------------------------------

# (test_id, message, requires_rag) — a definitional question must never fire a report tool.
# Grounding via ``rag_search`` is *required* only for Choice-FinX-specific terms that live in
# the KB (e.g. "contract note"); generic finance definitions ("what is a P&L?") may be answered
# from the model's own knowledge, so RAG is preferred there but not gated.
EXPLANATION_CASES = [
    ("F2", "What is a P&L?", False),
    ("F2-cn", "What is a contract note?", True),
]


@pytest.mark.parametrize(
    "message,requires_rag", [(m, r) for _, m, r in EXPLANATION_CASES],
    ids=[tid for tid, _, _ in EXPLANATION_CASES],
)
def test_explanation_does_not_report(message: str, requires_rag: bool) -> None:
    """A definitional request fires no report tool; Choice-specific terms also ground via RAG."""
    _require_env()
    reply = _reply(message)
    assert not _report_tools_in(reply), (
        f"{message!r} should not fire a report tool; got {reply.tools_called}"
    )
    if requires_rag:
        assert "rag_search" in reply.tools_called, (
            f"{message!r} is a Choice-FinX KB term and should ground via rag_search; "
            f"got {reply.tools_called}"
        )


# --------------------------------------------------------------------------------------
# Ambiguous / low-confidence — never guess a report. The critical safety property is that no
# report tool fires blindly and no parameters are fabricated; whether the agent clarifies via
# the tool or answers conversationally (the shipped prompt prefers answering) is not gated.
# --------------------------------------------------------------------------------------

AMBIGUOUS_CASES = [
    ("F3", "P&L"),
    ("F7", "hmm the report thing you know"),
]


@pytest.mark.parametrize(
    "message", [m for _, m in AMBIGUOUS_CASES], ids=[tid for tid, _ in AMBIGUOUS_CASES]
)
def test_ambiguous_does_not_guess_report(message: str) -> None:
    """An ambiguous request fires no report tool and fabricates no report parameters."""
    _require_env()
    reply = _reply(message)
    assert not _report_tools_in(reply), (
        f"ambiguous {message!r} must not fire a report tool blindly; got {reply.tools_called}"
    )
    hits = _hallucinated_params(reply.text)
    assert not hits, (
        f"ambiguous {message!r} fabricated report parameters {hits} in reply: {reply.text!r}"
    )


# --------------------------------------------------------------------------------------
# No parameter hallucination — a report-intent reply invents no report parameters.
# --------------------------------------------------------------------------------------

# Patterns for values the model must never fabricate (they come from the widget). Kept to
# high-confidence fabrication classes so mentioning that options exist ("pick the segment and
# date range in the widget") is not flagged.
_HALLUCINATION_PATTERNS = {
    "numeric date": re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
    "financial year": re.compile(r"\bFY\s?\d{2,4}\b|\b20\d{2}\s?[-/]\s?\d{2,4}\b", re.IGNORECASE),
    "client/account code": re.compile(r"\b[A-Z]{1,4}\d{4,}\b|\b\d{6,}\b"),
}


def _hallucinated_params(text: str) -> dict[str, str]:
    """Map each fabrication class to the first offending match found in ``text`` (if any)."""
    hits: dict[str, str] = {}
    for label, pattern in _HALLUCINATION_PATTERNS.items():
        match = pattern.search(text)
        if match:
            hits[label] = match.group(0)
    return hits


@pytest.mark.parametrize(
    "message,expected", [(m, e) for _, m, e in TRANSACTIONAL_CASES],
    ids=[tid for tid, _, _ in TRANSACTIONAL_CASES],
)
def test_report_intent_reply_has_no_fabricated_params(message: str, expected: set[str]) -> None:
    """A report-intent reply's text contains no fabricated dates, FYs, or client codes."""
    _require_env()
    reply = _reply(message)
    # Only meaningful when the turn actually signalled a report.
    assert _report_tools_in(reply) & expected, (
        f"{message!r} did not signal the expected report tool; got {reply.tools_called}"
    )
    hits = _hallucinated_params(reply.text)
    assert not hits, f"{message!r} fabricated report parameters {hits} in reply: {reply.text!r}"
