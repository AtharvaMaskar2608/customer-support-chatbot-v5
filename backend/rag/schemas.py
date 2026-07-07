"""Anthropic tool schema for the RAG retriever.

The agent (P4) passes ``RAG_SEARCH_TOOL`` to the Anthropic Messages API so the model can
call retrieval. The model-visible input is intentionally just ``{query}`` — ``top_k`` and
fusion parameters are host-side concerns, not something the model should tune per call.
"""

from typing import Any

RAG_SEARCH_TOOL: dict[str, Any] = {
    "name": "rag_search",
    "description": (
        "Search the customer-support FAQ knowledge base for passages relevant to the "
        "user's question. Returns ranked, citable chunks. Use this whenever a question "
        "may be answered by documented FAQ/help content, and ground the reply in the "
        "returned chunks with citations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The natural-language search query — typically the user's question, "
                    "rephrased into a focused, self-contained search string."
                ),
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
