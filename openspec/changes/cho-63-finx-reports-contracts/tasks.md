# Tasks: finx-reports-contracts

**Done condition:** `uv run pytest backend/tests` green; all additions importable; no existing constructor or test broken (additive-only).
**Test command:** `uv run pytest backend/tests`

## 1. Widget-step and report-request contracts (backend/contracts/events.py)

- [ ] 1.1 Add frozen `CardOption(label, value)`, `CardStep(kind="cards", param, options)`, `DateRangeStep(kind="date_range", from_param="from_date", to_param="to_date")`, and the `WidgetStep` discriminated union (on `kind`)
- [ ] 1.2 Extend `ReportRequestEvent`: `report_type` Literal grows to `ledger | global_pnl | detailed_pnl | contract_notes | tax_report | cml | contract_note`; add `steps: list[WidgetStep] = []`; keep `fields: list[str]` defaulted to `[]` (legacy, slated for removal in finx-middleware-tools)

## 2. Render-payload and session contracts (backend/contracts/models.py)

- [ ] 2.1 Add frozen `ReportColumn(key, label)` and `ReportRenderPayload(kind: Literal["table","link","empty","error"], title, columns=(), rows=(), url=None, message=None)` with docstring noting report URLs must never enter model context
- [ ] 2.2 Add `Session.finx_session_id: str = ""` with docstring distinguishing it from the legacy JWT `session_token`
- [ ] 2.3 Add `AgentReply.tools_called: tuple[str, ...] = ()` with docstring (records tool names invoked in the turn; consumed by agentic intent-routing evals)

## 3. Settings (backend/config/settings.py)

- [ ] 3.1 Add `finx_middleware_base_url` (`FINX_MIDDLEWARE_BASE_URL`, default `https://finx.choiceindia.com`); leave legacy FinX URL settings untouched

## 4. Tests

- [ ] 4.1 Unit tests: widget-step discriminated (de)serialization incl. unknown-`kind` rejection; `ReportRequestEvent` round-trips with `steps`; `ReportRenderPayload` table/link/empty/error shapes; `Session.finx_session_id` default and explicit value; `AgentReply.tools_called` default `()` and explicit value
- [ ] 4.2 Run full suite `uv run pytest backend/tests` — confirm zero regressions (additive check)
