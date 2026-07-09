# agentic-loop Specification

## Purpose
TBD - created by archiving change cho-54-agentic-loop. Update Purpose after archive.
## Requirements
### Requirement: Anthropic tool-use loop

The system SHALL run an Anthropic Messages API tool-use loop using `settings.anthropic_model` with thinking disabled, registering `rag_search` and the five intent-only report tools (`ledger`, `global_pnl`, `detailed_pnl`, `contract_notes`, `tax_report`), and repeating call→execute-tools→feed-results until the model returns a final answer. It SHALL expose `agent_reply(session, messages) -> AgentReply` (non-streaming) and `agent_reply_stream(session, messages) -> AsyncIterator[SSEEvent]`. `agent_reply` SHALL populate `AgentReply.tools_called` with the tool names invoked during the turn (`rag_search`, any report tool, `ask_clarifying_question`), so evals can assert intent routing deterministically without inferring tools from citations.

#### Scenario: FAQ answer is grounded and cited

- **WHEN** a user asks an in-scope FAQ question and the model calls `rag_search`
- **THEN** the loop feeds the retrieved chunks back, produces a final answer, and the reply includes the corresponding citations and `tools_called` contains `rag_search`

#### Scenario: Report intent is recorded in tools_called

- **WHEN** the model calls a report tool (e.g. `global_pnl`) for a transactional request
- **THEN** `agent_reply` returns with `tools_called` containing `global_pnl` (and no `rag_search`), so an intent-routing eval can assert the transactional path was taken rather than the RAG path

#### Scenario: System prompt lists tools and in-scope categories

- **WHEN** the loop builds its system prompt
- **THEN** it contains the available tool list (including the five report tools and that report results render in the UI, not via the assistant) and the in-scope KB categories derived from `qa_chunks` (`topic`/`section`)

### Requirement: Streaming SSE progress

`agent_reply_stream` SHALL emit `status` frames at tool-use boundaries (e.g. "Looking up the knowledge base…", "Generating the answer…"), stream `token` frames for the final answer, emit a `citations` frame when RAG was used, then a `usage` frame with per-message cost, latency, and running `cumulative_cost_inr`, then `done`.

#### Scenario: Progress then tokens then usage

- **WHEN** a turn runs to completion
- **THEN** the client receives status frame(s), then answer tokens, then a usage frame carrying `cumulative_cost_inr`, then `done`

### Requirement: Report intent pause and resume

When the model calls a report tool, the loop SHALL emit a `report_request` frame carrying the registry's `report_type` and `steps` widget spec plus the pending `tool_use_id` (retained for trace correlation only), then emit `usage` and `done` — **the turn ends**. The loop SHALL NOT call FinX with model-supplied params, SHALL NOT await a tool result for the pending `tool_use`, and SHALL NOT provide any resume entrypoint: report execution and rendering happen entirely outside the model via `POST /report`. `resume_report_stream` is deleted.

#### Scenario: Report request terminates the turn with a done frame

- **WHEN** the model calls `ledger`
- **THEN** the stream yields `report_request` (with the Normal/MTF card step and date-range step), then `usage`, then `done` — and no FinX call or further model call occurs in that turn

#### Scenario: No model involvement after widget submission

- **WHEN** the frontend later submits the widget params via `POST /report`
- **THEN** no Anthropic API call is made — the result is shaped server-side and rendered by the frontend

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

