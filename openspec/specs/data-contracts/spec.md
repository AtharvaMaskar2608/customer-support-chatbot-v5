# data-contracts Specification

## Purpose
TBD - created by archiving change cho-50-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Shared data contracts

The system SHALL provide frozen Pydantic v2 models used as the interface between all modules: `Citation`, `RagChunk`, `RagResult`, `ReportResult`, `Session`, `Usage`, and `AgentReply`. Downstream modules SHALL import these rather than redefine them. `Session` SHALL carry a unique, stable `session_id` that identifies one session/conversation (distinct from the per-client `client_code`), so tracing can group a conversation's turns.

#### Scenario: RagResult carries chunks with citations

- **WHEN** a `RagResult` is constructed with one or more `RagChunk` items
- **THEN** each chunk exposes its `id`, `chunk` text, `score`, and a `Citation` derived from `qa_chunks` metadata (`topic`, `section`, `question`, `answer_source`, `source_sheet`, `source_row`)

#### Scenario: ReportResult never partially fails

- **WHEN** a report tool call fails
- **THEN** it is represented as `ReportResult(ok=False, data=None, error=<message>)` rather than raising

#### Scenario: Session carries a unique session identity

- **WHEN** a `Session` is created (with or without an explicit `session_id`)
- **THEN** it exposes a non-empty `session_id`, stable for that object's lifetime and distinct from `client_code`, usable as the tracing `thread_id`; two sessions created without an explicit id receive distinct ids

### Requirement: SSE event contract

The system SHALL define an `SSEEvent` discriminated union covering `status`, `token`, `citations`, `usage`, `report_request`, `done`, and `error` frames, where `usage` frames include `cumulative_cost_inr`.

#### Scenario: Usage frame includes cumulative INR cost

- **WHEN** a `usage` SSE event is serialized
- **THEN** it contains per-message cost, latency, and a running `cumulative_cost_inr` field

#### Scenario: Report request frame names the report and required fields

- **WHEN** the agent decides a report is relevant and emits a `report_request` frame
- **THEN** the frame carries the `report_type` (`cml` | `contract_note`) and the list of fields the frontend widget must collect, so the model never supplies report parameter values itself

