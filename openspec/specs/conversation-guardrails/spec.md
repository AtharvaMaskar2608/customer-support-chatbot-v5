# conversation-guardrails Specification

## Purpose
TBD - created by archiving change cho-54-agentic-loop. Update Purpose after archive.
## Requirements
### Requirement: SEBI compliance — no advice or opinions

The agent SHALL NOT provide opinions, advice, or recommendations on reports or investments, regardless of how the user phrases or repeats the request. It may present factual report data and factual KB answers only.

#### Scenario: Advice request is declined

- **WHEN** the user asks "should I buy/sell this?" or presses for a recommendation, even after a report is shown
- **THEN** the agent declines to advise and restates factual information only

### Requirement: Scope enforcement — Choice FinX only

The agent SHALL politely decline and redirect messages unrelated to Choice FinX.

#### Scenario: Off-topic message is redirected

- **WHEN** the user asks something unrelated to Choice FinX (e.g. general trivia)
- **THEN** the agent politely declines and steers back to Choice FinX support topics

### Requirement: Guardrails hold across the whole conversation

Guardrails SHALL remain in force across every turn, including after clarifying questions and after tool use.

#### Scenario: Guardrail survives tool use and follow-ups

- **WHEN** the user obtains a report, then over several follow-up turns pushes for an investment opinion
- **THEN** the agent continues to refuse advice on every turn, never drifting after tool use or follow-ups

