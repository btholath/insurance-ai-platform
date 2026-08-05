# Insurance AI Platform

Django 5.x + PostgreSQL 16 + Redis, running entirely in Docker Compose. This
document is everything a first-time operator needs to get a working local
environment — no source-code reading required.

## Prerequisites

- Docker Engine with Compose v2 (`docker compose version` reports v2 or later)
- Git

No host Python is required — the application runs Python 3.13 inside its own
container. No account, API key, or network access to any external service is
needed at runtime.

## Setup — from clean clone to running platform

```bash
git clone <repository-url> insurance-ai-platform
cd insurance-ai-platform

cp .env.example .env          # the only manual configuration step
docker compose up --build -d  # builds the image, starts web + db + redis
```

`.env.example`'s `SECRET_KEY` and `POSTGRES_PASSWORD` are placeholder values —
functional for local development as-is, but replace them with real generated
values before this ever runs anywhere reachable by anyone but you.

**If `.env` already exists, `cp` overwrites it silently — no prompt, no
backup.** If you've previously brought the stack up (so the `db` volume
already holds data initialized with an earlier `.env`'s credentials),
re-running `cp .env.example .env` blindly will create a mismatch between
what's in `.env` now and what Postgres was actually initialized with. Check
first:

```bash
test -f .env && echo ".env already exists — back it up before overwriting"
```

If that happens and you get authentication errors on startup, either restore
your previous `.env`, or wipe the volume and start fresh (this **erases local
data** — safe as long as you have no data you need to keep):

```bash
docker compose down -v
cp .env.example .env
docker compose up --build -d
```

The entrypoint waits for the database, applies migrations, and starts the
server. Watch it reach a healthy state:

```bash
docker compose ps             # all three services: running, web healthy
docker compose logs -f web    # Ctrl-C once "Starting gunicorn" appears
```

Create the first System Administrator account:

```bash
docker compose exec web python manage.py createsuperuser
# prompts for email, role, password — role must be system_administrator
```

Verify the platform is up:

```bash
curl -s http://localhost:8000/health/
# → {"status":"healthy","checks":{"database":{"status":"ok"},"cache":{"status":"ok"}}}
```

That's it — clone to running platform, no undocumented steps.

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
| Rebuild after a source or dependency change | `docker compose up --build -d` |
| Django shell | `docker compose exec web python manage.py shell` |
| Make migrations | `docker compose exec web python manage.py makemigrations` |
| Apply migrations | `docker compose exec web python manage.py migrate` |
| Local `psql` access | uncomment the `db` port mapping in `docker-compose.yml`, then `docker compose up -d db` |

**Rebuilds are required after any host-side source edit.** `docker-compose.yml`
does not mount the source tree into the `web` container — the image is built
from a `COPY . /app` step, so `docker compose up -d` alone will keep running
whatever code was baked into the image at the last `--build`. Running tests
or the server against a stale image will silently exercise old code.

## Troubleshooting

**`web` never becomes healthy** — check `docker compose logs web`. Most often
a missing or empty `.env` key: startup fails deliberately and names the
missing setting rather than starting partially.

**Port 8000 already in use** — another process holds it. Stop it, or change
the published port in `docker-compose.yml`.

**Migrations fail on first run** — usually a stale volume from an earlier,
incompatible schema. `docker compose down -v` then `up --build -d` rebuilds
from scratch. This **erases local data**; safe in this phase, since no
business data exists yet.

**Tests are slow** — `--reuse-db` is baked into the default `pytest`
invocation (`pyproject.toml`'s `addopts`), so the test database persists
across runs instead of being rebuilt every time. After a migration change,
run once with `pytest --create-db` to force a rebuild; see
[quickstart.md Scenario 5](specs/001-foundation-platform-skeleton/quickstart.md#scenario-5--the-test-suite-runs-from-day-one-story-5)
for the full test-suite validation walkthrough.

**`/health/` returns `503` right after startup** — the database may still be
accepting connections. Wait for the healthcheck's `start_period` to elapse;
if it persists past ~30s, check `docker compose logs db`.

## Further reading

- [`specs/001-foundation-platform-skeleton/quickstart.md`](specs/001-foundation-platform-skeleton/quickstart.md) —
  full validation scenarios for every user story (roles/RBAC, audit logging,
  health checks, test suite)
- [`specs/001-foundation-platform-skeleton/contracts/`](specs/001-foundation-platform-skeleton/contracts/) —
  exact request/response shapes and permitted roles for every endpoint
- [`specs/001-foundation-platform-skeleton/data-model.md`](specs/001-foundation-platform-skeleton/data-model.md) —
  entity definitions (`User`, `AuditLog`, `Role`)
