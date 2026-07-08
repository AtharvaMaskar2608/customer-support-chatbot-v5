# Design: report-intent-evals (agentic evals — Choice Jini Phase 1 + Phase 2)

## Context

`backend/evals/chatbot/` already runs DeepEval `ConversationalGolden`s through `model_callback` → `agent_reply`, scored by six conversational metrics on Confident AI (per `docs/chatbot_eval/{1,2,3}_*.md`). Two forces reshape it: the tool surface changed (five intent-only report tools, report turns end at `report_request`), and the user's agentic eval scenarios are the full Choice Jini workbook — **Phase 1 (A–E, 36 KB cases)** and **Phase 2 (F–M, 46 RAG+API cases)**.

Critically, the current `callback.py` documents its own blind spot: it infers `rag_search` from citations and "Report/clarifying tool calls are not distinguishable from `AgentReply`." That makes Phase 2 category F (intent routing: transactional vs explanation) impossible to assert today. The fix is `AgentReply.tools_called` (A adds, B populates), which this change consumes.

## Goals / Non-Goals

**Goals:**
- Both phases become runnable, traceable goldens with no case silently dropped.
- Deterministic, pass/fail intent-routing assertions (category F) via `tools_called` — the core agentic safety property.
- Honest coverage: assert what v5 actually does; explicitly tag what belongs to endpoint tests or isn't built.

**Non-Goals:**
- No live FinX calls in evals (report tools never execute in `agent_reply`; the turn ends at intent). No frontend/widget testing (C's QA). No inventing ticket/session-keyword features to satisfy K/L cases.

## Decisions

### D1 — One workbook → one tagged catalog (`jini_cases.json`), then split by scope

`convert_jini_cases.py` (openpyxl) reads both sheets (header row 3) into `jini_cases.json`, each record: `{test_id, category, phase, scenario, input, expected_outcome (Expected behaviour + Pass criteria), severity, scope}`. `scope` is assigned by a category/case rule table (D3). The JSON is the committed source of truth; evals never parse xlsx at run time. Rationale: full traceability + "no silent caps" — a coverage summary is emitted (N per scope), so dropped cases are visible, not implied-covered.

### D2 — Three eval surfaces, each fed the matching scope

1. **Conversational simulation** (existing stack, LLM-judged, report-only): all `conversational` cases — Phase 1 A–E, Phase 2 F/J/M. Single-turn KB cases run as one-turn conversational goldens; multi-intent (J) as multi-turn. Metrics unchanged (retention, completeness, relevancy, role/topic, SEBI GEval).
2. **Deterministic intent routing** (`test_intent_routing.py`, pytest, gated): `intent_routing` cases (category F). Drives `agent_reply` on a crafted single user message, asserts `tools_called`:
   - transactional ("Send me my P&L", "I need my ledger for last month") → the expected report tool, and **not** `rag_search`;
   - explanation ("What is a P&L?") → `rag_search`, and **no** report tool;
   - ambiguous / low-confidence ("P&L", garbled) → `ask_clarifying_question` (no report tool fired blindly).
   Plus the no-parameter-hallucination regex sweep on report-intent replies.
3. **Endpoint cases → cross-referenced to B** (not re-implemented here): `endpoint`-tagged cases (G auth/delivery, H error handling, I data correctness) are properties of `/report` + the finx clients — asserted in `finx-middleware-tools` mocked-httpx tests. This change records the mapping (Test ID → B test) in `jini_cases.json` so coverage is auditable across both changes without duplicating fixtures in the eval package.

### D3 — Scope rule table (v5 capability truth)

| Category / cases | scope | Why |
|---|---|---|
| A–E (Phase 1) | `conversational` | RAG KB behavior — the existing suite |
| F1–F7 Intent Routing | `intent_routing` (+`conversational` for the judged dialogue) | The new agentic core; `tools_called` makes it deterministic |
| G1–G3 report transactional | `conversational` (intent) + `endpoint` (execution) | Agent signals intent (asserted here); `/report` executes (asserted in B). G3 "no date" case retargets CML→`tax_report` |
| G4 account-opening status | `out_of_scope` | No status-check tool in v5 |
| G5 auth propagation, G6 PDF+summary | `endpoint` | `/report` uses `finx_session_id`; tax returns a link (no LLM summary now) — B tests |
| H1–H8 API error handling | `endpoint` (H2/H3/H5/H6/H8) · `out_of_scope` (H1 timeout, H4 async, H7 partial) | Error→`ReportRenderPayload(error/empty)` is a client/endpoint property; no async/timeout UX in v5 |
| I1–I5 data correctness | `endpoint` | Right client/period/segment is `/report` using session identity + widget params — B tests |
| J1–J4 multi-intent & loop | `conversational` | Multi-turn agent behavior; J4 cycle cap = MAX_MESSAGES |
| K1–K7 ticket & handoff | `out_of_scope` (K2 summary → `conversational` note) | v5 only *offers* a support ticket at caps; no ticket system/reference/dedup |
| L1–L7 keywords & session | `out_of_scope` | No RESTART/END/inactivity handling in v5 |
| M1–M3 regression | `conversational` | Re-run Phase 1 through the post-API agent |

### D4 — `callback.py` reads `tools_called` from `AgentReply`

Replace citation-inference with `reply.tools_called`, emitting a `ToolCall` per name. This makes the simulator's `tools_called` faithful for report and clarifying turns, not just `rag_search`. Keeps `retrieval_context` behavior for the RAG metrics.

## Risks / Trade-offs

- [Report turns end at `report_request`, so a report golden's assistant turn is short] → conversational expected outcomes describe intent-signaling ("offers the ledger options"), and the deterministic `tools_called` check carries the real weight.
- [Endpoint cases live in B, not here] → cross-reference in `jini_cases.json` keeps one auditable map; avoids duplicating httpx fixtures and a file-ownership conflict.
- [Out-of-scope cases could look like coverage gaps] → they are tagged with an explicit reason and surfaced in the coverage summary, so "not built in v5" is documented, not hidden.
- [Eval cost grows (~70+ conversational goldens)] → tags (`phase1`, `phase2`, `intent_routing`) let CI run subsets; the deterministic intent-routing suite is cheap and is the gating one.
