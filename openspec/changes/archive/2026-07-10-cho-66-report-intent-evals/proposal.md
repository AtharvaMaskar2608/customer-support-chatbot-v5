# Proposal: report-intent-evals (agentic evals — Choice Jini Phase 1 + Phase 2)

## Why

The agent's tool surface changes completely (five intent-only report tools, results bypassing the LLM), and the user's authoritative agentic eval scenarios are the **Choice Jini RAG test cases** (`docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx`): **Phase 1** (`Phase1_KB_Bot`, categories A–E, 41 cases — RAG only) and **Phase 2** (`Phase2_TopN_Bot`, categories F–M, 47 cases — RAG + report/API agentic flows). This change turns **both phases** into the DeepEval-style agentic eval suite already scaffolded under `backend/evals/chatbot/` (the `ConversationSimulator` + `model_callback` + metric stack from `docs/chatbot_eval/`), and adds deterministic intent-routing assertions the current harness cannot express. Implements Linear **CHO-60**.

## What Changes

- **Single source of truth:** convert the whole workbook into a committed `jini_cases.json` — one record per case preserving `test_id`, `category`, `severity`, and a `scope` tag (`conversational` | `intent_routing` | `endpoint` | `out_of_scope`), so no case is silently dropped and every one is traceable.
- **Phase 1 (A–E) → conversational goldens** run through the existing simulator + six-metric stack (retention, completeness, relevancy, role/topic adherence, SEBI GEval).
- **Phase 2 in-scope conversational (F Intent Routing, J Multi-intent & Loop, M Regression) → conversational goldens** on the same stack.
- **Deterministic intent-routing assertions (category F):** using the new `AgentReply.tools_called` (added in A, populated in B), assert transactional phrasings route to the correct report tool, explanation phrasings route to `rag_search`, and ambiguous/low-confidence phrasings route to `ask_clarifying_question` — pass/fail pytest, not LLM-judged.
- **No-parameter-hallucination sweep** on report-intent replies (no fabricated dates, group tokens, client codes, FinYears).
- **Retire dead references:** update existing goldens that name `cml_report`/`contract_note`; `CHATBOT_ROLE` reflects the five new reports.
- **Honest scope mapping for the rest:** categories whose behavior is a `/report` endpoint property, not a conversational one — **G (transactional delivery/auth), H (API error handling), I (data correctness)** — are tagged `endpoint` and cross-referenced to the `finx-middleware-tools` (B) client + `/report` test suite (mocked httpx), where the same Test IDs are asserted. Categories describing features **not built in v5 — K (ticket system/reference/dedup), L (RESTART/END/inactivity keywords), and specific cases G4 (account-opening status), H1/H4 (timeout/async)** — are tagged `out_of_scope` with a one-line reason and **not** encoded as passing assertions.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `chatbot-multiturn-evals`: golden set grows to Phase 1 + Phase 2 in-scope cases; adds deterministic intent-routing + no-parameter-hallucination assertions; documents the endpoint/out-of-scope tagging.

## Impact

- **Files touched (exclusively assigned to this change):** `backend/evals/chatbot/` (`goldens.py`, `callback.py`, `test_chatbot.py`, new `convert_jini_cases.py`, committed `jini_cases.json` + `phase1_goldens.json`), and a new deterministic `test_intent_routing.py`. Reads the committed xlsx in `docs/`.
- **Depends on:** `finx-middleware-tools` (B) merged — evals assert the new tool names, terminal report turn, and read `AgentReply.tools_called`. Transitively depends on A.
- **`callback.py` fix:** today it can only infer `rag_search` from citations and explicitly cannot see report/clarifying tool calls; it will read `AgentReply.tools_called` instead, which is what makes category-F intent routing evaluable.
- **Linear:** implements CHO-60 (both phases).
- **Done condition:** `uv run pytest backend/evals/chatbot/test_intent_routing.py` passes (deterministic); the full DeepEval simulation runs over Phase 1 + Phase 2 conversational goldens and reports to Confident AI with Test IDs/categories grouped; `jini_cases.json` accounts for all 88 workbook cases by scope tag (52 conversational / 7 intent_routing / 12 endpoint / 17 out_of_scope).
