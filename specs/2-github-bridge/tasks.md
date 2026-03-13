# Tasks: Epic 2 — GitHub Bridge

**Feature**: GitHub Repository Connection & Scaffolding
**Branch**: `2-github-bridge`
**Plan**: `specs/2-github-bridge/plan.md`
**Total Tasks**: 27
**Status**: Ready for `/speckit.implement`

---

## User Story Map

| Story | Scenarios | Endpoints | Depends On |
|-------|-----------|-----------|------------|
| US1: Connect Repository | Scenario 1 (happy path) + Scenarios 2–5 (validation errors) | `POST /connect` | Foundation |
| US2: Connection Lifecycle | Scenarios 6, 7, 8 (status, rotate, disconnect) | `GET /connection`, `PATCH /connection/token`, `DELETE /connection` | US1 |
| US3: Scaffolding & Config | Scenario 9 (re-scaffold) + FR-4 (config management) | `POST /scaffold`, `GET /config`, `PUT /config` | Foundation |

---

## Phase 1: Setup

- [X] T001 Add `respx` to requirements.txt
- [X] T002 Add `GITHUB_TOKEN_ENCRYPTION_KEY` to .env with a generated Fernet key value
- [X] T003 Add `GITHUB_TOKEN_ENCRYPTION_KEY: str` field to `Settings` class in src/config.py

---

## Phase 2: Foundation

> Blocking prerequisite for all user stories. Must complete in full before Phase 3.

- [X] T004 [P] Create `GitHubConnection` SQLAlchemy model (id, repository_url, encrypted_token, status, connected_by FK, connected_at, last_validated_at, last_scaffolded_at) in src/models/github_connection.py
- [X] T005 [P] Create `RepoStructureConfig` SQLAlchemy model (id, folders JSONB, is_default, created_by FK, updated_at) in src/models/repo_structure_config.py
- [X] T006 [P] Create `ScaffoldingRun` SQLAlchemy model (id, connection_id FK, triggered_by FK, ran_at, folders_created, folders_skipped, outcome, error_detail) in src/models/scaffolding_run.py
- [X] T007 Export `GitHubConnection`, `RepoStructureConfig`, `ScaffoldingRun` from src/models/__init__.py
- [X] T008 Create Alembic migration `003_create_github_tables.py` in migrations/versions/ — creates github_connections (with partial unique index `WHERE status = 'active'`), repo_structure_configs, scaffolding_runs tables with all indexes and foreign keys; includes downgrade()
- [X] T009 [P] Implement `utils/crypto.py` with `encrypt_token(plaintext: str) -> str` and `decrypt_token(ciphertext: str) -> str` using `cryptography.fernet.Fernet`; key loaded from `settings.GITHUB_TOKEN_ENCRYPTION_KEY`; encrypted values prefixed `v1:<ciphertext>`; raises `EnvironmentError` if key missing
- [X] T010 Implement `utils/github_api.py` with: `GitHubValidationError(code, message, missing_permissions)`, `GitHubUnavailableError`, `parse_repository_url(url) -> tuple[str, str]` (owner, repo), `validate_and_check_access(repository_url, token) -> None` (two-step: GET /user then GET /repos/{owner}/{repo}), `scaffold_repository(repository_url, token, folders) -> tuple[int, int]` (creates .gitkeep for missing folders, returns (created, skipped)); timeout `httpx.Timeout(10.0, connect=5.0)`
- [X] T011 [P] Write unit tests for encrypt/decrypt roundtrip, wrong key raises InvalidToken, missing env var raises at init, version prefix present in ciphertext in tests/utils/test_crypto.py
- [X] T012 [P] Write unit tests for all GitHub API error mappings using `respx` mocks (TOKEN_INVALID on 401, REPO_NOT_FOUND on 404, REPO_ACCESS_DENIED on 403, INSUFFICIENT_PERMISSIONS on push=false, GITHUB_UNAVAILABLE on timeout/5xx, scaffold creates missing folders and skips existing) in tests/utils/test_github_api.py
- [X] T013 Add default `RepoStructureConfig` seeding to `_lifespan()` in src/main.py — inserts default folders config if no `repo_structure_configs` row exists; import new models in lifespan block

---

## Phase 3: US1 — Connect Repository

**Goal**: Admin provides a repo URL + PAT, platform validates and connects, auto-scaffolds the folder structure.

**Independent test criteria**: `POST /api/v1/github/connect` with a mocked GitHub API returns 201 with scaffolding summary; invalid token returns 422 with no DB rows created.

- [X] T014 [US1] Create `src/api/github.py` with `APIRouter(prefix="/github", tags=["github"])` and implement `POST /connect` endpoint: check no active connection (409), validate URL format, call `validate_and_check_access()` (map `GitHubValidationError` → 422, `GitHubUnavailableError` → 503), encrypt token, insert `GitHubConnection`, flush, validate config, call `scaffold_repository()`, insert `ScaffoldingRun`, update `last_scaffolded_at`, `write_audit(action="github_connected")`, commit, return 201
- [X] T015 [US1] Mount github router in `src/main.py` `create_app()` with `prefix="/api/v1"`
- [X] T016 [US1] Add `GITHUB_TOKEN_ENCRYPTION_KEY` test fixture to `tests/conftest.py` — patches `settings.GITHUB_TOKEN_ENCRYPTION_KEY` with a generated test Fernet key for all tests
- [X] T017 [US1] Write integration tests for `POST /connect`: happy path (201, scaffolding summary, token not in response), TOKEN_INVALID (422, no DB rows), REPO_NOT_FOUND (422, no DB rows), INSUFFICIENT_PERMISSIONS (422, missing_permissions in response), GITHUB_UNAVAILABLE (503, no DB rows), duplicate connect (409), non-admin (403) in tests/api/test_github.py

---

## Phase 4: US2 — Connection Lifecycle

**Goal**: Admin can view connection status, rotate the access token, and disconnect the repository.

**Independent test criteria**: Each of the three lifecycle endpoints returns correct status/body; failed rotation leaves existing token unchanged; disconnect transitions status to inactive.

- [X] T018 [US2] Implement `GET /connection` in src/api/github.py — fetch active connection (404 if none), return status, repository_url, connected_at, last_validated_at, last_scaffolded_at, `token_on_file: true`; never return encrypted_token field
- [X] T019 [US2] Implement `PATCH /connection/token` in src/api/github.py — fetch active connection (404 if none), call `validate_and_check_access()` with new token against existing repository_url (leave connection unchanged on failure), on success update encrypted_token + last_validated_at, `write_audit(action="github_token_rotated")`, commit, return 200
- [X] T020 [US2] Implement `DELETE /connection` in src/api/github.py — fetch active connection (404 if none), set `status = "inactive"`, `write_audit(action="github_disconnected")`, commit, return 204
- [X] T021 [US2] Write integration tests: GET /connection (200 with token_on_file, no token value), GET /connection when none (404), PATCH /connection/token happy path (200, last_validated_at updated), PATCH rotation with bad token (422, existing token unchanged), DELETE (204, status=inactive), DELETE when none (404), non-admin (403 on all three) in tests/api/test_github.py

---

## Phase 5: US3 — Scaffolding & Config Management

**Goal**: Admin can re-run scaffolding manually, view the folder structure configuration, and replace it with a custom one.

**Independent test criteria**: Re-running scaffold on a fully initialized repository returns folders_created=0, folders_skipped=N; custom config is used on the next scaffold run; malformed config returns 400.

- [X] T022 [US3] Implement `POST /scaffold` in src/api/github.py — fetch active connection (404 if none), load active config, validate config (400 + CONFIG_INVALID if malformed), decrypt token, call `scaffold_repository()`, insert `ScaffoldingRun`, update `connection.last_scaffolded_at`, `write_audit(action="github_scaffolded")`, commit, return 200 with run summary
- [X] T023 [US3] [P] Implement `GET /config` in src/api/github.py — return active RepoStructureConfig (id, folders, is_default, updated_at); always returns 200 (default is seeded on startup)
- [X] T024 [US3] [P] Implement `PUT /config` in src/api/github.py — validate folders array (non-empty, no `..`, no leading/trailing slashes, max 200 entries) (400 + CONFIG_INVALID if invalid), upsert the non-default config row (update if exists, insert if not), set `created_by` from current user, return 200 with updated config
- [X] T025 [US3] Write integration tests: POST /scaffold happy path (200, folders_created + folders_skipped), POST /scaffold idempotent (all folders_skipped on second run), POST /scaffold no connection (404), POST /scaffold with invalid config (400), GET /config returns default (200), PUT /config with valid folders (200), PUT /config with empty folders (400), PUT /config with path traversal (400), non-admin (403 on all three) in tests/api/test_github.py

---

## Phase 6: Polish

- [X] T026 Assert token value never appears in any API response body across all tests in tests/api/test_github.py — add a reusable `assert_no_token` helper and call it on every response in the test file
- [X] T027 Verify all 50 tasks in specs/1-epic-1-iam/tasks.md are marked `[X]` and all 27 tasks in this file are marked `[X]` before closing the epic

---

## Dependency Graph

```
T001 → T002 → T003
              │
              ▼
T004 ─┐
T005 ─┤→ T007 → T008 → T013
T006 ─┘
T009 ──────────────────────┐
T010 ──────────────────────┤→ T014 → T015 → T016 → T017  [US1 complete]
T011 (parallel with T009)  │         │
T012 (parallel with T010)  │         └──────────────────→ T018 → T019 → T020 → T021  [US2 complete]
                            │
                            └──────────────────────────→ T022 → T023 → T024 → T025  [US3 complete]

T017 + T021 + T025 → T026 → T027
```

---

## Parallel Execution Opportunities

| Parallel Group | Tasks | Condition |
|----------------|-------|-----------|
| Model creation | T004, T005, T006 | All touch different files |
| Utility creation | T009, T010 | Different files; T010 must not call T009 yet |
| Unit tests | T011, T012 | Different test files; no shared state |
| Config endpoints | T023, T024 | Different handlers in same file — implement sequentially if editing same function block |

---

## Implementation Strategy

**MVP scope (minimum shippable)**: Phases 1–3 (T001–T017). Delivers the core connect + scaffold flow with full validation error handling.

**Full epic**: All phases. Adds lifecycle management (token rotation, disconnect, status) and config management.

**Key sequencing rule**: T014 (POST /connect) is the most complex task. Implement it last in Phase 3 after T009 (crypto), T010 (github_api), and T013 (config seeding) are all complete and their unit tests pass.
