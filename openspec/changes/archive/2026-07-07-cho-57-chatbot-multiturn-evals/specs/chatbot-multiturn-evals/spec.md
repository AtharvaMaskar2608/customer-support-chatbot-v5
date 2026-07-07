## ADDED Requirements

### Requirement: Agent-adapting model callback

The system SHALL provide an async `model_callback(input, turns, thread_id) -> Turn` that drives the real agent via `agent_reply`, returning a `Turn(role="assistant", content=..., retrieval_context=<raw chunk texts>, tools_called=[...])`.

#### Scenario: Callback returns a populated Turn

- **WHEN** the simulator calls the callback with a user `input` and prior `turns`
- **THEN** it invokes `agent_reply` and returns an assistant `Turn` whose `content`, `retrieval_context`, and `tools_called` reflect that reply

### Requirement: Multi-turn golden set with guardrail probes

The system SHALL define at least 20 `ConversationalGolden`s (`scenario`, `expected_outcome`, `user_description`) covering primary flows, edge cases, and guardrail probes that attempt to elicit investment advice or off-topic responses.

#### Scenario: Guardrail probe golden exists

- **WHEN** the golden set is assembled
- **THEN** it includes conversations whose scenario is to repeatedly request an investment recommendation or push an off-topic query

### Requirement: Conversation scoring across the four dimensions

The system SHALL simulate the goldens with `ConversationSimulator` and score the resulting `ConversationalTestCase`s with metrics covering context retention (`KnowledgeRetentionMetric`), goal completion (`ConversationCompletenessMetric`), consistency (`TurnRelevancyMetric`), and guardrail adherence (`RoleAdherenceMetric`, `TopicAdherenceMetric`, and a `ConversationalGEval` SEBI-compliance metric).

#### Scenario: Guardrail-probe conversation is scored for compliance

- **WHEN** a guardrail-probe conversation is evaluated
- **THEN** the SEBI-compliance `ConversationalGEval` scores whether the agent refused advice across every turn
