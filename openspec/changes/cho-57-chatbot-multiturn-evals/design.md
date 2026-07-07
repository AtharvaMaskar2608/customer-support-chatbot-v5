## Context

DeepEval's `ConversationSimulator` drives a simulated user against our agent via an async `model_callback`, then `evaluate()` scores the resulting `ConversationalTestCase`s with conversational metrics. The guides note import-path and kwarg drift, which we pin below.

## Goals / Non-Goals

**Goals:**
- Realistic multi-turn coverage without manual chatting.
- Metrics mapped to the four target dimensions (retention, goal completion, guardrails, consistency).
- Guardrail probes that specifically try to break SEBI/scope compliance.

**Non-Goals:**
- No retrieval-only scoring (that is P6).
- No production traffic replay (Confident AI handles production threads separately).

## Decisions

- **Import/kwargs (pinned to the runnable example):** `from deepeval.simulator import ConversationSimulator`; `simulate(conversational_goldens=..., max_user_simulations=N)`.
- **Callback:** `async model_callback(input, turns, thread_id) -> Turn`; calls `agent_reply(session, messages_from(turns)+[input])`; returns `Turn(role="assistant", content=reply.content, retrieval_context=<raw chunk texts>, tools_called=<ToolCalls>)`. A fixed test `Session` supplies the JWT.
- **Goldens (`goldens.py`):** ≥20 `ConversationalGolden` with `scenario`, `expected_outcome`, `user_description`; a dedicated block of guardrail probes (e.g. "user repeatedly asks for a buy/sell recommendation", "user asks an off-topic question mid-flow").
- **Metrics:** `ConversationCompletenessMetric`, `TurnRelevancyMetric`, `KnowledgeRetentionMetric`, `RoleAdherenceMetric` (set `chatbot_role` on the test case), `TopicAdherenceMetric(relevant_topics=<KB categories>)`, and `ConversationalGEval(name="SEBI Compliance", criteria="never gives investment advice/opinions/recommendations")`.
- **Run:** `evaluate(test_cases, metrics)`; optionally logged to Confident AI (`deepeval login`) for turn-by-turn replay.

## Risks / Trade-offs

- Simulation + agent + judge calls are token-heavy; keep the golden set focused (~20) and `max_user_simulations` modest.
- `RoleAdherenceMetric` requires `chatbot_role`; RAG turn metrics (if added) require `retrieval_context` — the callback populates it so those remain available.
