## ADDED Requirements

### Requirement: CML report tool

The system SHALL provide `cml_report(session, client_id) -> ReportResult` that issues `POST {FINX_CML_BASE_URL}/mis/reports/generate` with body `{"reportType":"cml","searchBy":"client-id","searchValue":client_id}` and headers `Authorization: session.session_token`, `authType: jwt`, `source: FINX_WEB`. `client_id` originates from the frontend widget, not the model.

#### Scenario: Successful CML report

- **WHEN** the upstream returns 2xx with a JSON body
- **THEN** the tool returns `ReportResult(ok=True, data=<parsed json>)`

### Requirement: Contract Note tool

The system SHALL provide `contract_note(session, mobile_no, contract_date) -> ReportResult` that issues `POST {FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate` with body `{"mobileNo":mobile_no,"contractDate":contract_date}` (contractDate `DD-MM-YYYY`) and the shared auth headers. Both params originate from the frontend widget.

#### Scenario: Invalid date format is rejected before the call

- **WHEN** `contract_date` does not match `DD-MM-YYYY`
- **THEN** the tool returns `ReportResult(ok=False, error=...)` without making a network request

### Requirement: Tools never raise

Both report tools SHALL isolate all upstream failures from the caller, returning `ReportResult(ok=False, error=...)` on any network error, timeout, or non-2xx response.

#### Scenario: Upstream failure is contained

- **WHEN** the upstream returns a 500 or the request times out
- **THEN** the tool returns `ReportResult(ok=False, error=...)` and does not raise an exception

### Requirement: Intent-only Anthropic tool schemas

The system SHALL expose `CML_REPORT_TOOL` and `CONTRACT_NOTE_TOOL` as Anthropic tool definitions with **no data parameters** in the model-visible input schema. A model tool call signals only that a report is relevant; report parameter values are collected from the frontend widget and injected by the API/agent layer, never produced by the model.

#### Scenario: Model cannot supply report parameters

- **WHEN** the agent registers `CML_REPORT_TOOL` / `CONTRACT_NOTE_TOOL` and the model calls one
- **THEN** the tool input schema contains no `client_id`/`mobile_no`/`contract_date`/session fields, so the model cannot fabricate parameter values; the agent turns the call into a `report_request` for the frontend widget
