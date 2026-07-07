# Manual QA checklist — frontend-poc

**Setup**

```bash
# terminal 1 — API (needs .env: DB, Anthropic key, FinX base URLs)
uv run uvicorn backend.main:app --port 8000

# terminal 2 — static frontend
python3 -m http.server 3000 -d frontend
# open http://localhost:3000          (API base defaults to http://localhost:8000;
#                                      override with ?api=http://host:port)
```

**Login**

- [ ] Submit phone / user id / session token *with stray leading+trailing spaces* → login succeeds (values trimmed client-side; server trims again).
- [ ] Wrong/unreachable API → inline error under the form, button re-enables.
- [ ] After login the header shows the user id; the empty state greets by user id.

**FAQ turn (status → tokens → citations → cost)**

- [ ] Ask e.g. "What are the brokerage charges?" → shimmer status line ("Generating…", then "Looking up the knowledge base…" on RAG).
- [ ] Answer streams token-by-token with a blinking gradient caret; caret stops on done.
- [ ] "N sources" chip appears under the message; hover (desktop) or tap (mobile) reveals the citation card (topic › section, question, source sheet/row).
- [ ] Per-message pill shows ₹cost + latency; the session-spend card counts up (compact pill in the header below 1280px; full floating card top-left at ≥1280px).
- [ ] A second turn keeps history: `prior_cost_inr` accrues (cumulative card grows, doesn't reset).

**Report widget (structured params, never free text)**

- [ ] Ask "get my contract note" → the agent pauses; a lock-badged widget renders with mobile number **prefilled from the login phone** and a **native date-picker**.
- [ ] Pick a date → submit → payload sends `contract_date` as `DD-MM-YYYY` (verify in the network tab), plus `tool_use_id` and the paused messages snapshot.
- [ ] The summary streams into a new bubble; widget dims/disables (no double submit).
- [ ] Ask "get my CML report" → widget shows `client_id` prefilled from the optional login client code (editable when blank).
- [ ] Report failure (expired JWT) → the agent still answers gracefully (ReportResult ok=false summarised), or the stream ends with a red error bubble — never a hung UI.

**Guardrails & caps (rendering only)**

- [ ] Ask for investment advice → declines factually (renders as a normal message).
- [ ] Error frame mid-stream renders as a red-tinted bubble; composer re-enables.

**Responsive / polish**

- [ ] 375px width: compact cost pill in header, bubbles ≤92%, composer usable, widget fits, no horizontal scroll.
- [ ] Report widget "Never mind" cancels cleanly (no `/report` call, composer re-enables); error bubbles offer "Try again".
- [ ] Desktop: aurora animates; `prefers-reduced-motion` disables blob/float animations.

**Known limitation (accepted for POC)**: durable client history is flattened to plain
text turns, so the ≤2 clarifying-question cap is enforced within a turn but the server
cannot count clarifying tool_use blocks from prior turns' client-held history.
