# Parallelization plan — FinX middleware reports sprint (2026-07-08)

Parent: **CHO-62**. Four changes, each with a Linear issue and an OpenSpec change dir:

| # | Linear | OpenSpec change |
|---|---|---|
| A | CHO-63 | `cho-63-finx-reports-contracts` |
| B | CHO-64 | `cho-64-finx-middleware-tools` |
| C | CHO-65 | `cho-65-frontend-report-widgets` |
| D | CHO-66 | `cho-66-report-intent-evals` |

## File-touch matrix (conflict basis)

| Change | Files |
|---|---|
| A | `backend/contracts/models.py`, `backend/contracts/events.py`, `backend/config/settings.py`, contract tests |
| B | `backend/tools/finx.py`, `backend/tools/schemas.py`, `backend/agent/{tools,loop,prompt}.py`, `backend/api/routes.py`, backend tests, **+ cleanup edits to A's `events.py`/`settings.py`** |
| C | `frontend/index.html`, `frontend/js/app.js`, `frontend/css/`, `frontend/tailwind.config.js` |
| D | `backend/evals/chatbot/` (goldens, converter, runner), reads `docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx` |

## Known overlaps (surfaced per workflow rules)

- **A ↔ B** on `backend/contracts/events.py` and `backend/config/settings.py` (B removes the legacy shapes A deliberately left in place). Resolved by hard sequencing: B starts only after A merges to `main`.
- **B ↔ C**: zero shared files; both build against A's landed contracts (`report_request.steps`, `ReportRenderPayload`, `Session.finx_session_id`). C's final end-to-end QA task (5.3) needs B's `/report` live — it is C's last task, after B lands.
- **A → B → D on `AgentReply.tools_called`**: A adds the field (additive), B populates it in the loop, D asserts on it for intent-routing (Phase 2 category F). Threads cleanly through the batch order; no shared-file conflict (each change owns its file).
- **B ↔ D**: no shared files, but D asserts B's runtime behavior (`tools_called`, new tool names, terminal report turn) → D sequenced after B.
- **CHO-61** spans B (backend: `done` after `report_request`) and C (frontend: centralized terminal handling) — independent halves, no file overlap.
- Nobody touches lockfiles, migrations, or root config; `settings.py` edits are explicitly assigned (A adds, B removes).

## Batches

```
Batch 1:  A (CHO-63) finx-reports-contracts            → merge to main
Batch 2:  B (CHO-64) finx-middleware-tools   ∥   C (CHO-65) frontend-report-widgets
Batch 3:  D (CHO-66) report-intent-evals  +  C task 5.3 (joint E2E QA)
```

## Done conditions / test commands

- A: `uv run pytest backend/tests` (additive-only; zero regressions)
- B: `uv run pytest backend/tests` (mocked-httpx client tests, loop ordering + `tools_called`, `/report` JSON, no legacy refs)
- C: `/browse` QA checklist (widgets, login, CHO-61) with stubbed `/report`; joint E2E after B
- D: deterministic pytest (intent routing via `tools_called`, no-param-hallucination) + full DeepEval simulation over **both** Phase 1 and Phase 2 goldens reporting to Confident AI

## Linear mapping

- CHO-62 parent · CHO-63 A · CHO-64 B · CHO-65 C · CHO-66 D
- CHO-61 (stuck "Generating answer…") → B task 3.1 + C tasks 4.x
- CHO-60 (more test cases) → D (Phase 1 + Phase 2 of `Choice_Jini_RAG_TestCases`)
