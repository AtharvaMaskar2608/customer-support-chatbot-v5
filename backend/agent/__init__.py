"""Agentic loop package: Anthropic tool-use loop, system prompt, tools, and cost.

Public surface: :func:`agent_reply` (non-streaming, for evals), :func:`agent_reply_stream`
(streaming ``SSEEvent``s, for the API), the tool registry (:data:`TOOLS`), and
:func:`build_system_prompt`.
"""

from backend.agent.cost import build_usage, message_cost_inr
from backend.agent.loop import (
    agent_reply,
    agent_reply_stream,
    conversation_message_count,
)
from backend.agent.prompt import build_system_prompt
from backend.agent.tools import TOOLS, dispatch_tool, is_report_tool

__all__ = [
    "TOOLS",
    "agent_reply",
    "agent_reply_stream",
    "build_system_prompt",
    "build_usage",
    "conversation_message_count",
    "dispatch_tool",
    "is_report_tool",
    "message_cost_inr",
]
