# project-configuration — delta for finx-reports-contracts

## ADDED Requirements

### Requirement: FinX middleware base URL setting

The system SHALL expose `finx_middleware_base_url` (env `FINX_MIDDLEWARE_BASE_URL`, default `https://finx.choiceindia.com`) on `Settings`, as the single base URL for all FinX middleware report endpoints (`/api/middleware/*` and `/middleware-go/*`). Legacy `finx_cml_base_url` / `finx_contract_note_base_url` remain until their consumers are deleted by the `finx-middleware-tools` change.

#### Scenario: Default middleware base URL

- **WHEN** `FINX_MIDDLEWARE_BASE_URL` is not set in the environment
- **THEN** `get_settings().finx_middleware_base_url` is `https://finx.choiceindia.com`

#### Scenario: Override via environment

- **WHEN** `FINX_MIDDLEWARE_BASE_URL` is set (e.g. to a staging host)
- **THEN** `get_settings().finx_middleware_base_url` reflects the override
