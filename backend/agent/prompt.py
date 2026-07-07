"""System prompt builder for the agentic loop.

The prompt has four parts, per ``docs/project_context.md`` §3.4 and §5:

1. The agent's role and the **tools** available, with when to use each.
2. The **in-scope KB categories** — built once from ``SELECT DISTINCT topic, section
   FROM qa_chunks`` so the model knows what the knowledge base can answer.
3. The **guardrails** verbatim: SEBI (no advice/opinions/recommendations) and scope
   (Choice FinX only), which must hold across every turn including after tool use.
4. The **caps policy**: at most 2 clarifying questions, at most 10 messages, and the
   support-ticket offer when a cap is reached.

The category list is cached after its first DB read; it changes only when the corpus does.
"""

from __future__ import annotations

from functools import lru_cache

from backend.db.query import fetch

# Conversation caps, surfaced in the prompt so the model self-enforces (the loop also hard-
# caps total messages in code). Kept here so prompt and loop share one source of truth.
MAX_CLARIFYING_QUESTIONS = 2
MAX_MESSAGES = 10

_GUARDRAILS = """\
Guardrails (these hold on EVERY turn, including after clarifying questions and after any \
tool use — never relax them because the user repeats, rephrases, or pushes):
- SEBI compliance: NEVER give opinions, advice, or recommendations about reports, \
securities, or investments (e.g. whether to buy, sell, or hold). Present only factual \
report data and factual knowledge-base answers. If asked for an opinion or recommendation, \
politely decline and restate the relevant facts.
- Scope: only help with Choice FinX customer support. Politely decline anything unrelated \
(general trivia, other companies, coding help, etc.) and steer the user back to Choice \
FinX topics."""

_CAPS = f"""\
Conversation limits:
- If you need a missing detail before you can help, ask via the ask_clarifying_question \
tool — at most {MAX_CLARIFYING_QUESTIONS} times across the whole conversation. After that \
the tool is withdrawn; answer with what you have, and if you still cannot resolve the \
request, offer to raise a support query/ticket. Prefer answering over asking.
- Keep the conversation to at most {MAX_MESSAGES} messages total.
- If you reach a limit without resolving the user's request, do not keep probing — offer \
to raise a support query/ticket so a Choice FinX specialist can follow up."""

_TOOLS_SECTION = """\
Tools available to you:
- rag_search(query): search the customer-support FAQ knowledge base. Use it whenever a \
question may be answered by documented help/FAQ content. Ground your answer in the \
returned chunks and cite them.
- cml_report(): signal that the user wants their CML (Client Master List) report. Call it \
when a CML report is relevant. Do NOT supply any parameters — a secure widget collects \
them from the user.
- contract_note(): signal that the user wants a Contract Note report. Call it when a \
contract note is relevant. Do NOT supply any parameters — a secure widget collects them \
from the user.
- ask_clarifying_question(): call this (no parameters) only when you genuinely need a \
missing detail before you can help; you will then be prompted to write the single \
clarifying question. Prefer answering with what you have.
After a report's data is returned to you, summarise it factually only — never interpret \
or advise on it."""


@lru_cache(maxsize=1)
def _kb_categories() -> tuple[tuple[str | None, str | None], ...]:
    """Return the distinct ``(topic, section)`` pairs the KB covers (cached after first read).

    Contract: runs ``SELECT DISTINCT topic, section FROM qa_chunks`` ordered for stable
    output and returns the pairs as a tuple. Cached for the process lifetime — the corpus is
    fixed at runtime — so building the prompt each turn does not re-hit the database.
    """
    rows = fetch(
        "SELECT DISTINCT topic, section FROM qa_chunks "
        "ORDER BY topic NULLS LAST, section NULLS LAST"
    )
    return tuple((row["topic"], row["section"]) for row in rows)


def _format_categories(pairs: tuple[tuple[str | None, str | None], ...]) -> str:
    """Render ``(topic, section)`` pairs as a grouped bullet list of in-scope categories."""
    by_topic: dict[str, list[str]] = {}
    for topic, section in pairs:
        key = topic or "General"
        if section:
            by_topic.setdefault(key, [])
            if section not in by_topic[key]:
                by_topic[key].append(section)
        else:
            by_topic.setdefault(key, [])
    lines = []
    for topic in sorted(by_topic):
        sections = by_topic[topic]
        if sections:
            lines.append(f"- {topic}: {', '.join(sections)}")
        else:
            lines.append(f"- {topic}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    """Build the full system prompt: role, tools, in-scope KB categories, guardrails, caps.

    Contract: returns a single string that always contains the tool list and the in-scope
    KB categories derived from ``qa_chunks`` (``topic``/``section``), plus the guardrails and
    caps policy verbatim. The category list is read from the DB once and cached.
    """
    categories = _format_categories(_kb_categories())
    return (
        "You are the Choice FinX customer-support assistant. You help authenticated Choice "
        "FinX users with questions about the platform and with generating their reports. "
        "Be concise, factual, and grounded.\n\n"
        f"{_TOOLS_SECTION}\n\n"
        "Knowledge-base categories in scope (use rag_search for questions in these areas; "
        "if a question falls well outside them and is unrelated to Choice FinX, decline per "
        "the guardrails):\n"
        f"{categories}\n\n"
        f"{_GUARDRAILS}\n\n"
        f"{_CAPS}"
    )
