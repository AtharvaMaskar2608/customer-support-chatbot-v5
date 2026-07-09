# Design: finx-reports-contracts

## Context

Today `ReportRequestEvent` carries a flat `fields: list[str]` and the frontend maps field names to inputs via `FIELD_META`. The new report suite needs *chained* widgets (pick a variant card, then a date range) and per-report option sets, so the event must become a declarative widget spec. Separately, report results will no longer be summarized by the model (locked decision: option b), so a render-payload contract is needed between `POST /report` and the frontend.

This change lands **only contract shapes** in `main` so that backend (B), frontend (C), and evals (D) can build in parallel against the same types.

## Goals / Non-Goals

**Goals:**
- Single-sourced widget-step and render-payload contracts, additive to existing models.
- `Session` can carry the FinX middleware SessionId.
- Repo stays green at every merge point (old code untouched and working).

**Non-Goals:**
- No tool implementations, no agent-loop changes, no frontend changes, no deletion of legacy shapes (all in change B/C).
- No per-report widget definitions (which cards a `ledger` request shows) — those live with the tool registry in change B; this change defines only the *types*.

## Decisions

### D1 — Declarative `steps` on `ReportRequestEvent` (replaces flat `fields`, additive for now)

```python
class CardOption(BaseModel):        # frozen
    label: str                      # "MTF Ledger"
    value: str                      # "MTF"  (opaque to frontend; backend maps to API Group)

class CardStep(BaseModel):          # frozen
    kind: Literal["cards"] = "cards"
    param: str                      # e.g. "group" / "fin_year"
    options: tuple[CardOption, ...]

class DateRangeStep(BaseModel):     # frozen
    kind: Literal["date_range"] = "date_range"
    from_param: str = "from_date"   # YYYY-MM-DD, no default value in the UI
    to_param: str = "to_date"

WidgetStep = Annotated[Union[CardStep, DateRangeStep], Field(discriminator="kind")]

class ReportRequestEvent(BaseModel):
    type: Literal["report_request"] = "report_request"
    report_type: Literal[
        "ledger", "global_pnl", "detailed_pnl", "contract_notes", "tax_report",
        "cml", "contract_note",   # legacy; removed by finx-middleware-tools
    ]
    steps: list[WidgetStep] = []    # new path; frontend chains these in order
    fields: list[str] = []          # legacy path; removed by finx-middleware-tools
    tool_use_id: str
```

Rationale: two widget primitives (cards, date range) compose every report in the FinX docs; a discriminated union keeps the frontend renderer a dumb switch. Alternative considered — per-report bespoke event types — rejected: five near-identical events and a wider frontend surface.

### D2 — `ReportRenderPayload` in `contracts/models.py`

```python
class ReportColumn(BaseModel):      # frozen
    key: str                        # row dict key, e.g. "Narration"
    label: str                      # header text, e.g. "Description"

class ReportRenderPayload(BaseModel):  # frozen
    kind: Literal["table", "link", "empty", "error"]
    title: str                      # e.g. "MTF Ledger · 2026-04-01 → 2026-07-15"
    columns: tuple[ReportColumn, ...] = ()   # kind == "table"
    rows: tuple[dict, ...] = ()              # kind == "table"; row dicts keyed by column key
    url: str | None = None                   # kind == "link" (tax report PDF)
    message: str | None = None               # kind == "empty" | "error" (e.g. "Data not found.")
```

This is the response body of the reworked `POST /report` (JSON, no longer SSE — implemented in B, consumed in C). Rationale: results bypass the LLM entirely (locked decision b); backend shapes rows/columns server-side so the frontend renderer stays generic. The tax-report URL rides only in this payload — never into model context — because generated report URLs are unauthenticated.

### D3 — `Session` gains `finx_session_id: str = ""` (additive); JWT `session_token` stays

The login page will collect both tokens (user decision). Default `""` keeps every existing constructor and test valid; requiredness is enforced at the API boundary in change B (`POST /session` rejects a blank `finxSessionId`) and in the form in change C. `client_code` is already required on the model.

### D4 — Additive-then-remove migration

A lands additive shapes → B deletes legacy literals, `fields`, old tools, and old base-URL settings → C switches the frontend. The repo is green after each merge; nothing depends on ordering between B and C because both consume only what A landed. Alternative — one big breaking change — rejected: it would force B and C into a single serialized change.

### D5 — Settings

`finx_middleware_base_url: str = Field("https://finx.choiceindia.com", alias="FINX_MIDDLEWARE_BASE_URL")`. The `from: Web_finx.choiceindia.com_V_4.6.0.4` header is a client constant in B, not a setting — it is protocol detail, not deployment config.

## Risks / Trade-offs

- [Legacy + new shapes coexist briefly] → confined to one sprint; B's task list includes the removals, and the archived spec will show only the end state.
- [`rows: tuple[dict, ...]` is loosely typed] → deliberate: five reports with unknown/partially-documented success schemas (docs flag PNL/contract-note success bodies as "pending capture"); backend B normalizes rows, and tightening per-report row models later is additive.
- [Frontend must treat `CardOption.value` as opaque] → values are FinX API tokens ("MTF", "Cash", "Group23", "2025-2026"); the contract docstring states the frontend never interprets them.
