## 1. Contract

- [ ] 1.1 `backend/contracts/models.py`: add `session_id: str` to `Session` (unique, stable; `default_factory` generates a uuid when not supplied).

## 2. Agent wiring

- [ ] 2.1 `backend/agent/loop.py`: trace with `thread_id=session.session_id` (all three `update_current_trace` call sites) instead of `session.client_code`.

## 3. Done condition & test

- [ ] 3.1 `openspec validate cho-59-add-session-identity --strict` passes.
- [ ] 3.2 Test: `Session(...).session_id` is populated and stable for a given object; two `Session`s constructed without an explicit id get distinct ids. `pytest backend/contracts backend/agent`.
