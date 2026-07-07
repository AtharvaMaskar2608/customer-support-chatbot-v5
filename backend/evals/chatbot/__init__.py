"""Multi-turn conversational evaluation of the Choice FinX agent.

Simulates whole conversations against the real agent (:func:`backend.agent.loop.agent_reply`)
via DeepEval's ``ConversationSimulator`` and scores the resulting ``ConversationalTestCase``s
for context retention, goal completion, guardrail adherence, and turn-to-turn consistency.

Standalone eval — nothing in the app imports it. See ``docs/chatbot_eval/``.
"""
