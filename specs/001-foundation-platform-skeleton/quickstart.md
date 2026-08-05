# Quickstart & Validation Guide: Foundation — Platform Skeleton

**Feature**: `001-foundation-platform-skeleton` | **Date**: 2026-07-30

How to bring the platform up from a clean clone and prove each user story
actually works. This is the validation guide the acceptance criteria are checked
against — it is not an implementation guide. Model and endpoint detail lives in
[data-model.md](./data-model.md) and [contracts/](./contracts/).

**Note**: this describes the target state *after* implementation. None of it
runs until `/speckit-tasks` and `/speckit-implement` have completed.

---

## Prerequisites

- WSL Ubuntu on Windows 11 (or any Linux host)
- Docker Engine with Compose v2 (`docker compose version` reports v2 or later)
- Git

That is the complete list. No host Python is required — the application runs
Python 3.13 inside its container (research.md §1). No account, API key, or
network access to any external service is needed at runtime (SC-011).

---

## Setup — from clean clone to running platform

Target: under 30 minutes with no undocumented steps (SC-001).

```bash
git clone <repository-url> insurance-ai-platform
cd insurance-ai-platform

cp .env.example .env          # the only manual configuration step
docker compose up --build -d  # builds the image, starts web + db + redis
```

The entrypoint waits for the database, applies migrations, and starts the
server. Watch it reach a healthy state:

```bash
docker compose ps             # all three services: running, web healthy
docker compose logs -f web    # Ctrl-C once "Starting gunicorn" appears
```

Create the first System Administrator:

```bash
docker compose exec web python manage.py createsuperuser
# prompts for email, role, password — role must be system_administrator
```

**Expected**: three services running, `web` reporting healthy, and
`http://localhost:8000/health/` returning `200`.

---

## Validation scenarios

Each scenario maps to a user story and can be run independently. Automated
equivalents live in the test suite; the manual commands are here so the
behaviour can be confirmed by inspection too.

### Scenario 1 — The whole system runs locally (Story 1)

**Covers**: FR-001, FR-002, FR-003, SC-001, SC-010, SC-011

```bash
# 1a. All services reachable
docker compose ps
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health/   # → 200

# 1b. Data survives a full restart (SC-010)
docker compose exec web python manage.py shell -c \
  "from django.contrib.auth import get_user_model; print(get_user_model().objects.count())"
docker compose down          # note: NOT 'down -v' — that would remove volumes
docker compose up -d
# rerun the count above → same number
```

**Expected**: the user count is identical before and after the restart.

```bash
# 1c. No external network dependency (SC-011)
docker compose down
docker network create --internal isolated-test
# start the stack with outbound access removed, then repeat 1a
```

**Expected**: all services start and `/health/` returns `200` with no outbound
connectivity. (Images must already be pulled — image pulls are a build-time
step, not a runtime dependency.)

```bash
# 1d. Fail-fast on missing configuration (FR-005)
# Remove a required key from .env, then:
docker compose up web
```

**Expected**: startup aborts with a message naming the missing setting. Not a
partial start, not a traceback about something unrelated downstream.

---

### Scenario 2 — Roles are assigned and enforced server-side (Story 2)

**Covers**: FR-008 – FR-017, SC-002, SC-003

Sign in as the System Administrator and create one account per role:

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"<password>"}'

curl -b cookies.txt -X POST http://localhost:8000/api/users/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"adjuster@example.com","password":"<password>","role":"claims_adjuster"}'
# → 201, body echoes role, no password field
```

**2a. Invalid role is rejected (FR-010)**

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/users/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"x@example.com","password":"<password>","role":"auditor"}'
```

**Expected**: `400`, body identifies `role` as invalid, no account created.

**2b. Unauthenticated request is refused without disclosing existence (FR-012)**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/users/       # → 403
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/users/1/     # → 404
```

**Expected**: `404` on the detail route — a `403` there would confirm the
account exists. See [contracts/README.md](./contracts/README.md#existence-non-disclosure-rule-fr-012).

**2c. Wrong role is refused, target unchanged (FR-013)**

Sign in as the Claims Adjuster created above, then attempt account creation.

**Expected**: `403`, and the user count is unchanged.

**2d. Superuser does not bypass RBAC (spec edge case)**

Create an account with `is_superuser=true` but role `product_manager`, then call
`GET /api/audit/`.

**Expected**: `403`. Superuser status confers no API access.

**2e. Role change takes effect immediately (FR-016)**

As the administrator, `PATCH /api/users/{id}/` with
`{"role":"system_administrator"}` for a user who was just refused in 2c. Without
restarting anything or signing that user out, retry their refused request.

**Expected**: it now succeeds — no restart, no re-login.

---

### Scenario 3 — Audit records are written and cannot be altered (Story 3)

**Covers**: FR-018 – FR-024, SC-004, SC-005

**3a. Account creation and role change are recorded (FR-020, SC-004)**

```bash
curl -b cookies.txt \
  "http://localhost:8000/api/audit/history/accounts.User/7/"
```

**Expected**: `200` with entries in chronological order — `user.created` first,
then `user.role_changed` — each carrying actor, timestamp, outcome, and
before/after values. Response shape in
[contracts/audit.md](./contracts/audit.md).

**3b. Records cannot be modified or deleted (FR-019, SC-005)**

At the ORM layer:

```bash
docker compose exec web python manage.py shell -c \
  "from apps.audit.models import AuditLog; e = AuditLog.objects.first(); e.action='tampered'; e.save()"
```

**Expected**: raises. Then confirm the queryset paths also raise:
`AuditLog.objects.all().update(action='x')` and `AuditLog.objects.all().delete()`.

At the database layer (the binding guarantee):

```bash
docker compose exec db psql -U <user> -d <db> \
  -c "UPDATE audit_auditlog SET action='tampered' WHERE id=1;"
```

**Expected**: the trigger rejects it. Same for `DELETE`.

**3c. Audit survives actor deletion (FR-021)**

Delete a user who has audit entries, then re-read their entries.

**Expected**: entries remain readable; `actor` is null but `actor_identifier` and
`actor_role` still identify who acted.

**3d. Failed audit write blocks the action (FR-022)**

Covered by an automated test that forces the audit insert to fail during account
creation.

**Expected**: the request fails and no account is created — the action is not
committed without its audit entry.

---

### Scenario 4 — Health reflects dependency state (Story 4)

**Covers**: FR-025 – FR-028, SC-006, SC-007

```bash
# 4a. Healthy
curl -s -w '\nHTTP %{http_code} in %{time_total}s\n' http://localhost:8000/health/
```

**Expected**: `200`, `{"status":"healthy"}`, both checks `ok`, well under 5 s.

```bash
# 4b. Database down (SC-007)
docker compose stop db
curl -s -w '\nHTTP %{http_code} in %{time_total}s\n' http://localhost:8000/health/
docker compose start db
```

**Expected**: `503`, `database` reports `error`, `cache` reports `ok`, response
within 5 s (SC-006) — not a hang, not a `500`.

```bash
# 4c. Cache down
docker compose stop redis
curl -s -w '\nHTTP %{http_code} in %{time_total}s\n' http://localhost:8000/health/
docker compose start redis
```

**Expected**: `503`, `cache` reports `error`, `database` reports `ok`.

**4d. No sensitive disclosure (FR-028)**

Inspect every response body from 4a–4c.

**Expected**: only `status` and the two `checks` entries. No host names, ports,
connection strings, credentials, exception text, or version strings.

---

### Scenario 5 — The test suite runs from day one (Story 5)

**Covers**: FR-029 – FR-034, SC-008, SC-009

```bash
docker compose exec web pytest
```

**Expected**: the suite runs to completion, reports pass/fail, prints a coverage
summary (FR-031), and finishes in under 2 minutes (SC-008).

Run against the host Python and it will not reflect the shipped runtime — the
container's 3.13 interpreter is the one that governs (research.md §1).

**5a. Any role in one call (FR-030, SC-009)**

`UserFactory` exposes a per-role builder, so a test needing an Underwriter
writes one call with no other field setup. Verified by the factory's own tests.

**5b. Test isolation (FR-032)**

```bash
docker compose exec web python manage.py shell -c \
  "from django.contrib.auth import get_user_model; print(get_user_model().objects.count())"
docker compose exec web pytest
# rerun the count → unchanged
```

**Expected**: the development database is untouched — pytest-django creates and
drops a separate test database.

**5c. Required coverage (FR-033, FR-034)**

The suite includes, at minimum:

- every endpoint × all nine roles × the unauthenticated case, asserting the
  matrix in [contracts/users.md](./contracts/users.md#rbac-test-matrix-fr-033-sc-002-sc-003)
- audit records written for account creation and role change
- audit modification and deletion attempts failing at **both** the ORM and
  database layers

---

## Everyday commands

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop (keep data) | `docker compose down` |
| Stop and **erase** data | `docker compose down -v` |
| Logs | `docker compose logs -f web` |
| Run tests (default: reuses the test DB) | `docker compose exec web pytest` |
| Run tests after a migration change | `docker compose exec web pytest --create-db` |
| Tests + coverage detail | `docker compose exec web pytest --cov-report=term-missing` |
| Rebuild after dependency change | `docker compose up --build -d` |
| Django shell | `docker compose exec web python manage.py shell` |
| Make migrations | `docker compose exec web python manage.py makemigrations` |
| Apply migrations | `docker compose exec web python manage.py migrate` |

---

## Troubleshooting

**`web` never becomes healthy** — `docker compose logs web`. Most often a
missing `.env` key: startup fails deliberately and names the setting (FR-005).

**Port 8000 already in use** — another process holds it. Stop it, or change the
published port in `docker-compose.yml`.

**Migrations fail on first run** — usually a stale volume from an earlier,
incompatible schema. `docker compose down -v` then `up --build -d` rebuilds from
scratch. This **erases local data**; safe in this phase, since no business data
exists yet.

**Tests are slow** — `--reuse-db` is baked into the default `pytest`
invocation (`pyproject.toml`'s `addopts`), so the test database persists
across runs. After a migration change, run once with `pytest --create-db`
to force a rebuild. See also the [README](../../README.md#everyday-commands).

**`/health/` returns 503 right after startup** — the database may still be
accepting connections. Wait for the `start_period` in the healthcheck to elapse;
if it persists past ~30 s, check `docker compose logs db`.
