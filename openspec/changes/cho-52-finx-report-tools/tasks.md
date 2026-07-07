## 1. Clients

- [ ] 1.1 `backend/tools/finx.py`: `cml_report(session, client_id) -> ReportResult` calling `POST {FINX_CML_BASE_URL}/mis/reports/generate`.
- [ ] 1.2 `contract_note(session, mobile_no, contract_date) -> ReportResult` calling `POST {FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate`.
- [ ] 1.3 Shared header builder `{Authorization, authType: jwt, source: FINX_WEB}` from `session.session_token`.
- [ ] 1.4 Defensive: validate `contract_date` matches `DD-MM-YYYY`; invalid → `ReportResult(ok=False,...)` without a network call.

## 2. Error isolation

- [ ] 2.1 Wrap both calls: network error / timeout / non-2xx → `ReportResult(ok=False, error=...)`; never raise.

## 3. Anthropic tool schemas (intent-only)

- [ ] 3.1 `backend/tools/schemas.py`: `CML_REPORT_TOOL` and `CONTRACT_NOTE_TOOL` with **empty data input schemas** (no `client_id`/`mobile_no`/`contract_date` properties) — a model tool call signals intent; params are widget-supplied.

## 4. Done condition

- [ ] 4.1 `openspec validate finx-report-tools --strict` passes.
- [ ] 4.2 Test: mocked httpx transport asserts success → `ok=True`, injected 500/timeout → `ok=False` (no exception), and bad date → `ok=False` with no request. `pytest backend/tools`.
