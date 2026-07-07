# session-auth Specification

## Purpose
TBD - created by archiving change cho-56-api-sse-session. Update Purpose after archive.
## Requirements
### Requirement: Session creation from trimmed login inputs

The system SHALL provide `POST /session` accepting `{userId, mobileNo, sessionToken}` (and optional `clientCode`), stripping leading/trailing whitespace on every input, creating an in-memory `Session`, and returning `{session_id}`. The `sessionToken` (JWT) SHALL be retained for downstream FinX report calls.

#### Scenario: Inputs are trimmed and a session is created

- **WHEN** `POST /session` is called with values containing surrounding whitespace
- **THEN** the stored `Session` holds the trimmed `user_id`, `mobile_no`, and `session_token`, and the response returns a `session_id`

#### Scenario: Session token is available to report tools

- **WHEN** a later `/report` call references the `session_id`
- **THEN** the stored `session_token` is used as the FinX `Authorization` header

