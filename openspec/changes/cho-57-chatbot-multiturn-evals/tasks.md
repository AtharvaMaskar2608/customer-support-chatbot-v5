## 1. Model callback

- [ ] 1.1 `backend/evals/chatbot/callback.py`: `async model_callback(input, turns, thread_id) -> Turn` adapting `agent_reply`; map to `Turn(content, retrieval_context, tools_called)` with a fixed test `Session`.

## 2. Goldens

- [ ] 2.1 `backend/evals/chatbot/goldens.py`: ≥20 `ConversationalGolden(scenario, expected_outcome, user_description)` incl. a guardrail-probe block (SEBI advice-seeking, off-topic scope pushes).

## 3. Simulate & score

- [ ] 3.1 `backend/evals/chatbot/test_chatbot.py`: `ConversationSimulator(model_callback=...).simulate(conversational_goldens=..., max_user_simulations=N)`.
- [ ] 3.2 `evaluate(test_cases, metrics=[ConversationCompletenessMetric, TurnRelevancyMetric, KnowledgeRetentionMetric, RoleAdherenceMetric, TopicAdherenceMetric, ConversationalGEval("SEBI Compliance")])`; set `chatbot_role` on cases.

## 4. Done condition

- [ ] 4.1 `openspec validate chatbot-multiturn-evals --strict` passes.
- [ ] 4.2 Test command: `deepeval test run backend/evals/chatbot/test_chatbot.py` (or `python -m backend.evals.chatbot.test_chatbot`) simulates the goldens and produces per-metric scores, with guardrail-probe conversations scored by the SEBI-compliance metric.
