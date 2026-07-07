"""HTTP surface: FastAPI routes, the in-memory session store, and SSE serialization.

This package fronts the agent (P4) and report tools (P2) for the POC frontend (P8). It
owns no agent or tool logic — it only transports sessions and ``SSEEvent`` frames over HTTP.
"""
