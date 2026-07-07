## Why

The agent needs read-only access to FinX MIS reports so it can answer report questions without a human. Phase 1 covers two: the **CML report** and the **Contract Note**. Each is a simple authenticated HTTP call, but both must be exposed to the agent as Anthropic tools and must never crash the agent loop on an upstream failure.

## What Changes

- Add two httpx report clients + their Anthropic tool schemas:
  - **CML:** `POST {FINX_CML_BASE_URL}/mis/reports/generate`, body `{"reportType":"cml","searchBy":"client-id","searchValue":<clientId>}`.
  - **Contract Note:** `POST {FINX_CONTRACT_NOTE_BASE_URL}/mis/v2/contract-note/generate`, body `{"mobileNo":<mobile>,"contractDate":"DD-MM-YYYY"}`.
- Shared headers on every call: `Authorization: <session JWT>`, `authType: jwt`, `source: FINX_WEB`.
- Tools **never raise** — every failure (network, non-2xx, timeout) maps to `ReportResult(ok=False, error=...)`.

## Capabilities

### New Capabilities
- `finx-report-tools`: read-only CML and Contract Note report tools with Anthropic tool schemas and non-raising error handling.

## Impact

- New: `backend/tools/finx.py` (clients), `backend/tools/schemas.py` (Anthropic tool defs), `backend/tools/__init__.py`.
- Imports `Session`, `ReportResult`, and `Settings` from foundations (`data-contracts`, `project-configuration`). Adds no root dependencies (`httpx` declared by foundations).
- Consumed by the agent (`agentic-loop`), which registers these tool schemas and dispatches calls.
