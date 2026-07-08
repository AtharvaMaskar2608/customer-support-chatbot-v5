# Tasks: report-intent-evals (agentic evals — Choice Jini Phase 1 + Phase 2)

**Done condition:** `test_intent_routing.py` passes (deterministic, gated); the DeepEval simulation runs over Phase 1 + Phase 2 conversational goldens and reports to Confident AI with Test IDs/categories grouped; `jini_cases.json` accounts for all 82 workbook cases by scope tag with a printed coverage summary.
**Test command:** `uv run pytest backend/evals/chatbot/test_intent_routing.py` (deterministic); `deepeval test run backend/evals/chatbot/test_chatbot.py` (full simulation).
**Prerequisite:** `finx-middleware-tools` (B) merged — asserts new tool names + terminal report turn and reads `AgentReply.tools_called`.

## 1. Workbook → traceable catalog

- [ ] 1.1 Write `convert_jini_cases.py` (openpyxl; both sheets, header row 3) → committed `jini_cases.json` with `test_id`/`category`/`phase`/`severity`/`expected_outcome`/`scope`
- [ ] 1.2 Encode the D3 scope rule table (conversational / intent_routing / endpoint / out_of_scope); `endpoint` records carry a B-test cross-reference, `out_of_scope` records a one-line reason
- [ ] 1.3 Emit a coverage summary (count per scope, totalling all cases); commit the JSON

## 2. Callback + goldens refresh (backend/evals/chatbot/)

- [ ] 2.1 `callback.py`: take `tools_called` from `AgentReply.tools_called` instead of inferring `rag_search` from citations
- [ ] 2.2 `goldens.py`: remove `cml_report`/`contract_note` references; update `CHATBOT_ROLE` to the five current reports; add report-flavored SEBI probe
- [ ] 2.3 Build Phase 1 (A–E) conversational goldens from `jini_cases.json` (preserving test_id/category), replacing/merging the thin existing set
- [ ] 2.4 Build Phase 2 in-scope conversational goldens (F intent dialogue, J multi-intent/loop, M regression); tag groups `phase1`/`phase2`/`intent_routing`/`multiturn`

## 3. Deterministic intent-routing suite

- [ ] 3.1 `test_intent_routing.py`: per category-F case, drive `agent_reply` and assert `tools_called` — transactional→report tool (not rag_search), explanation→rag_search (no report tool), ambiguous/low-confidence→ask_clarifying_question
- [ ] 3.2 No-parameter-hallucination sweep (date regex, group tokens `MTF|Cash|Derv|Group1|Group23`, client-code pattern, FinYear) on report-intent replies
- [ ] 3.3 Make these gate (real pass/fail), distinct from the report-only LLM-judged simulation

## 4. Runner + reporting

- [ ] 4.1 `test_chatbot.py`: register both phases; keep the six metrics report-only; expose tag filters for subset runs
- [ ] 4.2 Full run; verify Confident AI grouping shows Test IDs/categories for both phases; record pass/fail + coverage summary in the change
- [ ] 4.3 Delete the duplicate `docs/Choice_Jini_RAG_TestCases_Phase1_Phase2 (1).xlsx` (byte-identical to the kept copy)
- [ ] 4.4 Update Linear CHO-60 with results and mark done

## 5. Cross-change coverage note (endpoint cases)

- [ ] 5.1 Confirm the `endpoint`-tagged Test IDs (G auth/delivery, H2/H3/H5/H6/H8 errors, I data-correctness) are asserted in `finx-middleware-tools` (B) mocked-httpx `/report` + client tests; if any is uncovered there, flag it on CHO-64 rather than duplicating fixtures here
