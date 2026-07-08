# finx-report-tools — delta for finx-middleware-tools

## REMOVED Requirements

### Requirement: CML report tool

**Reason**: The CML report is retired from the chatbot; the new FinX middleware report suite replaces all legacy report tools.
**Migration**: No replacement — delete `cml_report`, `CML_REPORT_TOOL`, and `FINX_CML_BASE_URL` usage.

### Requirement: Contract Note tool

**Reason**: Replaced by the middleware-go contract-notes endpoint (`client_id` + `YYYY-MM-DD` date range, header-only auth) — different endpoint, params, and date format.
**Migration**: Use `get_contract_notes(session, from_date, to_date)` per the new middleware clients requirement.

## MODIFIED Requirements

### Requirement: Tools never raise

All five middleware report clients SHALL isolate upstream failures from the caller, returning `ReportResult(ok=False, error=...)` on any network error, timeout, or in-band failure. Errors are in-band on these APIs: HTTP status is 200 even for failures, so clients SHALL map envelope `Status != "Success"` → `ok=False` with the upstream `Reason`, and Go `StatusCode` other than 200/204 → `ok=False` with the upstream `Message`. Go `StatusCode == 204` is a successful empty result (`ok=True`, no rows), not an error. Date parameters SHALL be validated as `YYYY-MM-DD` before any network call.

#### Scenario: In-band failure is contained

- **WHEN** `GetGlobalPNLNew` returns HTTP 200 with `{"Status":"Fail","Response":null,"Reason":"Data not found."}`
- **THEN** the client returns `ReportResult(ok=False, error="Data not found.")` without raising

#### Scenario: Go 204 is an empty success

- **WHEN** the contract endpoint returns `{"StatusCode":204,"Message":"No valid contract notes found...","Body":{}}`
- **THEN** the client returns `ReportResult(ok=True)` with empty data, distinguishable from an error

#### Scenario: Invalid date rejected locally

- **WHEN** a client is called with `from_date="15-04-2026"`
- **THEN** it returns `ReportResult(ok=False, error=...)` without making a network request

### Requirement: Intent-only Anthropic tool schemas

The system SHALL expose five Anthropic tool definitions — `ledger`, `global_pnl`, `detailed_pnl`, `contract_notes`, `tax_report` — each with **no data parameters** in the model-visible input schema (`{"type":"object","properties":{},"additionalProperties":false}`). A model tool call signals only that a report family is relevant; the report variant (Normal/MTF, segment, financial year) and dates are collected via frontend widgets and injected by the API layer, never produced by the model. Legacy `CML_REPORT_TOOL` and `CONTRACT_NOTE_TOOL` are deleted.

#### Scenario: Model cannot supply report parameters

- **WHEN** the model calls `ledger`
- **THEN** the tool input carries no group/date/client/session fields, and the agent converts the call into a `report_request` widget spec

## ADDED Requirements

### Requirement: FinX middleware report clients

The system SHALL provide five read-only `httpx` clients on `settings.finx_middleware_base_url`, authorized via header `authorization: session.finx_session_id` with `origin: https://finx.choiceindia.com` (plus `from: Web_finx.choiceindia.com_V_4.6.0.4` where noted), each returning `ReportResult`:

- `get_ledger(session, group, from_date, to_date)` → `POST /api/middleware/GetLedgerDetails`, body `{LoginId:"JIFFY", ClientId, Group, FromDate, ToDate, SessionId}`, `group ∈ {"Group1","MTF"}`
- `get_global_pnl(session, group, from_date, to_date)` → `POST /api/middleware/GetGlobalPNLNew`, body `{UserId:ClientId, ClientId, Group, FromDate, ToDate, With_Exp:1, SessionId}`, `group ∈ {"Cash","Derv","Comm"}`
- `get_detailed_pnl(session, group, from_date, to_date)` → `POST /api/middleware/GetDetailedPNL`, body `{UserId:"neuron", ClientId, Group, FromDate, ToDate, SessionId}` with `from:` header, `group ∈ {"Group1","Group23"}`
- `get_contract_notes(session, from_date, to_date)` → `POST /middleware-go/report/contract`, body `{client_id, from_date, to_date}` with `from:` header (no SessionId in body)
- `get_tax_report(session, fin_year)` → `POST /api/middleware/GetTaxReportPDF`, body `{ClientId, FinYear, RequestFor:2, FileFormat:1, SessionId}`, `fin_year ∈ {"2024-2025","2025-2026","2026-2027"}`

`ClientId`/`client_id` is always `session.client_code`; `SessionId` (where present in the body) is `session.finx_session_id`.

#### Scenario: Ledger request carries fixed platform identity

- **WHEN** `get_ledger(session, "MTF", "2026-04-01", "2026-07-15")` runs
- **THEN** it POSTs to `/api/middleware/GetLedgerDetails` with `LoginId="JIFFY"`, `ClientId=session.client_code`, `Group="MTF"`, and `SessionId=session.finx_session_id` both in the `authorization` header and the body

#### Scenario: Detailed PNL uses the fixed "neuron" user

- **WHEN** `get_detailed_pnl(session, "Group23", ...)` runs
- **THEN** the body carries `UserId="neuron"` (not the client code) and the request includes the `from:` version header

#### Scenario: Tax report returns a download URL

- **WHEN** `get_tax_report(session, "2025-2026")` succeeds
- **THEN** the result's data carries the `Response` URL string (a `client-report.choiceindia.com` PDF link)

### Requirement: Report widget registry

The system SHALL define a registry mapping each report tool name to its `report_type` and ordered `WidgetStep` chain: `ledger` → group cards (Normal Ledger=`Group1`, MTF Ledger=`MTF`) + date range; `global_pnl` → segment cards (Equity=`Cash`, Derivatives=`Derv`, Commodity=`Comm`) + date range; `detailed_pnl` → cards (Standard=`Group1`, Commodity=`Group23`) + date range; `contract_notes` → date range only; `tax_report` → FinYear cards only. Date-range steps SHALL carry no default values.

#### Scenario: Ledger intent produces the two-step widget spec

- **WHEN** the agent handles a `ledger` tool call
- **THEN** the emitted `report_request` carries the group card step (Normal/MTF) followed by the date-range step

### Requirement: Report render shaping

The system SHALL shape each `ReportResult` into a `ReportRenderPayload`: ledger results as a table with the documented column map; PNL and contract-note results as tables with columns derived from row keys (success schemas pending upstream capture); tax reports as a `link` payload. Empty results (no rows, Go 204) SHALL become `kind="empty"` with the upstream message; failures become `kind="error"` with a client-safe message. Tax-report URLs SHALL appear only in the render payload — never in model prompts or trace bodies.

#### Scenario: Ledger rows become a table payload

- **WHEN** a ledger result contains voucher rows
- **THEN** the payload is `kind="table"` with the fixed ledger columns and one row dict per voucher

#### Scenario: No data renders as an informational notice

- **WHEN** the upstream reports "Data not found."
- **THEN** the payload is `kind="empty"` with that message, and nothing is sent to the model
