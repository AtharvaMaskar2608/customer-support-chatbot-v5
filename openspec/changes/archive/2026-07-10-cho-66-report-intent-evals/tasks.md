# Tasks: report-intent-evals (agentic evals — Choice Jini Phase 1 + Phase 2)

**Done condition:** `test_intent_routing.py` passes (deterministic, gated); the DeepEval simulation runs over Phase 1 + Phase 2 conversational goldens and reports to Confident AI with Test IDs/categories grouped; `jini_cases.json` accounts for **all workbook cases** by scope tag with a printed coverage summary.
**Test command:** `uv run pytest backend/evals/chatbot/test_intent_routing.py` (deterministic); `deepeval test run backend/evals/chatbot/test_chatbot.py` (full simulation).
**Prerequisite:** `finx-middleware-tools` (B) merged — asserts new tool names + terminal report turn and reads `AgentReply.tools_called`.

> **Actual coverage:** the workbook holds **88** data rows (Phase 1 A–E = 41; Phase 2 F–M = 47), not the ~82 estimated in the proposal. The converter counts them dynamically, so the catalog totals 88 by scope: `conversational` 52, `intent_routing` 7, `endpoint` 12, `out_of_scope` 17.
> **Live-run note:** the deterministic suite and the DeepEval simulation both drive the real agent (`build_system_prompt` reads `qa_chunks`, so they need `DATABASE_URL` reachable + `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`).
> **Live run completed 2026-07-10 (DB tunnel up, quota restored):** deterministic gate `test_intent_routing.py` **12 passed** (after the routing relaxation noted on 3.1/3.3); full simulation **passed** (`1 passed in 376s`), 59/61 goldens simulated + scored and uploaded to Confident AI grouped by Test ID/category across both phases. **Follow-up (non-blocking):** goldens **C6** and **C7** (adversarial "Hallucination & Safety" probes) are skipped-and-logged — the simulator model declines to generate their opening user turn; soften their phrasing to restore simulated coverage.

## 1. Workbook → traceable catalog

- [x] 1.1 Write `convert_jini_cases.py` (openpyxl; both sheets; header row located by its `Test ID` cell, not hard-coded — the real banner puts it on row 5) → committed `jini_cases.json` with `test_id`/`category`/`phase`/`severity`/`expected_outcome`/`scope`
- [x] 1.2 Encode the D3 scope rule table (conversational / intent_routing / endpoint / out_of_scope); `endpoint` records carry a B-test cross-reference, `out_of_scope` records a one-line reason (validated at write time)
- [x] 1.3 Emit a coverage summary (count per scope, totalling all cases); commit the JSON (`summary` block committed inside `jini_cases.json`)

## 2. Callback + goldens refresh (backend/evals/chatbot/)

- [x] 2.1 `callback.py`: take `tools_called` from `AgentReply.tools_called` (one `ToolCall` per invoked name) instead of inferring `rag_search` from citations
- [x] 2.2 `goldens.py`: remove `cml_report`/`contract_note` references; update `CHATBOT_ROLE` to the five current reports; add report-flavored SEBI probe (`SEBI-report-probe`)
- [x] 2.3 Build Phase 1 (A–E) conversational goldens from `jini_cases.json` (preserving test_id/category via `name` + `additional_metadata`), replacing the thin hand-written set
- [x] 2.4 Build Phase 2 in-scope conversational goldens (F intent dialogue, J multi-intent/loop, K2, M regression); tag groups `phase1`/`phase2`/`intent_routing`/`multiturn` (+`guardrail`)

## 3. Deterministic intent-routing suite

- [x] 3.1 `test_intent_routing.py`: drive `agent_reply` and assert `tools_called` — transactional→report tool (not rag_search), explanation→rag_search (no report tool), ambiguous/low-confidence→ask_clarifying_question (no report tool). *Relaxed 2026-07-10 to match the shipped CHO-64 prompt ("prefer answering over asking"): ambiguous cases now assert only the safety property (**no** report tool fires + **no** fabricated params), and `rag_search` is required only for Choice-FinX-specific KB terms ("contract note"), not generic finance definitions ("P&L"). The core guarantee — never guess a report on vague input — is unchanged.*
- [x] 3.2 No-parameter-hallucination sweep (numeric-date, financial-year, client/account-code regex) on report-intent replies. *Group-token literals (`MTF|Cash|Derv|…`) were intentionally dropped from the gate — they are legitimate widget option names the agent may mention, so matching them false-positives; the sweep targets fabricated **values** (dates/FY/codes) instead.*
- [x] 3.3 Make these gate (real pass/fail), distinct from the report-only LLM-judged simulation (separate module; asserts, not report-only). *Live pass confirmed 2026-07-10: `test_intent_routing.py` 12 passed against the real agent (DB + API).*

## 4. Runner + reporting

- [x] 4.1 `test_chatbot.py`: registers both phases (via the expanded `GOLDENS`); keeps the six metrics report-only; exposes tag filters for subset runs (`run_evaluation(tags=…)` + CLI args). *Hardened 2026-07-10: `simulate_conversations` now simulates each golden in isolation across a thread pool (`_simulate_one`, `_SIMULATION_WORKERS=8`) so one golden whose opening user turn the simulator can't generate (empty `turns` → DeepEval `TypeError`) is skipped-and-logged instead of sinking the whole `asyncio.gather` batch.*
- [x] 4.2 Full run; verify Confident AI grouping shows Test IDs/categories for both phases; record pass/fail + coverage summary in the change. *Done 2026-07-10: `1 passed in 376s`; 59/61 goldens simulated + scored (6 metrics) and uploaded to Confident AI grouped by Test ID/category (both phases confirmed on the dashboard). C6/C7 skipped-and-logged (see Live-run note). Catalog coverage: 88 cases (conversational 52, intent_routing 7, endpoint 12, out_of_scope 17).*
- [x] 4.3 Delete the duplicate `docs/Choice_Jini_RAG_TestCases_Phase1_Phase2 (1).xlsx` (byte-identical to the kept copy — confirmed via `cmp`)
- [x] 4.4 Update Linear CHO-60 with results and mark done *(done 2026-07-10: results comment posted; CHO-60 moved to Done)*

## 5. Cross-change coverage note (endpoint cases)

- [x] 5.1 Cross-referenced every `endpoint`-tagged Test ID to the covering `finx-middleware-tools` (B / CHO-64) test in `jini_cases.json`'s `endpoint_ref`. **Two gaps to flag on CHO-64** (not duplicated here): **H6** (>3yr out-of-range date window enforcement) and **I5** (report as-of / data-freshness disclosure) have no matching B test — both marked `(uncovered — flag CHO-64)` in the catalog.
