# session-auth — delta for finx-middleware-tools

## MODIFIED Requirements

### Requirement: Session creation from trimmed login inputs

The system SHALL provide `POST /session` accepting `{userId, mobileNo, sessionToken, finxSessionId, clientCode}`, stripping leading/trailing whitespace on every input, creating an in-memory `Session`, and returning `{session_id}`. `finxSessionId` (the FinX middleware SessionId) and `clientCode` SHALL be required and non-empty after trimming — every middleware report call needs both. `sessionToken` (legacy JWT) continues to be accepted and stored but no longer authorizes any report call.

#### Scenario: Inputs are trimmed and a session is created

- **WHEN** `POST /session` is called with values containing surrounding whitespace
- **THEN** the stored `Session` holds the trimmed `user_id`, `mobile_no`, `session_token`, `finx_session_id`, and `client_code`, and the response returns a `session_id`

#### Scenario: Blank FinX session id or client code is rejected

- **WHEN** `finxSessionId` or `clientCode` is missing or blank after trimming
- **THEN** `POST /session` fails with a validation error and no session is created

#### Scenario: FinX session id is available to report calls

- **WHEN** a later `/report` call references the `session_id`
- **THEN** the stored `finx_session_id` is used as the middleware `authorization` header (and body `SessionId` where the endpoint requires it), and `client_code` supplies `ClientId`
