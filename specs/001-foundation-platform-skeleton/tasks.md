---

description: "Task list for Phase 1 Foundation — Platform Skeleton & Role-Based Access"
---

# Tasks: Phase 1 Foundation — Platform Skeleton & Role-Based Access

**Input**: Design documents from `/specs/001-foundation-platform-skeleton/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included. The spec requires them explicitly — FR-029 through FR-034 mandate an automated suite, RBAC-refusal tests, and audit-immutability tests, and constitution Principle V ("Test-First for Business Rules — NON-NEGOTIABLE") requires RBAC decisions and audit-immutability tests to be written before the code they cover. Tests within each story are ordered before their implementation tasks and MUST fail first.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- File paths are exact and match `plan.md`'s Project Structure

## Path Conventions

Single Django project at repository root (per plan.md): `config/` (project settings/urls), `apps/<name>/` (Django apps), `tests/` (cross-app integration tests), `docker/`, `scripts/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository scaffolding, dependency manifest, and Docker image definition — nothing here is Django-app code yet.

- [X] T001 Create root directories per plan.md's Project Structure: `config/`, `apps/`, `docker/django/`, `scripts/`, `tests/integration/` (empty `__init__.py` where Python packages are needed)
- [X] T002 Create `pyproject.toml` with dependencies: Django 5.1.x, djangorestframework 3.15.x, psycopg[binary] 3.x, redis 5.x, django-environ, gunicorn, and dev/test deps pytest, pytest-django, pytest-cov, factory-boy; include `[tool.pytest.ini_options]` (`DJANGO_SETTINGS_MODULE=config.settings.test`, testpaths) and `[tool.coverage.run]` (`source = ["apps", "config"]`)
- [X] T003 [P] Create `docker/django/Dockerfile` using `python:3.13-slim-bookworm`, installing `pyproject.toml` dependencies, copying the project, and setting the container entrypoint to `scripts/entrypoint.sh`
- [X] T004 [P] Create `scripts/entrypoint.sh`: wait for Postgres to accept connections, run `python manage.py migrate`, then exec `gunicorn config.wsgi:application --bind 0.0.0.0:8000`; make it executable
- [X] T005 [P] Create `.env.example` listing every required setting from research.md §9 (`SECRET_KEY`, `DEBUG`, `DATABASE_URL` or discrete `POSTGRES_*` vars, `REDIS_URL`, `ALLOWED_HOSTS`) with placeholder (non-real) values
- [X] T006 [P] Create `.gitignore` covering `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `htmlcov/`, `.coverage`, and Python venv directories

**Checkpoint**: Repository has structure, dependency manifest, and container build definition — no application code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Django project configuration, the custom User model (which per research.md §2 MUST be in place before the first migration and cannot be swapped later), the single RBAC mechanism, Docker Compose orchestration, and the pytest/Factory Boy harness. Every user story depends on this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. In particular, the custom `User` model and its first migration must land before any other app's migrations, since `AUTH_USER_MODEL` cannot be changed afterward without a destructive reset.

- [X] T007 `manage.py` at repository root, pointing to `config.settings.dev` by default (per Django's standard generated file, adapted for the `config/` layout)
- [X] T008 `config/__init__.py`, `config/wsgi.py`, `config/asgi.py` (standard Django project files referencing `config.settings`)
- [X] T009 `config/settings/base.py`: shared settings, `INSTALLED_APPS` (django admin/auth/contenttypes/sessions, rest_framework, apps.core, apps.accounts, apps.audit, apps.health, apps.customers, apps.policies, apps.claims), `AUTH_USER_MODEL = "accounts.User"`, `django-environ` setup, and an explicit `REQUIRED_SETTINGS` list validated at the bottom of the file that raises `ImproperlyConfigured` naming every missing key (FR-004, FR-005, research.md §9)
- [X] T010 [P] `config/settings/dev.py`: imports `base`, sets `DEBUG` from env, local-development overrides
- [X] T011 [P] `config/settings/test.py`: imports `base`, sets `PASSWORD_HASHERS` to `MD5PasswordHasher` only (research.md §11), test-specific `DATABASES` override if needed
- [X] T012 `config/urls.py`: root URLconf mounting `apps.health.urls` at `/health/` and each app's urls under `/api/` (`/api/users/`, `/api/audit/`, `/api/auth/`, `/api/customers/`, `/api/policies/`, `/api/claims/`)
- [X] T013 `apps/core/__init__.py`, `apps/core/apps.py` (AppConfig) and `apps/core/models.py` with `TimeStampedModel` abstract base (created/updated timestamps) for reuse by later modules
- [X] T014 `apps/core/permissions.py`: implement `HasRole(*roles)` DRF permission class factory per research.md §4 — checks `request.user.role` membership only (no `is_superuser` bypass), deny-by-default for null/blank/unrecognised role, and raises `NotFound` (not `PermissionDenied`) for unauthenticated/unpermitted callers on detail-view contexts so FR-012's 404-not-403 rule holds
- [X] T015 [P] `apps/accounts/__init__.py`, `apps/accounts/apps.py`
- [X] T016 `apps/accounts/models.py`: `Role(TextChoices)` enum with the nine values from data-model.md, and `User(AbstractBaseUser, PermissionsMixin)` with `email` (unique, `USERNAME_FIELD`), `first_name`, `last_name`, `role` (required, `choices=Role.choices`), `is_active`, `is_staff`, `is_superuser`, `date_joined`, `REQUIRED_FIELDS = ["role"]`, plus a `Meta.constraints` `CheckConstraint` named `user_role_valid` restricting `role` to the nine values
- [X] T017 `apps/accounts/managers.py`: `UserManager` with `create_user(email, password, role, **extra)` and `create_superuser(...)`, both requiring `role`, normalizing email to lowercase
- [X] T018 Generate and commit the **first** migration for `apps/accounts` (`apps/accounts/migrations/0001_initial.py`) via `makemigrations accounts` — must be the first migration applied in the project since it defines `AUTH_USER_MODEL` (research.md §2)
- [X] T019 [P] `apps/accounts/admin.py`: register `User` in Django admin (needed for `PermissionsMixin`/`is_staff` per research.md §2), excluding raw password display
- [X] T020 [P] `apps/accounts/factories.py`: `UserFactory` (Factory Boy) producing a valid `User` with a default role, plus a `role` parameter/traits so any of the nine roles is a single call (FR-030), using `Faker` for email/name and Django's password hasher for password
- [X] T021 [P] `apps/audit/__init__.py`, `apps/audit/apps.py`
- [X] T022 `apps/audit/models.py`: `AuditLog` model per data-model.md (`timestamp`, `actor` FK `SET_NULL` to `accounts.User`, `actor_identifier`, `actor_role`, `action`, `target_type`, `target_id`, `outcome` choices `succeeded`/`refused`, `before`/`after`/`context` JSONFields), indexes on `(target_type, target_id, timestamp)`, `timestamp`, `actor`; override `save()` to raise on update (`self.pk` already set) and `delete()` to raise; custom manager/queryset overriding `update()`/`delete()` to raise
- [X] T023 Generate the `apps/audit` initial migration including a `migrations.RunSQL` operation that installs a PostgreSQL `BEFORE UPDATE OR DELETE ON audit_auditlog` trigger (`audit_log_immutable`) raising an exception, with matching reverse SQL to drop it (research.md §5)
- [X] T024 [P] `apps/audit/services.py`: `record_action(actor, action, target_type, target_id, outcome, before=None, after=None, context=None)` — writes one `AuditLog` row, called inside the caller's `transaction.atomic()` block (FR-022, research.md §6)
- [X] T025 [P] `apps/audit/factories.py`: `AuditLogFactory` (Factory Boy) for constructing audit records directly in tests
- [X] T026 [P] `apps/health/__init__.py`, `apps/health/apps.py`
- [X] T027 `apps/health/checks.py`: `check_database()` and `check_cache()` functions, each with a 2-second bounded timeout (Postgres `connect_timeout=2` via a fresh connection, Redis `PING` with `socket_connect_timeout=2`/`socket_timeout=2`), catching all exceptions and returning `"ok"`/`"error"` — never raising (research.md §8)
- [X] T028 [P] `tests/conftest.py`: shared fixtures — `api_client` (DRF `APIClient`), `user_in_role` (factory fixture wrapping `UserFactory` per role), `authenticated_client` helper
- [X] T029 Configure `docker-compose.yml` at repo root: `web` (build from `docker/django/Dockerfile`, env from `.env`, port 8000 published, `depends_on` both `db` and `redis` with `condition: service_healthy`), `db` (`postgres:16-alpine`, named volume `postgres_data`, `pg_isready` healthcheck, ports not published), `redis` (`redis:7-alpine`, `--appendonly yes`, named volume `redis_data`, `redis-cli ping` healthcheck, ports not published) — per research.md §10
- [X] T030 Verify the foundational stack boots: `docker compose up --build -d`, confirm all three services reach `running`/`healthy`, `python manage.py migrate` applies cleanly inside the container, then `docker compose down`

**Checkpoint**: Django project boots under Docker Compose, the custom `User` model and RBAC mechanism exist, the audit log is append-only at both ORM and DB layers, health check probes work, and the test harness (pytest/Factory Boy/coverage) is wired. User story implementation can now begin.

---

## Phase 3: User Story 1 - Platform Operator Runs the Whole System Locally (Priority: P1) 🎯 MVP

**Goal**: A fresh clone, brought up with `cp .env.example .env` + `docker compose up --build -d`, reaches a running application, database, and cache with no external network dependency, and retains data across a restart.

**Independent Test**: On a clean machine with only the container runtime, follow quickstart.md's Setup section from a fresh clone; confirm all services reach a running state and `/health/` responds (uses the `/health/` endpoint built as part of foundational work in Phase 2, since Story 1's acceptance criteria depend on an observable liveness signal — the full contract for that endpoint is delivered in Story 4).

### Tests for User Story 1

- [X] T031 [P] [US1] Integration test in `tests/integration/test_environment.py`: `docker compose ps`-equivalent smoke assertion is out of scope for pytest (it's a container-level check); instead write a pytest test that opens a real DB connection and a real Redis connection using the configured settings and asserts both succeed, proving the Django app's configuration correctly reaches both services
- [X] T032 [P] [US1] Test in `apps/core/tests/test_settings.py`: instantiate settings with a required env var missing (via `override_settings`/subprocess invocation of `manage.py check` with a stripped env) and assert `ImproperlyConfigured` is raised naming the missing setting (FR-005)

### Implementation for User Story 1

- [X] T033 [US1] `README.md` at repo root (or `docs/setup.md` if preferred): document the exact setup sequence from quickstart.md — clone, `cp .env.example .env`, `docker compose up --build -d`, `createsuperuser`, verifying `/health/` — written so a first-time operator needs no source-code reading (FR-007, SC-001)
- [X] T034 [US1] Add a commented-out host port mapping for `db` in `docker-compose.yml` for operators who want local `psql` access, without publishing it by default (research.md §10)
- [X] T035 [US1] Manually verify SC-010 (data survives restart) and SC-011 (no external network dependency) per quickstart.md Scenario 1b/1c, and record confirmation in the PR/commit description

**Checkpoint**: User Story 1 is independently functional — the platform starts, persists data, and requires no outbound network access.

---

## Phase 4: User Story 2 - Administrator Assigns Roles and the System Enforces Them (Priority: P1)

**Goal**: A System Administrator creates accounts with exactly one of the nine roles; every restricted action is decided server-side; unpermitted and unauthenticated callers are refused without disclosing record existence; role changes take effect immediately.

**Independent Test**: Create one account per role, attempt a restricted action (`POST /api/users/`) as each, and confirm only System Administrator succeeds while all others (and unauthenticated callers) are refused, per contracts/users.md's RBAC test matrix.

### Tests for User Story 2

- [X] T036 [P] [US2] Contract/unit test in `apps/accounts/tests/test_models.py`: assert `User` rejects a role outside the nine values at both `full_clean()` and DB `CheckConstraint` level (raw SQL insert / `QuerySet.update()` bypassing validation) — FR-010
- [X] T037 [P] [US2] Unit test in `apps/core/tests/test_permissions.py`: exercise `HasRole` directly — unauthenticated denied, wrong role denied, correct role allowed, null/blank/unrecognised role denied (FR-014), `is_superuser=True` with a non-permitted role still denied (spec edge case)
- [X] T038 [P] [US2] Contract test in `apps/accounts/tests/test_views.py`: full RBAC matrix from contracts/users.md against `POST /api/users/` and `GET /api/users/{id}/` — all nine roles plus unauthenticated, asserting `201`/`200` only for System Administrator, `403` for unauthenticated/wrong-role on the collection route, `404` for unauthenticated/wrong-role on the detail route (FR-033, SC-002, SC-003)
- [X] T039 [P] [US2] Test in `apps/accounts/tests/test_views.py`: `POST /api/users/` with an invalid `role` value returns `400` naming the field, no account created (FR-010)
- [X] T040 [P] [US2] Test in `apps/accounts/tests/test_views.py`: `PATCH /api/users/{id}/` role change by System Administrator succeeds, and the affected user's *next* request is evaluated against the new role with no restart/re-login (FR-016)
- [X] T041 [P] [US2] Test in `apps/accounts/tests/test_factories.py`: `UserFactory` produces a valid user for each of the nine roles in a single call with no extra field setup (FR-030, SC-009)

### Implementation for User Story 2

- [X] T042 [P] [US2] `apps/accounts/serializers.py`: `UserSerializer` (create: email/password/first_name/last_name/role; response: excludes password; role validated against `Role.choices`) and a separate read serializer if needed for `GET`
- [X] T043 [US2] `apps/accounts/views.py`: `UserViewSet` (or explicit `CreateAPIView`/`RetrieveUpdateAPIView`) implementing `POST /api/users/`, `GET /api/users/`, `GET /api/users/{id}/`, `PATCH /api/users/{id}/`, permission_classes using `HasRole(Role.SYSTEM_ADMINISTRATOR)`, writing `user.created`/`user.role_changed`/`user.updated`/`user.deactivated` audit records via `record_action()` inside the request's transaction (FR-017, FR-020)
- [X] T044 [US2] `apps/accounts/urls.py`: route `/api/users/` and `/api/users/{id}/` to the views from T043
- [X] T045 [US2] Wire Django session auth endpoints in `config/urls.py` or a small `apps/accounts` auth view module: `POST /api/auth/login/`, `POST /api/auth/logout/` per contracts/users.md (generic failure message on bad credentials, inactive accounts cannot sign in)
- [X] T046 [US2] `apps/customers/`, `apps/policies/`, `apps/claims/` placeholder apps: each with `apps.py`, `urls.py`, and a single `GET .../placeholder/` view restricted via `HasRole` to the roles listed in contracts/README.md's placeholder table (System Administrator plus two module-specific roles each), returning the documented `{"module": ..., "status": "placeholder"}` body
- [X] T047 [P] [US2] Test in `apps/customers/tests/test_views.py`, `apps/policies/tests/test_views.py`, `apps/claims/tests/test_views.py`: each placeholder endpoint permits its documented roles and refuses all others plus unauthenticated (403 on these collection routes) — completes FR-033's "at least one placeholder per module" coverage

**Checkpoint**: User Stories 1 AND 2 both work independently — the platform runs, and role-based access is enforced server-side for every account-management action.

---

## Phase 5: User Story 3 - Compliance Officer Sees an Unalterable Record of Sensitive Actions (Priority: P2)

**Goal**: Every user-account creation and role change writes an append-only audit record with actor, action, target, timestamp, outcome, and before/after state; no part of the platform can modify or delete an existing record; a Compliance Officer can retrieve a record's history in chronological order.

**Independent Test**: Perform an administrative action that changes a user account, confirm a corresponding audit record exists with the required fields, then attempt to alter or delete it and confirm the attempt fails at both ORM and database layers.

### Tests for User Story 3

- [X] T048 [P] [US3] Unit test in `apps/audit/tests/test_models.py`: `AuditLog.save()` raises on update of an existing record; `.delete()` raises; queryset `.update()`/`.delete()` raise (FR-019, SC-005 — ORM layer)
- [X] T049 [P] [US3] Integration test in `apps/audit/tests/test_immutability_db.py`: using a raw DB cursor (bypassing the ORM entirely), attempt `UPDATE audit_auditlog ...` and `DELETE FROM audit_auditlog ...` against an existing row and assert the database trigger rejects both (FR-019, SC-005 — DB layer, research.md §5)
- [X] T050 [P] [US3] Test in `apps/audit/tests/test_services.py`: `record_action()` writes a row with all required fields populated inside the caller's transaction; simulate an audit-insert failure (e.g. invalid `outcome` value or mocked DB error) mid-transaction and assert the *enclosing* action's changes are rolled back too (FR-022, edge case "audit write fails while the action succeeds")
- [X] T051 [P] [US3] Test in `apps/accounts/tests/test_views.py` (or `apps/audit/tests/test_integration.py`): creating a user and then changing their role produces exactly the `user.created` then `user.role_changed` audit entries with correct before/after values (FR-020, SC-004)
- [X] T052 [P] [US3] Test in `apps/audit/tests/test_models.py`: deleting a `User` that has audit entries leaves those entries readable with `actor` null but `actor_identifier`/`actor_role` intact (FR-021)
- [X] T053 [P] [US3] Contract test in `apps/audit/tests/test_views.py`: `GET /api/audit/` and `GET /api/audit/history/{target_type}/{target_id}/` — permitted for Compliance Officer and System Administrator, `403`/`404` respectively for every other role and unauthenticated callers; history endpoint returns entries in ascending chronological order (FR-024)
- [X] T053a [P] [US3] Contract test in `apps/audit/tests/test_views.py`: `GET /api/audit/history/{target_type}/{target_id}/` for a target with **zero** audit entries returns `200` with `{"target_type": ..., "target_id": ..., "count": 0, "results": []}` — explicitly **not** `404`, since the query is about the audit log, not the target record's existence (contracts/audit.md "no history returns 200 with count: 0")
- [X] T053b [P] [US3] Contract test in `apps/audit/tests/test_views.py`: after the acting user's account is deleted, `GET /api/audit/` and the history endpoint still serialize that entry with `actor: null` but `actor_identifier` and `actor_role` populated from the write-time snapshot, matching contracts/audit.md's "Deleted-actor behaviour" example (FR-021 at the API layer, complementing T052's model-layer test)
- [X] T054 [P] [US3] Test in `apps/audit/tests/test_views.py`: `POST`/`PUT`/`PATCH`/`DELETE` on any audit route return `405 Method Not Allowed`

### Implementation for User Story 3

- [X] T055 [P] [US3] `apps/audit/serializers.py`: read-only `AuditLogSerializer` matching the response shape in contracts/audit.md
- [X] T056 [US3] `apps/audit/views.py`: `AuditListView` (`GET /api/audit/` with `target_type`/`target_id`/`actor`/`action`/`ordering` filters, default `-timestamp`) and `AuditHistoryView` (`GET /api/audit/history/{target_type}/{target_id}/`, ascending `timestamp` then `id`), both `permission_classes = [HasRole(Role.COMPLIANCE_OFFICER, Role.SYSTEM_ADMINISTRATOR)]`, read-only (no create/update/delete routes)
- [X] T057 [US3] `apps/audit/urls.py`: route `/api/audit/` and `/api/audit/history/<str:target_type>/<str:target_id>/` to the views from T056

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — audit logging is proven append-only and chronologically retrievable.

---

## Phase 6: User Story 4 - Operator Confirms System Health at a Glance (Priority: P2)

**Goal**: An unauthenticated `GET /health/` reports `200`/`healthy` when Postgres and Redis are reachable, `503`/`unhealthy` identifying the failing dependency otherwise, within 5 seconds, disclosing no sensitive detail.

**Independent Test**: Query `/health/` with all services up (expect `200`), then with the database stopped (expect `503` naming `database`), per quickstart.md Scenario 4.

### Tests for User Story 4

- [X] T058 [P] [US4] Test in `apps/health/tests/test_checks.py`: `check_database()` and `check_cache()` each return `"ok"` when the dependency is reachable and `"error"` (never raising) when connection parameters point somewhere unreachable, completing within their 2-second timeout
- [X] T059 [P] [US4] Contract test in `apps/health/tests/test_views.py`: `GET /health/` with both dependencies healthy returns `200` with the exact three-key body from contracts/health.md; with `check_database`/`check_cache` mocked to fail individually, returns `503` identifying the correct failing dependency while the other stays `ok` (FR-026, FR-027, SC-007)
- [X] T060 [P] [US4] Test in `apps/health/tests/test_views.py`: response body contains only `status` and `checks.{database,cache}.status` — assert absence of any host/port/credential/version/exception-message keys (FR-028); assert no authentication is required
- [X] T061 [P] [US4] Test in `apps/health/tests/test_views.py`: response is returned within a bounded time (assert wall-clock duration in-test is well under 5s) even when a probe would otherwise hang (mock a slow/unresponsive dependency) — FR-027, SC-006

### Implementation for User Story 4

- [X] T062 [US4] `apps/health/views.py`: unauthenticated `APIView` calling `check_database()` and `check_cache()` (both always run, independent of each other), returning `200` if both `ok` else `503`, body per contracts/health.md exactly
- [X] T063 [US4] `apps/health/urls.py`: route `GET /health/` to the view from T062, mounted at the root path (not under `/api/`) in `config/urls.py`
- [X] T064 [US4] Add the `web` service healthcheck to `docker-compose.yml` using the container's own Python against `http://localhost:8000/health/`, per the snippet in contracts/health.md (`interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 30s`)

**Checkpoint**: All four stories so far work independently; the health endpoint is now what Story 1's `depends_on: condition: service_healthy` and quickstart.md's verification both rely on.

---

## Phase 7: User Story 5 - Developer Writes and Runs Automated Tests From Day One (Priority: P2)

**Goal**: `docker compose exec web pytest` runs the full suite to completion with a coverage report in under 2 minutes, against an isolated test database, using `UserFactory` traits for any of the nine roles in one call.

**Independent Test**: Run the test command on a fresh checkout; confirm the suite executes, reports pass/fail, produces coverage, and leaves the development database's row counts unchanged.

**Note**: Most of this story's infrastructure (pytest/pytest-django/factory-boy configuration, `UserFactory`, `tests/conftest.py`) was already built in Phase 2 (Foundational) because every other story's tests depend on it. This phase's remaining tasks close the gaps that only become verifiable once all stories exist: full-suite runtime, isolation, and the coverage command itself.

### Tests for User Story 5

- [X] T065 [P] [US5] Test in `tests/integration/test_isolation.py`: record the count of `User` rows via a non-pytest path (or a fixture simulating "dev data"), run a representative subset of the suite, and assert pytest-django's test database is distinct from the configured dev database name (FR-032)

### Implementation for User Story 5

- [X] T066 [US5] Add `--reuse-db` as the documented default local test invocation and a documented `--create-db` variant for post-migration runs (research.md §11); record both in README/quickstart cross-reference
- [X] T067 [US5] Run the complete suite via `docker compose exec web pytest --cov-report=term-missing` and confirm: all tests pass, coverage report prints, total runtime is under 2 minutes (SC-008); address any failing test or timeout before proceeding
- [X] T068 [US5] Confirm `docker compose exec web pytest` run twice in a row produces identical dev-database row counts (FR-032, quickstart.md Scenario 5b) — manual verification recorded in commit/PR description

**Checkpoint**: All five user stories are independently functional and collectively verified — this is the full Phase 1 scope.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation against the complete quickstart guide and constitution re-check; no new functional surface.

- [X] T069 [P] Run quickstart.md Scenario 1 (full environment) end-to-end exactly as documented, including the outbound-network-blocked check (SC-011) and the stop/restart data-persistence check (SC-010)
- [X] T070 [P] Run quickstart.md Scenarios 2–5 end-to-end exactly as documented (role enforcement matrix, audit immutability at both layers, health degradation for each dependency, full test suite) and confirm every "Expected" outcome matches
- [X] T071 Review `README.md`/setup docs against FR-007 and SC-001: have a fresh reader (or a clean-environment dry run) follow only the written docs and time the path to a running, tested system (target: under 30 minutes)
- [X] T072 Final coverage report review: confirm `apps/core`, `apps/accounts`, `apps/audit`, `apps/health` all have meaningful coverage from the tests written in Phases 2–7 (FR-031)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. **BLOCKS all user stories** — contains the custom User model (must be the first migration, per research.md §2), the single RBAC mechanism, the append-only audit model, Docker Compose orchestration, and the test harness.
- **User Stories (Phase 3–7)**: All depend on Foundational phase completion.
  - **US1** (Phase 3) and **US4** (Phase 6) are tightly coupled in practice: US1's independent test queries `/health/`, which US4 builds. They are listed as separate phases per spec priority, but US4's view/urls (T062–T063) should land before US1's final verification task (T035) is exercised end-to-end. Implement in the order given below.
  - **US2** (Phase 4) depends only on Foundational (User model, HasRole, audit service) — independently testable.
  - **US3** (Phase 5) depends only on Foundational (AuditLog, record_action) — independently testable; uses US2's endpoints to generate real audit entries in its integration test (T051) but its own audit-immutability tests (T048–T050, T052–T054) need only Foundational.
  - **US5** (Phase 7) depends on Foundational's test harness; its remaining tasks are best run last since they validate the *complete* suite across all other stories.
- **Polish (Phase 8)**: Depends on all user stories being complete.

### Recommended sequential order (single developer / LLM agent)

1. Phase 1 (Setup)
2. Phase 2 (Foundational) — through T030
3. Phase 6 (US4: Health) — T058–T064, since Phase 3's own checkpoint (T035) needs a working `/health/`
4. Phase 3 (US1: Environment) — T031–T035, now verifiable end-to-end
5. Phase 4 (US2: Roles & RBAC) — T036–T047
6. Phase 5 (US3: Audit) — T048–T057, whose integration test (T051) exercises US2's endpoints
7. Phase 7 (US5: Test infra closure) — T065–T068
8. Phase 8 (Polish) — T069–T072

### Within Each User Story

- Tests MUST be written and FAIL before their corresponding implementation tasks (Principle V).
- Models/serializers before views; views before urls wiring.
- Story checkpoint validated before moving to the next story.

### Parallel Opportunities

- All `[P]`-marked Setup tasks (T003–T006) can run together.
- Within Foundational, T010/T011 (settings variants), T015/T019/T020, T021/T024/T025, T026 can run in parallel with each other where files don't overlap — but respect the strict ordering T016 → T017 → T018 (model before manager before migration) and T022 → T023 (model before migration).
- All `[P]` test tasks within a story phase (e.g., T036–T041, T048–T054, T058–T061) can be written in parallel — different test files, no shared state.
- US2 and US3's test-writing can proceed in parallel once Foundational is done, since they touch different apps' test directories, though US3's T051 needs US2's views (T043) to exist first.

---

## Parallel Example: User Story 2

```bash
# Launch all US2 tests together (different test files):
Task: "Contract/unit test in apps/accounts/tests/test_models.py — role constraint"
Task: "Unit test in apps/core/tests/test_permissions.py — HasRole matrix"
Task: "Contract test in apps/accounts/tests/test_views.py — full RBAC matrix"
Task: "Test factory single-call role builder in apps/accounts/tests/test_factories.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + its health dependency)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 6: User Story 4 (health endpoint — needed for US1's own verification)
4. Complete Phase 3: User Story 1
5. **STOP and VALIDATE**: platform runs locally, persists data, no external calls, `/health/` reports correctly
6. Deploy/demo if ready — this alone delivers "a reproducible local environment"

### Incremental Delivery

1. Setup + Foundational → foundation ready (Django project, User model, RBAC, audit, Docker Compose, test harness)
2. Health (US4) + Environment (US1) → MVP: running, persistent, health-checked local platform
3. Roles & RBAC (US2) → administrators can create accounts and enforcement is proven
4. Audit (US3) → every account/role action leaves an unalterable record
5. Test infra closure (US5) → full-suite runtime, isolation, and coverage confirmed
6. Polish → full quickstart re-run, documentation timing check

### Parallel Team Strategy

With multiple developers, after Foundational completes:
- Developer A: US4 (health) then US1 (environment docs/verification)
- Developer B: US2 (roles/RBAC/placeholders)
- Developer C: US3 (audit views/history) — can start test-writing immediately, implementation waits only on US2's views for its one cross-story integration test

---

## Notes

- `[P]` tasks touch different files with no unresolved dependency.
- `[Story]` label maps every user-story-phase task to US1–US5 for traceability.
- Tests are written first within each phase and must fail before their implementation task is done (Principle V, FR-029–034).
- The custom `User` model's first-migration ordering (T018) is the single highest-cost mistake to get wrong per research.md §2 — do not generate any other app's migration before it.
- Audit immutability (T048–T049) must be tested at **both** the ORM and database layers — the database trigger is the binding guarantee (research.md §5).
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
