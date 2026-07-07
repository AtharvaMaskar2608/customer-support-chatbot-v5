# agentic-loop Specification

## Purpose
TBD - created by archiving change cho-54-agentic-loop. Update Purpose after archive.
## Requirements
### Requirement: Anthropic tool-use loop

The system SHALL run an Anthropic Messages API tool-use loop using `settings.anthropic_model` with thinking disabled, registering `rag_search`, `cml_report`, and `contract_note`, and repeating call→execute-tools→feed-results until the model returns a final answer. It SHALL expose `agent_reply(session, messages) -> AgentReply` (non-streaming) and `agent_reply_stream(session, messages) -> AsyncIterator[SSEEvent]`.

#### Scenario: FAQ answer is grounded and cited

- **WHEN** a user asks an in-scope FAQ question and the model calls `rag_search`
- **THEN** the loop feeds the retrieved chunks back, produces a final answer, and the reply includes the corresponding citations

#### Scenario: System prompt lists tools and in-scope categories

- **WHEN** the loop builds its system prompt
- **THEN** it contains the available tool list and the in-scope KB categories derived from `qa_chunks` (`topic`/`section`)

### Requirement: Streaming SSE progress

`agent_reply_stream` SHALL emit `status` frames at tool-use boundaries (e.g. "Looking up the knowledge base…", "Generating the answer…"), stream `token` frames for the final answer, emit a `citations` frame when RAG was used, then a `usage` frame with per-message cost, latency, and running `cumulative_cost_inr`, then `done`.

#### Scenario: Progress then tokens then usage

- **WHEN** a turn runs to completion
- **THEN** the client receives status frame(s), then answer tokens, then a usage frame carrying `cumulative_cost_inr`, then `done`

### Requirement: Report intent pause and resume

When the model calls a report tool, the loop SHALL emit a `report_request` frame (with `report_type`, the fields to collect, and the pending `tool_use_id`) and pause instead of calling FinX with model-supplied params. `resume_report_stream(session, messages, tool_use_id, report_result)` SHALL append the tool result and continue to a final answer.

#### Scenario: Report request pauses the turn

- **WHEN** the model calls `contract_note`
- **THEN** the stream yields a `report_request` naming `contract_note` and the fields (e.g. contract date), then ends the turn awaiting widget input — no FinX call is made with model-fabricated params

#### Scenario: Resume produces a compliant summary

- **WHEN** `resume_report_stream` is called with the `ReportResult` from a widget submission
- **THEN** the loop feeds it back as the tool result and streams a factual summary of the report

### Requirement: Conversation caps

The loop SHALL allow at most 2 clarifying questions per conversation and at most 10 total messages, both **enforced in code** (not by prompt alone). Clarifying questions SHALL be a structural `ask_clarifying_question` tool so they can be counted deterministically from the message history; once 2 have been asked, the loop SHALL withhold the tool from the model on subsequent turns so a 3rd cannot be asked. When a cap is reached without resolution, the assistant SHALL offer to raise a support ticket.

#### Scenario: Clarifying questions are counted structurally

- **WHEN** the model needs a missing detail
- **THEN** it asks via the `ask_clarifying_question` tool (rather than inline free text), and the loop counts prior `ask_clarifying_question` tool calls in the message history to know how many have been asked

#### Scenario: Third clarifying question is prevented in code

- **WHEN** 2 clarifying questions have already been asked in the conversation
- **THEN** the loop does not offer the `ask_clarifying_question` tool to the model, so it cannot ask a 3rd; the assistant answers with what it has or offers to raise a support ticket

#### Scenario: Message cap offers a ticket

- **WHEN** the conversation reaches 10 messages without resolution
- **THEN** the assistant offers to raise a support query/ticket rather than continuing to probe

