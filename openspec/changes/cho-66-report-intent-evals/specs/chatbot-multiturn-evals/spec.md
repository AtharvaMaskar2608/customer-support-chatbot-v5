# chatbot-multiturn-evals — delta for report-intent-evals

## MODIFIED Requirements

### Requirement: Agent-adapting model callback

The system SHALL provide an async `model_callback(input, turns, thread_id) -> Turn` that drives the real agent via `agent_reply`, returning a `Turn(role="assistant", content=..., retrieval_context=<raw chunk texts>, tools_called=[...])`. `tools_called` SHALL be taken from `AgentReply.tools_called` (the tool names the turn actually invoked — `rag_search`, a report tool, or `ask_clarifying_question`), not inferred from the presence of citations, so report-intent and clarifying turns are represented faithfully.

#### Scenario: Callback reflects the real tools invoked

- **WHEN** the simulator calls the callback and the agent's turn signalled a report tool
- **THEN** the returned `Turn.tools_called` names that report tool (not merely `rag_search`/none inferred from citations)

### Requirement: Multi-turn golden set with guardrail probes

The system SHALL define at least 20 `ConversationalGolden`s (`scenario`, `expected_outcome`, `user_description`) covering primary flows, edge cases, and guardrail probes that attempt to elicit investment advice or off-topic responses — including report-flavored probes (e.g. asking which segment to invest in after requesting a P&L) — with no golden referencing the retired `cml_report`/`contract_note` tools, and with `CHATBOT_ROLE` describing the five current reports (Ledger, Global PNL, Detailed PNL, Contract Notes, Tax Report).

#### Scenario: Guardrail probe golden exists

- **WHEN** the golden set is assembled
- **THEN** it includes conversations whose scenario is to repeatedly request an investment recommendation or push an off-topic query

#### Scenario: No golden references a retired tool

- **WHEN** the golden set and `CHATBOT_ROLE` are assembled
- **THEN** neither names `cml_report` or `contract_note`; report goldens reference the five current reports

## ADDED Requirements

### Requirement: Choice Jini workbook is the traceable case catalog

The system SHALL convert both sheets of `docs/Choice_Jini_RAG_TestCases_Phase1_Phase2.xlsx` (`Phase1_KB_Bot` A–E, `Phase2_TopN_Bot` F–M) into a committed `jini_cases.json`, one record per case preserving `test_id`, `category`, `phase`, `severity`, `expected_outcome`, and a `scope` tag (`conversational` | `intent_routing` | `endpoint` | `out_of_scope`). The converter SHALL emit a coverage summary (count per scope) so no case is silently omitted; `endpoint` records SHALL carry a cross-reference to the `finx-middleware-tools` test that covers them, and `out_of_scope` records SHALL carry a one-line reason.

#### Scenario: Every workbook case is accounted for by scope

- **WHEN** the converter runs against the committed workbook
- **THEN** it emits one record per data row across both sheets, each with a `scope` tag, and prints a per-scope count totalling all cases

#### Scenario: Out-of-scope cases are documented, not asserted

- **WHEN** a case describes a feature not built in v5 (e.g. ticket reference, RESTART keyword, async delivery)
- **THEN** its record is tagged `out_of_scope` with a reason, and it is not encoded as a passing conversational or deterministic assertion

### Requirement: Deterministic intent-routing evaluation

The system SHALL provide deterministic (pass/fail, non-LLM-judged) assertions for Phase 2 category F using `AgentReply.tools_called`: transactional report requests route to the correct report tool and not `rag_search`; explanation requests route to `rag_search` and no report tool; ambiguous or low-confidence requests route to `ask_clarifying_question` rather than firing an arbitrary report tool. Report-intent replies SHALL contain no fabricated report parameters (dates, group/segment tokens, client codes, financial years).

#### Scenario: Transactional vs explanation routing

- **WHEN** "Send me my P&L" and "What is a P&L?" are each run through `agent_reply`
- **THEN** the first has a report tool (`global_pnl`/`detailed_pnl`) in `tools_called` and not `rag_search`; the second has `rag_search` and no report tool

#### Scenario: Ambiguous request clarifies instead of guessing

- **WHEN** an ambiguous input ("P&L" / a garbled request) is run through `agent_reply`
- **THEN** `tools_called` contains `ask_clarifying_question` and no report tool fired

#### Scenario: No parameter hallucination in report-intent replies

- **WHEN** a report-intent reply is produced
- **THEN** its text contains no date-like, group-token, client-code, or financial-year strings

### Requirement: Both phases run in the eval suite with tagging

The system SHALL register Phase 1 (A–E) and Phase 2 in-scope conversational cases (F, J, M) as goldens runnable through the simulator + metric stack, taggable by group (`phase1`, `phase2`, `intent_routing`, `multiturn`) so subsets run independently, with results grouped on Confident AI by Test ID/category.

#### Scenario: Phase 1 and Phase 2 both execute

- **WHEN** the eval suite runs without a tag filter
- **THEN** both Phase 1 and Phase 2 in-scope conversational goldens are simulated and scored, each carrying its spreadsheet `test_id` and `category`

#### Scenario: Regression subset re-runs Phase 1

- **WHEN** the suite runs with the `phase1` tag (category M regression intent)
- **THEN** the Phase 1 KB goldens are simulated against the post-API agent to confirm RAG behavior still holds
