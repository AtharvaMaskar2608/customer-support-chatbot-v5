# data-contracts Specification

## Purpose
TBD - created by archiving change cho-50-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Shared data contracts

The system SHALL provide frozen Pydantic v2 models used as the interface between all modules: `Citation`, `RagChunk`, `RagResult`, `ReportResult`, `ReportRenderPayload`, `Session`, `Usage`, and `AgentReply`. Downstream modules SHALL import these rather than redefine them. `Session` SHALL carry a unique, stable `session_id` that identifies one session/conversation (distinct from the per-client `client_code`), so tracing can group a conversation's turns, and SHALL carry a `finx_session_id` (the FinX middleware SessionId used to authorize report calls, distinct from the legacy JWT `session_token`), defaulting to an empty string so existing constructors remain valid. `AgentReply` SHALL carry `tools_called: tuple[str, ...]` (defaulting to empty) recording the tool names invoked during the turn, so evals can assert intent routing deterministically.

#### Scenario: RagResult carries chunks with citations

- **WHEN** a `RagResult` is constructed with one or more `RagChunk` items
- **THEN** each chunk exposes its `id`, `chunk` text, `score`, and a `Citation` derived from `qa_chunks` metadata (`topic`, `section`, `question`, `answer_source`, `source_sheet`, `source_row`)

#### Scenario: ReportResult never partially fails

- **WHEN** a report tool call fails
- **THEN** it is represented as `ReportResult(ok=False, data=None, error=<message>)` rather than raising

#### Scenario: Session carries a unique session identity

- **WHEN** a `Session` is created (with or without an explicit `session_id`)
- **THEN** it exposes a non-empty `session_id`, stable for that object's lifetime and distinct from `client_code`, usable as the tracing `thread_id`; two sessions created without an explicit id receive distinct ids

#### Scenario: Session carries the FinX middleware session id

- **WHEN** a `Session` is created with `finx_session_id="abc123"`
- **THEN** `session.finx_session_id` returns `"abc123"`, and a `Session` constructed without it defaults to `""` (no constructor breakage)

#### Scenario: AgentReply records the tools it invoked

- **WHEN** an `AgentReply` is constructed with `tools_called=("ledger",)`
- **THEN** `reply.tools_called` returns `("ledger",)`, and an `AgentReply` constructed without it defaults to `()` (no constructor breakage)

#### Scenario: ReportRenderPayload represents a table result

- **WHEN** a `ReportRenderPayload(kind="table", title=..., columns=(ReportColumn(key, label), ...), rows=(dict, ...))` is serialized
- **THEN** the JSON carries ordered column specs and row dicts keyed by column `key`, sufficient for a generic frontend table renderer

#### Scenario: ReportRenderPayload represents link, empty, and error results

- **WHEN** a payload is constructed with `kind="link"` and a `url`, or `kind="empty"`/`kind="error"` with a `message`
- **THEN** it serializes with those fields populated and table fields empty, so the frontend can render a download link or an informational notice without model involvement

### Requirement: SSE event contract

The system SHALL define an `SSEEvent` discriminated union covering `status`, `token`, `citations`, `usage`, `report_request`, `done`, and `error` frames, where `usage` frames include `cumulative_cost_inr`. The `report_request` frame SHALL carry a declarative widget spec: `report_type` (one of `ledger`, `global_pnl`, `detailed_pnl`, `contract_notes`, `tax_report`, plus legacy `cml` | `contract_note` until their tools are removed), an ordered `steps` list of `WidgetStep`s (`CardStep` with `param` and `options: [CardOption(label, value)]`, or `DateRangeStep` with `from_param`/`to_param`, discriminated on `kind`), and the pending `tool_use_id`. Card option `value`s are opaque FinX API tokens the frontend never interprets. The legacy flat `fields` list remains defaulted to empty until removed.

#### Scenario: Usage frame includes cumulative INR cost

- **WHEN** a `usage` SSE event is serialized
- **THEN** it contains per-message cost, latency, and a running `cumulative_cost_inr` field

#### Scenario: Report request frame carries a chained widget spec

- **WHEN** the agent emits a `report_request` for a ledger
- **THEN** the frame carries `report_type="ledger"` and `steps=[CardStep(param="group", options=[("Normal Ledger","Group1"),("MTF Ledger","MTF")]), DateRangeStep(from_param="from_date", to_param="to_date")]`, so the frontend can chain a card picker then a date-range picker with no model-supplied parameter values

#### Scenario: Widget steps deserialize by kind

- **WHEN** a `report_request` frame's `steps` JSON is validated
- **THEN** each step deserializes to `CardStep` or `DateRangeStep` via the `kind` discriminator, and an unknown `kind` fails validation

