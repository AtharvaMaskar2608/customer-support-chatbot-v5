# project-configuration Specification

## Purpose
TBD - created by archiving change cho-50-foundations-and-contracts. Update Purpose after archive.
## Requirements
### Requirement: Environment-driven settings loader

The system SHALL load all runtime configuration from environment variables (via `.env`) into a single typed `Settings` object, with no connection details, model names, or secrets hardcoded in source.

#### Scenario: Required settings present

- **WHEN** the application starts with a `.env` providing `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FINX_CML_BASE_URL`, and `FINX_CONTRACT_NOTE_BASE_URL`
- **THEN** `get_settings()` returns a populated `Settings` object exposing those values as typed attributes

#### Scenario: Missing required setting fails fast

- **WHEN** a required setting (e.g. `DATABASE_URL`) is absent at startup
- **THEN** loading raises a validation error immediately, before any request is served

### Requirement: Configurable model and embedding defaults

The system SHALL expose `anthropic_model` (default `claude-sonnet-4-5`) and `embedding_model` (default `text-embedding-3-large`) as overridable settings.

#### Scenario: Override the model via env

- **WHEN** `ANTHROPIC_MODEL` is set to a different value in the environment
- **THEN** `get_settings().anthropic_model` reflects the override rather than the default

### Requirement: FinX middleware base URL setting

The system SHALL expose `finx_middleware_base_url` (env `FINX_MIDDLEWARE_BASE_URL`, default `https://finx.choiceindia.com`) on `Settings`, as the single base URL for all FinX middleware report endpoints (`/api/middleware/*` and `/middleware-go/*`). Legacy `finx_cml_base_url` / `finx_contract_note_base_url` remain until their consumers are deleted by the `finx-middleware-tools` change.

#### Scenario: Default middleware base URL

- **WHEN** `FINX_MIDDLEWARE_BASE_URL` is not set in the environment
- **THEN** `get_settings().finx_middleware_base_url` is `https://finx.choiceindia.com`

#### Scenario: Override via environment

- **WHEN** `FINX_MIDDLEWARE_BASE_URL` is set (e.g. to a staging host)
- **THEN** `get_settings().finx_middleware_base_url` reflects the override

