"""Convert the Choice Jini RAG workbook into the committed ``jini_cases.json`` catalog.

The workbook ``docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx`` holds the user's
authoritative agentic eval scenarios across two sheets — ``Phase1_KB_Bot`` (categories A–E,
RAG only) and ``Phase2_TopN_Bot`` (categories F–M, RAG + report/API flows). This module reads
both sheets and emits **one record per case** into :data:`OUTPUT_PATH`, each tagged with a
:class:`Scope` so the eval suite can route it to the right surface and *no case is silently
dropped*:

- ``conversational`` — LLM-judged multi-turn goldens (the existing simulator + metric stack).
- ``intent_routing`` — deterministic pass/fail ``tools_called`` assertions (category F).
- ``endpoint``       — a ``/report`` / finx-client property; asserted in ``finx-middleware-tools``
  (B / CHO-64), cross-referenced here via ``endpoint_ref`` rather than re-implemented.
- ``out_of_scope``   — a feature not built in v5 (ticket system, session keywords, async
  delivery, …); carries a one-line ``reason`` and is **not** encoded as a passing assertion.

The scope of every case is fixed by :data:`SCOPE_RULES` (the v5-capability truth table from the
change's design D3), keyed by ``test_id`` with a Phase-1 blanket default of ``conversational``.
Running the module rewrites ``jini_cases.json`` and prints a per-scope coverage summary that
totals every data row, so dropped or mis-scoped cases are visible rather than implied-covered::

    uv run python -m backend.evals.chatbot.convert_jini_cases

The workbook layout is *not* hard-coded: the header row is located by its ``Test ID`` cell, so
a re-exported workbook with shifted banner rows still converts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Repo paths — the workbook lives in docs/, the catalog next to this module.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
WORKBOOK_PATH = _REPO_ROOT / "docs" / "Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx"
OUTPUT_PATH = _THIS_DIR / "jini_cases.json"

# Sheet name -> phase tag.
_SHEETS = {"Phase1_KB_Bot": "phase1", "Phase2_TopN_Bot": "phase2"}

# The four scope tags a case can carry (a case routes to exactly one eval surface).
CONVERSATIONAL = "conversational"
INTENT_ROUTING = "intent_routing"
ENDPOINT = "endpoint"
OUT_OF_SCOPE = "out_of_scope"
SCOPES = (CONVERSATIONAL, INTENT_ROUTING, ENDPOINT, OUT_OF_SCOPE)


@dataclass(frozen=True)
class ScopeRule:
    """The scope decision for one case: the tag plus its required annotation.

    ``endpoint`` rules SHALL set ``endpoint_ref`` (the B test that covers the property);
    ``out_of_scope`` rules SHALL set ``reason``. ``note`` is free-form extra context (e.g. a
    parameter-mapping nuance) surfaced on the record for any scope.
    """

    scope: str
    endpoint_ref: str | None = None
    reason: str | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Scope rule table (design D3 — the v5-capability truth). Every Phase-2 case (F–M) is listed
# explicitly; Phase-1 cases (A–E) default to ``conversational`` via ``_DEFAULT_PHASE1``.
# ``endpoint`` refs point at the finx-middleware-tools (CHO-64) test that already asserts the
# property; where CHO-64 has no matching test the ref is flagged "(uncovered — flag CHO-64)"
# per tasks.md §5.1, rather than duplicating an httpx fixture in this package.
# --------------------------------------------------------------------------------------

_DEFAULT_PHASE1 = ScopeRule(CONVERSATIONAL)

SCOPE_RULES: dict[str, ScopeRule] = {
    # F — Intent Routing: the new agentic core, made deterministic by AgentReply.tools_called.
    # (These also feed the LLM-judged conversational sim; the intent_routing tag drives the
    # gating deterministic suite in test_intent_routing.py.)
    "F1": ScopeRule(INTENT_ROUTING),
    "F2": ScopeRule(INTENT_ROUTING),
    "F3": ScopeRule(INTENT_ROUTING),
    "F4": ScopeRule(INTENT_ROUTING),
    "F5": ScopeRule(INTENT_ROUTING),
    "F6": ScopeRule(INTENT_ROUTING),
    "F7": ScopeRule(INTENT_ROUTING),
    # G — API Transactional. G1–G3: agent signals intent (judged here) + /report executes
    # (asserted in B). G4: no status-check tool in v5. G5/G6: pure endpoint properties.
    "G1": ScopeRule(
        CONVERSATIONAL,
        endpoint_ref="backend/api/test_api.py::test_report_ledger_returns_table_payload",
        note="Agent signals report intent here; preset-range execution is a /report property.",
    ),
    "G2": ScopeRule(
        CONVERSATIONAL,
        endpoint_ref="backend/tools/test_finx.py::test_ledger_request_body_and_success",
        note="Custom-range validation + delivery is a /report + finx-client property.",
    ),
    "G3": ScopeRule(
        CONVERSATIONAL,
        endpoint_ref="backend/api/test_api.py::test_report_tax_returns_link_payload",
        note="'Send my CML' has no CML tool in v5; the no-date report family is tax_report.",
    ),
    "G4": ScopeRule(
        OUT_OF_SCOPE,
        reason="No account-opening status-check tool exists in v5.",
    ),
    "G5": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_headers_shape_with_from",
        note="Auth/session identity flows via headers; the model never sees the token.",
    ),
    "G6": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/api/test_api.py::test_report_tax_returns_link_payload",
        note="Tax returns a PDF link payload; there is no LLM summary caption in v5.",
    ),
    # H — API Error Handling. Client/endpoint properties (H2/H3/H5/H6/H8); v5 has no
    # timeout/async/partial-response UX (H1/H4/H7).
    "H1": ScopeRule(
        OUT_OF_SCOPE, reason="No timeout / infinite-spinner UX in v5 (synchronous render)."
    ),
    "H2": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/api/test_api.py::test_report_upstream_error_returns_error_payload",
    ),
    "H3": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/api/test_api.py::test_report_no_data_returns_empty_payload",
    ),
    "H4": ScopeRule(OUT_OF_SCOPE, reason="No async 'ack now, deliver later' flow in v5."),
    "H5": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_ledger_invalid_date_makes_no_request",
    ),
    "H6": ScopeRule(
        ENDPOINT,
        endpoint_ref="(uncovered — flag CHO-64: no explicit >3yr out-of-range date test)",
        note="Date-window enforcement not asserted in B; flag rather than duplicate here.",
    ),
    "H7": ScopeRule(
        OUT_OF_SCOPE, reason="No partial-response detection UX in v5 (render is all-or-nothing)."
    ),
    "H8": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_tax_report_upstream_500_does_not_raise",
        note="Invalid/expired token surfaces as a contained upstream error payload.",
    ),
    # I — Data Correctness: right client / period / segment / freshness are /report + client
    # properties using session identity and widget params, asserted in B.
    "I1": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_ledger_request_body_and_success",
        note="Client identity is bound by the session token, never a model-supplied code.",
    ),
    "I2": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_ledger_request_body_and_success",
        note="Requested period is the widget-collected date range in the request body.",
    ),
    "I3": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/api/test_api.py::test_report_ledger_returns_table_payload",
        note="Payload figures are the upstream finx response, not model-generated.",
    ),
    "I4": ScopeRule(
        ENDPOINT,
        endpoint_ref="backend/tools/test_finx.py::test_global_pnl_request_body_and_success",
        note="Segment is a widget param in the request body.",
    ),
    "I5": ScopeRule(
        ENDPOINT,
        endpoint_ref="(uncovered — flag CHO-64: no explicit as-of / freshness-date test)",
        note="Freshness/as-of disclosure not asserted in B; flag rather than duplicate here.",
    ),
    # J — Multi-intent & Loop: multi-turn agent behaviour, LLM-judged here.
    "J1": ScopeRule(CONVERSATIONAL),
    "J2": ScopeRule(CONVERSATIONAL),
    "J3": ScopeRule(CONVERSATIONAL),
    "J4": ScopeRule(
        CONVERSATIONAL, note="Cycle cap in v5 is MAX_MESSAGES (support-ticket offer at cap)."
    ),
    # K — Ticket & Handoff: v5 only *offers* a support ticket at caps; no ticket system,
    # reference numbers, dedup, or open-ticket awareness. K2 (summary quality) is the one
    # conversational property (the cap-time offer message).
    "K1": ScopeRule(OUT_OF_SCOPE, reason="No Freshdesk ticket-creation integration in v5."),
    "K2": ScopeRule(
        CONVERSATIONAL, note="v5 offers a support ticket at the cap; only the offer wording is judged."
    ),
    "K3": ScopeRule(OUT_OF_SCOPE, reason="No ticket metadata payload in v5."),
    "K4": ScopeRule(OUT_OF_SCOPE, reason="No ticket reference number returned in v5."),
    "K5": ScopeRule(OUT_OF_SCOPE, reason="No duplicate-ticket detection in v5."),
    "K6": ScopeRule(OUT_OF_SCOPE, reason="No open-ticket status lookup in v5."),
    "K7": ScopeRule(OUT_OF_SCOPE, reason="No TAT/policy messaging tied to a ticket system in v5."),
    # L — Keywords & Session: no RESTART/END keyword handling or inactivity timers in v5.
    "L1": ScopeRule(OUT_OF_SCOPE, reason="No RESTART keyword / state-reset handling in v5."),
    "L2": ScopeRule(OUT_OF_SCOPE, reason="No END keyword / feedback-prompt handling in v5."),
    "L3": ScopeRule(OUT_OF_SCOPE, reason="No keyword interception during input in v5."),
    "L4": ScopeRule(OUT_OF_SCOPE, reason="No 5-minute inactivity nudge in v5."),
    "L5": ScopeRule(OUT_OF_SCOPE, reason="No 15-minute inactivity hard-close in v5."),
    "L6": ScopeRule(OUT_OF_SCOPE, reason="No resume-after-nudge session state in v5."),
    "L7": ScopeRule(OUT_OF_SCOPE, reason="No 30-minute absolute session cap in v5."),
    # M — Regression: re-run Phase-1 KB behaviour through the post-API agent.
    "M1": ScopeRule(CONVERSATIONAL),
    "M2": ScopeRule(CONVERSATIONAL),
    "M3": ScopeRule(CONVERSATIONAL),
}


@dataclass
class JiniCase:
    """One workbook case, scope-tagged and traceable back to its Test ID."""

    test_id: str
    phase: str
    category: str
    scenario: str
    input: str
    expected_outcome: str
    severity: str
    scope: str
    endpoint_ref: str | None = None
    reason: str | None = None
    note: str | None = None
    tags: list[str] = field(default_factory=list)


def _clean(value: Any) -> str:
    """Normalise a cell to a trimmed single-spaced string (empty for ``None``)."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _expected_outcome(behaviour: Any, pass_criteria: Any) -> str:
    """Combine the workbook's Expected-behaviour and Pass-criteria columns into one string."""
    behaviour_text = _clean(behaviour)
    pass_text = _clean(pass_criteria)
    if pass_text:
        return f"{behaviour_text} Pass: {pass_text}".strip()
    return behaviour_text


def _scope_for(test_id: str, phase: str) -> ScopeRule:
    """Resolve the :class:`ScopeRule` for a case: explicit rule, else Phase-1 default."""
    if test_id in SCOPE_RULES:
        return SCOPE_RULES[test_id]
    if phase == "phase1":
        return _DEFAULT_PHASE1
    raise KeyError(
        f"No scope rule for Phase-2 case {test_id!r}; add it to SCOPE_RULES (no silent default)."
    )


def _tags_for(case_phase: str, scope: str, category: str) -> list[str]:
    """Group tags used by test_chatbot's subset filters (``phase1``/``phase2``/…)."""
    tags = [case_phase, scope]
    if scope == INTENT_ROUTING:
        tags.append("intent_routing")
    if "Multi-intent" in category or "Loop" in category:
        tags.append("multiturn")
    # De-dupe while preserving order.
    seen: dict[str, None] = {}
    for tag in tags:
        seen.setdefault(tag, None)
    return list(seen)


def _header_row(rows: list[tuple[Any, ...]]) -> int:
    """Index of the header row (its first cell is ``Test ID``); raises if absent."""
    for i, row in enumerate(rows):
        if row and _clean(row[0]).lower() == "test id":
            return i
    raise ValueError("Could not locate a 'Test ID' header row in the sheet.")


def load_cases(workbook_path: Path = WORKBOOK_PATH) -> list[JiniCase]:
    """Read both sheets of the workbook into scope-tagged :class:`JiniCase` records.

    Contract: opens ``workbook_path`` read-only, and for each sheet in :data:`_SHEETS`
    locates the ``Test ID`` header row, then reads every subsequent row with a non-empty
    Test ID into a :class:`JiniCase` (columns fixed by position: Test ID, Category, Test
    scenario, Sample input, Expected behaviour, Pass criteria, Severity). Scope comes from
    :func:`_scope_for`. Returns the cases in sheet-then-row order. Raises ``KeyError`` if a
    Phase-2 case has no scope rule.
    """
    import openpyxl

    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    cases: list[JiniCase] = []
    for sheet_name, phase in _SHEETS.items():
        worksheet = workbook[sheet_name]
        rows = list(worksheet.iter_rows(values_only=True))
        start = _header_row(rows) + 1
        for row in rows[start:]:
            cells = tuple(row) + (None,) * 7
            test_id = _clean(cells[0])
            if not test_id:
                continue
            rule = _scope_for(test_id, phase)
            cases.append(
                JiniCase(
                    test_id=test_id,
                    phase=phase,
                    category=_clean(cells[1]),
                    scenario=_clean(cells[2]),
                    input=_clean(cells[3]),
                    expected_outcome=_expected_outcome(cells[4], cells[5]),
                    severity=_clean(cells[6]),
                    scope=rule.scope,
                    endpoint_ref=rule.endpoint_ref,
                    reason=rule.reason,
                    note=rule.note,
                    tags=_tags_for(phase, rule.scope, _clean(cells[1])),
                )
            )
    workbook.close()
    return cases


def coverage_summary(cases: list[JiniCase]) -> dict[str, int]:
    """Per-scope counts plus a ``total`` — the "no silent caps" audit line."""
    summary = {scope: 0 for scope in SCOPES}
    for case in cases:
        summary[case.scope] += 1
    summary["total"] = len(cases)
    return summary


def _validate(cases: list[JiniCase]) -> None:
    """Fail loudly on the invariants the scope tags must satisfy."""
    for case in cases:
        if case.scope == ENDPOINT and not case.endpoint_ref:
            raise ValueError(f"{case.test_id}: endpoint case is missing an endpoint_ref")
        if case.scope == OUT_OF_SCOPE and not case.reason:
            raise ValueError(f"{case.test_id}: out_of_scope case is missing a reason")
    ids = [case.test_id for case in cases]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate Test IDs in workbook: {sorted(duplicates)}")


def write_catalog(
    workbook_path: Path = WORKBOOK_PATH, output_path: Path = OUTPUT_PATH
) -> list[JiniCase]:
    """Convert the workbook and write ``jini_cases.json``; returns the cases.

    Contract: ``load_cases`` → ``_validate`` → writes a JSON object
    ``{"summary": <coverage_summary>, "cases": [<record>, …]}`` (2-space indented, trailing
    newline) to ``output_path``. The ``summary`` is the committed coverage audit; ``cases``
    preserves workbook order. Returns the in-memory cases so callers can print/inspect them.
    """
    cases = load_cases(workbook_path)
    _validate(cases)
    payload = {
        "summary": coverage_summary(cases),
        "cases": [asdict(case) for case in cases],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return cases


def main() -> None:
    """CLI: rewrite ``jini_cases.json`` and print the per-scope coverage summary."""
    cases = write_catalog()
    summary = coverage_summary(cases)
    print(f"Wrote {summary['total']} cases to {OUTPUT_PATH.relative_to(_REPO_ROOT)}")
    for scope in SCOPES:
        print(f"  {scope:<15} {summary[scope]:>3}")
    print(f"  {'total':<15} {summary['total']:>3}")


if __name__ == "__main__":
    main()
