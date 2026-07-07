## Why

RAG-level evals (P6) don't capture whole-conversation behavior: context retention, goal completion, guardrail adherence, and consistency across turns. This change evaluates the end-to-end agent over simulated multi-turn conversations.

## What Changes

- **Model callback:** `model_callback(input, turns, thread_id) -> Turn` adapting P4 `agent_reply` — maps the reply to a `Turn(role="assistant", content=..., retrieval_context=<raw chunk texts>, tools_called=[...])`.
- **Golden set:** ≥20 `ConversationalGolden(scenario, expected_outcome, user_description)` covering primary flows, edge cases, and **guardrail probes** (SEBI advice-seeking, off-topic scope pushes).
- **Simulation:** `ConversationSimulator(model_callback=...).simulate(conversational_goldens=..., max_user_simulations=N)` → `list[ConversationalTestCase]`.
- **Scoring:** `evaluate(test_cases, metrics=[...])` with `ConversationCompletenessMetric` (goal completion), `TurnRelevancyMetric` (consistency), `KnowledgeRetentionMetric` (context retention), `RoleAdherenceMetric` + `TopicAdherenceMetric` + a `ConversationalGEval` "SEBI/policy compliance" (guardrails).
- Confident AI integration for hosted test reports and thread replay.

Follows `docs/chatbot_eval/1_multi_turn_eval.md`, `2_..._metrics.md`, `3_..._simulation.md`.

## Capabilities

### New Capabilities
- `chatbot-multiturn-evals`: simulated multi-turn conversations against the agent, scored for retention, goal completion, guardrail adherence, and consistency.

## Impact

- New: `backend/evals/chatbot/callback.py`, `backend/evals/chatbot/goldens.py`, `backend/evals/chatbot/test_chatbot.py`, `backend/evals/chatbot/__init__.py`.
- Imports P4 `agent_reply` and foundations (`Settings`). Adds no root dependencies (`deepeval` declared by foundations).
- Standalone eval — nothing else imports it.
