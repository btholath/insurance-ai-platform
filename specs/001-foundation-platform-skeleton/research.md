# Phase 0 Research: Foundation — Platform Skeleton & Role-Based Access

**Feature**: `001-foundation-platform-skeleton` | **Date**: 2026-07-30

The spec's Assumptions section already fixes the stack ("Stack is pre-decided,
not chosen here" — the constitution's Technology Stack Constraints are binding).
So this document does not re-litigate framework selection. It resolves the open
decisions that the spec deliberately left to the plan, and records best-practice
choices for each mandated technology.

No `NEEDS CLARIFICATION` markers remain in the plan's Technical Context.

---

## 1. Python 3.13 requirement vs. host Python 3.12.3

**Decision**: Pin Python 3.13 in the application container image
(`python:3.13-slim-bookworm`). Do not require or upgrade the host interpreter.

**Rationale**: The constitution mandates Python 3.13 for all spec-driven work.
The WSL host currently has 3.12.3. Because every application process — server,
migrations, and the test suite — runs inside the container, the container's
interpreter is the one that governs. The host Python is used only to invoke
`docker compose`, which is version-agnostic. This satisfies the constraint
without asking the operator to rebuild their system interpreter, which would
also contradict SC-001's "under 30 minutes from a clean machine".

**Consequence for testing**: `pytest` is documented as run *through* the
container (`docker compose exec web pytest`), not on the host. A host-side
`pytest` invocation against a 3.12 interpreter would not be testing the runtime
that ships.

**Alternatives considered**:
- *Install 3.13 on the host via pyenv/deadsnakes*: rejected — adds a manual
  prerequisite step to SC-001's 30-minute path, and creates two interpreters
  that can drift.
- *Relax to 3.12*: rejected — requires a constitution amendment for no benefit,
  since the container solves it.

---

## 2. Custom User model: `AbstractBaseUser` vs. `AbstractUser`

**Decision**: `AbstractBaseUser` + `PermissionsMixin`, with email as
`USERNAME_FIELD` and a required `role` field.

**Rationale**: `AbstractUser` ships a `username` field the spec never asks for
and a `groups`/`user_permissions` model whose presence invites exactly the
mistake Principle III forbids — access decisions drifting into Django's
permission framework instead of the single `HasRole` mechanism FR-015 requires.
`AbstractBaseUser` gives full control of the field set. `PermissionsMixin` is
retained solely so `django.contrib.admin` works (it needs `is_staff` and
`has_perm`); admin access is not the RBAC surface and `HasRole` never consults
Django permissions.

**Critical timing note**: The custom user model *must* be in place in the very
first migration. Django's `AUTH_USER_MODEL` cannot be swapped after any
migration referencing it has been applied without a destructive reset. This is
the single highest-cost ordering mistake available in this phase, and it is why
Story 2 (identity) is P1 alongside Story 1.

**Alternatives considered**:
- *`AbstractUser` + role field*: rejected — carries `username` (unused) and
  normalizes toward Django groups for authorization.
- *Separate `Profile` model holding the role*: rejected — makes every permission
  check a join and every role read a potential `Profile.DoesNotExist`, and
  FR-014's deny-by-default becomes an exception path rather than a value check.

---

## 3. Role representation: enum vs. `Role` table

**Decision**: `django.db.models.TextChoices` enum on `User.role`, with a
`CharField(choices=Role.choices)` plus a database `CheckConstraint` restricting
the column to the nine values.

**Rationale**: The spec's Assumptions state the nine roles are "a closed set…
Adding a tenth role is a spec change, not a runtime configuration action." A
`Role` database table models the opposite — runtime-extensible roles — and would
invite a tenth row to be inserted without a spec. The enum makes the closed set
structural, gives compile-time-ish safety in code (`Role.FRAUD_ANALYST`), and
the `CheckConstraint` satisfies FR-010 even against raw SQL or a bulk update
that bypasses Django validation.

Note the BRD §10 lists `Role` and `Permission` as core tables. That is the
long-term schema; FR-009/FR-010 as specified describe a fixed nine-value
attribute, and the spec's "Fine-grained per-record or per-field permissions" are
explicitly out of scope. Promoting roles to tables is a later spec's decision
when per-permission granularity actually arrives.

**Alternatives considered**:
- *`Role` + `Permission` tables now*: rejected — builds runtime extensibility the
  spec forbids, and a permission-assignment UI that is out of scope.
- *Django `Group` per role*: rejected — same Principle III drift risk as above;
  group membership is many-to-many, contradicting FR-009's "exactly one role".

---

## 4. RBAC enforcement mechanism

**Decision**: A single DRF permission class in `apps/core/permissions.py`:

```
HasRole(*roles)  →  used as permission_classes = [IsAuthenticated, HasRole(Role.SYSTEM_ADMINISTRATOR)]
```

implemented via a class factory so the allowed roles are declared per view.
Enforcement happens in `has_permission()`, evaluated on every request before the
view body runs.

**Rationale**: FR-015 requires *one* reusable mechanism so later modules do not
each invent a check. DRF's permission layer is the correct seam: it runs at the
view/API layer (Principle III's explicit requirement), it applies uniformly to
every HTTP method, and it cannot be bypassed by a hand-constructed request the
way a template `{% if %}` can.

Four behaviours are decided here because they are the ones most often gotten
wrong:

1. **Superuser does not bypass.** `HasRole` checks `user.role` only. The spec's
   edge case is explicit: "The System Administrator role MUST NOT be silently
   treated as an unrestricted bypass." No `if user.is_superuser: return True`.
2. **Deny by default (FR-014).** A user whose `role` is null, blank, or an
   unrecognised string fails every `HasRole` check. The check is membership in
   the view's allowed set, never a negative check.
3. **Existence non-disclosure (FR-012).** Unauthenticated requests to
   object-scoped routes return **404**, not 403 — a 403 on a detail route
   confirms the record exists. Collection routes return 403. Implemented by
   raising `NotFound` from the permission layer on detail views for anonymous
   users.
4. **Immediate effect (FR-016).** Role is read from `request.user.role` on each
   request, and Django's session auth re-fetches the user row per request. No
   role caching in the session, no role claim baked into a token. A role change
   therefore applies to the very next request without restart or re-login.

**Alternatives considered**:
- *Django `@permission_required` decorators*: rejected — ties authorization to
  the `auth.Permission` table, which contradicts §3's decision.
- *Middleware doing global path→role mapping*: rejected — the route table
  becomes a second source of truth that drifts from the views, and it silently
  fails open for any route nobody remembered to list.
- *Per-view manual `if request.user.role != ...` checks*: rejected — exactly the
  "each module invents its own check" outcome FR-015 exists to prevent.

---

## 5. Audit log immutability

**Decision**: Enforce append-only at two independent layers.

- **ORM layer**: `AuditLog.save()` raises if `self.pk` is already set (i.e. any
  update); `AuditLog.delete()` and the queryset's `delete()`/`update()` raise.
- **Database layer**: a PostgreSQL `BEFORE UPDATE OR DELETE` trigger on the
  table that raises an exception, installed via a `migrations.RunSQL` operation.

**Rationale**: FR-019 says "No part of the platform may modify or delete an
existing audit record." The ORM guard catches ordinary application code and
gives a clear error. It does **not** catch raw SQL, `bulk_update`, a future
Django admin action, or a psql session — and Principle II calls audit records
append-only without qualification. The trigger is the actual guarantee; the ORM
guard is the fast, legible failure. SC-005 requires 100% of modification and
deletion attempts to fail, verified by tests, so both layers get direct tests.

**Alternatives considered**:
- *ORM guard only*: rejected — a `QuerySet.update()` bypasses `save()` entirely,
  so the guarantee would be false for the most likely accidental mutation.
- *Postgres role with revoked UPDATE/DELETE grants*: rejected as the sole
  mechanism — it requires the app to connect as a restricted role, which
  conflicts with the same connection running migrations. The trigger achieves
  the same protection without a second connection identity.
- *Append-only via an external log stream*: rejected — introduces infrastructure
  beyond the spec's scope and complicates FR-024's chronological retrieval.

---

## 6. Audit write atomicity (FR-022)

**Decision**: Write the audit record inside the same
`transaction.atomic()` block as the action it describes, through one service
function `apps.audit.services.record_action(...)`. No `on_commit` hook, no
async dispatch, no `try/except` that swallows the audit failure.

**Rationale**: FR-022 states that when an audit record cannot be written, the
action MUST NOT be silently committed. Same-transaction writing makes this
automatic: if the audit `INSERT` fails, the transaction rolls back and the
action never happened. An `on_commit` callback would fire *after* the action is
durable — precisely the failure mode the requirement forbids. Routing every
write through one service function also means later modules satisfy FR-023 by
calling it rather than re-deriving the pattern.

**Trade-off accepted**: audit writes are on the request's critical path and a
Postgres failure fails the whole action. That is the correct behaviour here —
the spec ranks the completeness of the audit record above availability of the
action.

**Alternatives considered**:
- *Django signals (`post_save`) for audit*: rejected — signals cannot see the
  acting user without thread-local request state, and they fire for fixtures,
  migrations, and test factories, producing audit noise that isn't a real action.
  Explicit `record_action()` calls at the point of the business action are both
  visible in code review and correct about the actor.
- *Celery task for the audit write*: rejected — violates FR-022 (async means the
  action commits before the log exists) and adds infrastructure out of scope.

---

## 7. Audit actor survives user deletion (FR-021)

**Decision**: `actor = FK(User, null=True, on_delete=models.SET_NULL)` plus a
denormalized `actor_identifier` CharField snapshot (the actor's email at the
time of the action) and `actor_role` snapshot, both written at record time and
never updated.

**Rationale**: `SET_NULL` alone satisfies "the record remains readable" but not
"MUST still identify who acted" — a null FK identifies nobody. The snapshot
columns preserve identity independently of the user row. Snapshotting the role
too is worth the column: an audit reader needs to know what role the actor held
*when they acted*, not what role they hold now (a role changed after the fact
would otherwise silently rewrite the meaning of the history).

`PROTECT` was considered and rejected: it makes user deletion impossible once
any action is logged, which is a policy the spec does not ask for.

---

## 8. Health check probes and bounded time (FR-027, SC-006)

**Decision**: An unauthenticated DRF `APIView` that runs two probes with
explicit short timeouts and returns HTTP **200** when both pass, HTTP **503**
when either fails, with a JSON body naming each dependency's status.

- **Postgres probe**: `SELECT 1` on a connection opened with
  `connect_timeout=2` (set in the health check's own connection parameters, not
  the global pool), wrapped so any `OperationalError` becomes an unhealthy
  result rather than a 500.
- **Redis probe**: `PING` with `socket_connect_timeout=2` and
  `socket_timeout=2`.

Total worst case ≈ 4 s, inside SC-006's 5 s bound.

**Rationale**: FR-027 requires a definite result within bounded time *and* a
signal "an automated supervisor can detect without parsing prose". The HTTP
status code is that signal — `docker compose` healthchecks and every monitoring
tool key off it natively; the JSON body carries the per-dependency detail
FR-026 requires. Without explicit timeouts, a hung TCP connection to a
partitioned database blocks on the OS default (often 2+ minutes), which is the
"health queried during startup MUST NOT hang" edge case.

**Disclosure discipline (FR-028, SC-007)**: the response body contains only
`{"status": ..., "checks": {"database": {"status": ...}, "cache": {...}}}`.
No host names, ports, DSNs, driver versions, Django/Python versions, or
exception messages. Exception detail is logged server-side and never serialized.
`DEBUG` must be false in any configuration where the endpoint is reachable by an
untrusted caller, since Django's debug pages leak settings.

**Alternatives considered**:
- *`django-health-check` package*: rejected — its default output includes
  backend class names and error strings, which is a direct FR-028 conflict, and
  the two probes needed here are a few lines each.
- *Always return 200 with a status field*: rejected — forces supervisors to
  parse the body, contrary to FR-027.
- *Separate liveness and readiness endpoints*: rejected as scope beyond FR-025's
  single endpoint; the split matters for Kubernetes rollouts, which are out of
  scope.

---

## 9. Configuration and fail-fast startup (FR-004, FR-005)

**Decision**: `django-environ` reading a `.env` file, with an explicit
`REQUIRED_SETTINGS` list validated at the bottom of `config/settings/base.py`.
Any missing name raises `ImproperlyConfigured` naming that setting, before the
application finishes importing settings. `.env.example` lists every required key
with placeholder values and is committed; `.env` is gitignored.

**Rationale**: FR-005 requires refusal to start "with a message naming the
missing item". `env("KEY")` without a default already raises, but raises one
name at a time and only when that setting is first read — which for a rarely
read setting can be at request time, not startup. An explicit up-front loop over
the required list fails at import, names all missing keys at once, and is the
thing a new operator following SC-001 actually reads.

**Alternatives considered**:
- *Defaults for everything*: rejected — directly contradicts FR-005, and a
  default `SECRET_KEY` is a security defect that survives into later phases.
- *`python-decouple` / plain `os.environ`*: rejected — no meaningful difference;
  `django-environ` additionally parses `DATABASE_URL` and typed values, which
  reduces hand-written casting.

---

## 10. Docker Compose service topology and data persistence

**Decision**: Three services — `web`, `db`, `redis` — on one bridge network,
with named volumes `postgres_data` and `redis_data`. `web` declares
`depends_on` with `condition: service_healthy` for both dependencies. `db` and
`redis` each declare their own container healthcheck (`pg_isready`,
`redis-cli ping`).

**Rationale**: FR-003 and SC-010 require data to survive a stop/restart in 100%
of attempts. Named volumes do this; bind mounts to the WSL filesystem would also
persist but bring permission and I/O-performance problems on WSL2 for Postgres
specifically. `condition: service_healthy` is what makes Story 1's "without
manual intervention" true — plain `depends_on` only waits for container start,
not readiness, so the first `manage.py migrate` races the database.

The entrypoint additionally waits for the DB and runs `migrate` before starting
the server, so a fresh clone reaches a working system in one command
(SC-001).

**Port exposure**: `web` publishes 8000. `db` and `redis` ports are **not**
published to the host by default — they are reachable on the compose network,
and publishing them widens the surface with no benefit for the documented flow.
A commented-out mapping is left in the file for operators who want a local psql.

**Alternatives considered**:
- *Bind-mount `./postgres_data`*: rejected — WSL2 cross-filesystem I/O and
  permission issues, and it drops a large gitignored directory into the repo.
- *Single container running all three*: rejected — contradicts FR-001's separate
  services and makes the per-dependency health reporting of FR-026 meaningless.

---

## 11. Test infrastructure

**Decision**: pytest + pytest-django + pytest-cov + factory-boy, configured in
`pyproject.toml`. `UserFactory` in `apps/accounts/factories.py` exposes a
per-role trait so any of the nine roles is one call (`UserFactory(role=...)`,
plus named shortcuts). Test database is the pytest-django managed
`test_<dbname>`, created and dropped per run.

**Rationale**: Constitution mandates pytest + Factory Boy. FR-030 requires a
single-call builder for any role — a `role` parameter plus `Params`/traits gives
that without nine near-duplicate factory classes. FR-032's isolation is met by
pytest-django's separate test database (never the dev volume) combined with
per-test transaction rollback (`django_db` marker), so no test can leave state
behind. FR-031's coverage comes from `--cov=apps --cov=config` with a terminal
report.

Two settings matter for SC-008's 2-minute budget: `--reuse-db` as the documented
default for local iteration (with a documented `--create-db` when migrations
change), and `PASSWORD_HASHERS = ["...MD5PasswordHasher"]` in `settings/test.py`
— password hashing dominates runtime in any suite that creates users, which this
one does heavily.

**Alternatives considered**:
- *Django's built-in `manage.py test`*: rejected — constitution mandates pytest.
- *`model_bakery` instead of Factory Boy*: rejected — constitution names Factory
  Boy.
- *One factory class per role*: rejected — nine classes to maintain against one
  changing model, for no expressiveness gain over traits.

---

## 12. Deferred stack components

Two items in the constitution's Technology Stack Constraints are intentionally
not installed in this phase.

### Celery

**Decision**: Not installed. Redis is stood up as infrastructure; no worker
service, no `celery.py`, no tasks.

**Rationale**: The spec's Out of Scope section explicitly excludes background
job processing and scheduled work, and states Redis "is stood up here as
required infrastructure, but no queued or asynchronous work is defined in this
phase." Adding an idle worker container would be untested, unexercised surface
that nonetheless must start correctly for Story 1 to pass. The first module that
queues work adds it, at which point the broker is already running.

This is a deferral, not a constitution deviation — Principle-level requirements
are unaffected, and the stack constraint governs *what* is used when background
jobs exist, which they do not yet.

### pgvector

**Decision**: Not installed; `postgres:16-alpine` used rather than a
pgvector-bundled image.

**Rationale**: Vector search and embedding storage are explicitly out of scope
(spec Out of Scope), and no model in `data-model.md` has an embedding field.
Installing the extension now means carrying an untested dependency and a
migration nobody can validate against real usage. When Module 7/8 needs it, the
change is a base-image swap plus a `CREATE EXTENSION` migration — additive, with
no rework of anything built here.

**Alternative considered**: *use `pgvector/pgvector:pg16` now to avoid a future
image swap.* Reasonable, and cheap. Rejected on the narrower ground that this
phase should install nothing it cannot test; the future swap is a one-line
change with no data migration, since no table would have used the type.

---

## Summary of decisions

| # | Area | Decision |
|---|---|---|
| 1 | Python 3.13 | Containerized interpreter; host stays 3.12 |
| 2 | User model | `AbstractBaseUser` + `PermissionsMixin`, email login, first migration |
| 3 | Roles | `TextChoices` enum + DB `CheckConstraint`, no Role table |
| 4 | RBAC | Single `HasRole` DRF permission class; no superuser bypass; deny-by-default; 404 for anonymous on detail routes; per-request role read |
| 5 | Audit immutability | ORM guard + Postgres `BEFORE UPDATE OR DELETE` trigger |
| 6 | Audit atomicity | Same-transaction write via `record_action()`; no signals, no async |
| 7 | Actor retention | `SET_NULL` FK + snapshot of actor identifier and role |
| 8 | Health check | Unauthenticated view, 2 s timeouts per probe, 200/503, no detail disclosure |
| 9 | Config | `django-environ` + explicit required-settings check at import; `.env.example` committed |
| 10 | Compose | `web`/`db`/`redis`, named volumes, healthcheck-gated `depends_on` |
| 11 | Tests | pytest-django + Factory Boy traits + coverage; isolated test DB; fast hasher |
| 12 | Deferred | Celery and pgvector not installed this phase, with rationale |
