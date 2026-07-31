# Implementation Plan: Phase 1 Foundation — Platform Skeleton & Role-Based Access

**Branch**: `001-foundation-platform-skeleton` | **Date**: 2026-07-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-foundation-platform-skeleton/spec.md`

## Summary

Stand up the Django 5.x + PostgreSQL 16 + Redis local environment that every
later module builds on, and make the platform's two non-negotiable guarantees —
server-side RBAC (Principle III) and append-only audit logging (Principle II) —
structural from day one.

Technical approach: a single Django project (`config/`) with business modules
under `apps/`, all services orchestrated by Docker Compose. Identity is a custom
`AbstractBaseUser` subclass in `apps/accounts` carrying exactly one role from a
nine-value `TextChoices` enum. RBAC is enforced through one reusable DRF
permission class (`HasRole`) applied at the view layer, never in templates.
Audit logging is a single append-only `AuditLog` model in `apps/audit`, written
inside the same database transaction as the action it records, with mutation and
deletion blocked at both the ORM layer and by a PostgreSQL trigger. Health is an
unauthenticated DRF endpoint that probes Postgres and Redis with bounded
timeouts and returns HTTP 503 on failure. Tests run under pytest + pytest-django
+ Factory Boy with coverage, against an isolated test database.

## Technical Context

**Language/Version**: Python 3.13 (containerized; host WSL Ubuntu has 3.12.3 —
all application execution happens inside the container, so the host version is
not a constraint)

**Primary Dependencies**: Django 5.1.x, Django REST Framework 3.15.x,
psycopg[binary] 3.x, redis-py 5.x, django-environ (config loading + fail-fast on
missing settings), gunicorn (container entrypoint)

**Storage**: PostgreSQL 16 (Docker image `postgres:16-alpine`, named volume for
persistence). Redis 7 (`redis:7-alpine`, appendonly persistence). `pgvector` is
**not** installed in this phase — no embeddings exist yet; deferred to the module
that first needs it.

**Testing**: pytest 8.x + pytest-django + pytest-cov + factory-boy 3.x. Test DB
is created and destroyed per run by pytest-django, separate from the dev volume.

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose v2 orchestration.
No production/cloud deployment in scope.

**Project Type**: Web service (Django backend + DRF API). No frontend in this
phase — the BRD's `frontend/` directory is not created, since nothing populates
it until a later phase.

**Performance Goals**: Health endpoint returns a definite status within 5 s under
all conditions (SC-006). Full test suite completes in under 2 minutes (SC-008).
No throughput or latency targets — this phase carries no production data (spec
Assumptions: "Performance targets deferred").

**Constraints**: Zero required outbound calls to external services at runtime
(SC-011, Principle I). Startup fails loudly on missing required configuration
(FR-005). All secrets supplied via environment, never committed (FR-004).

**Scale/Scope**: 4 Django apps with substance (`accounts`, `audit`, `core`,
`health`) plus 3 structural placeholders (`customers`, `policies`, `claims`);
2 persisted models (`User`, `AuditLog`); 9 roles; ~6 endpoints.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | How this plan satisfies it | Gate |
|---|---|---|---|
| **I. Local-First, No Cloud Dependencies** | Yes | All services (Django, Postgres, Redis) run in local containers. No SDK, API client, or network call to any hosted service is introduced. Verified by SC-011 (run with outbound access blocked). Base images are pulled once at build time, which is not a runtime dependency. | PASS |
| **II. Auditability by Default** | Yes | `apps/audit.AuditLog` exists from the first migration, is written for user-account creation and role change (FR-020), and is append-only enforced twice: ORM-level (`save()` rejects updates, `delete()` raises) and DB-level (PostgreSQL `BEFORE UPDATE OR DELETE` trigger). Audit writes share the action's transaction, so a failed audit write rolls back the action (FR-022). Actor FK uses `ON DELETE SET NULL` with a denormalized `actor_identifier` snapshot so records survive user deletion (FR-021). Schema is generic (`target_type`/`target_id`/`before`/`after` JSON) so later modules reuse it (FR-023). | PASS |
| **III. RBAC (NON-NEGOTIABLE)** | Yes | Enforcement lives in one DRF permission class, `apps/core/permissions.py::HasRole`, applied at the view layer on every non-public endpoint. No template-only restriction anywhere. Unauthenticated callers get 404 on restricted object routes (not 403) so existence is not disclosed (FR-012). Role with no valid value is deny-by-default (FR-014). `is_superuser` does **not** bypass `HasRole` (spec edge case: administrator ≠ unrestricted). Role is read from the DB per request, so changes take effect immediately (FR-016). Placeholder role-restricted endpoints in `customers`/`policies`/`claims` exercise the mechanism where later modules will use it. | PASS |
| **IV. Explainable AI Outputs** | No | This feature introduces no AI/LLM functionality of any kind (spec Out of Scope). Principle IV has no surface to apply to. Not an exception — a vacuous condition. | N/A |
| **V. Test-First for Business Rules (NON-NEGOTIABLE)** | Yes | pytest + Factory Boy + coverage configured before any feature code (FR-029/030/031). This phase contains no scoring or business-rule logic, so the TDD-ordering mandate has no scoring surface; however RBAC decisions and audit-immutability are treated as business rules — their tests are written before the code they cover. Coverage is measured and reported (FR-031). | PASS |
| **VI. Disposable Prototyping Stays Disposable** | Yes | Nothing from the Phase 0 Streamlit spike is imported, refactored, referenced, or scaffolded here. The spike is not a dependency of any artifact in this plan. | PASS |

**Technology Stack Constraints compliance**: Python 3.13 ✓ (in container),
Django 5.x + DRF ✓, PostgreSQL 16+ ✓, Redis ✓, pytest + Factory Boy with
coverage ✓, WSL Ubuntu + Docker Compose ✓.

Two stack items are named in the constitution but deliberately **not installed**
in this phase, both justified in [research.md](./research.md):

- **Celery** — the constitution lists it as the background-job stack, but the
  spec explicitly places background/scheduled work out of scope. Redis is stood
  up now as required infrastructure; Celery is added by the first module that
  queues work. Not a deviation: nothing here needs a job runner, and an unused
  worker container would be untested surface area.
- **pgvector** — required by the constitution for embeddings/vector search;
  no embeddings exist until Module 7/8. Adding the extension now would install
  a dependency this phase cannot test against real usage. The Postgres image
  choice does not preclude it later.

Neither is a Constitution Exception in the sense of violating a Core Principle
(I–VI) — no principle is weakened or bypassed. However, both deviate from the
**Technology Stack Constraints** section's binding list ("Background Jobs:
Celery"; "PostgreSQL 16+ with the `pgvector` extension"), and the constitution's
Governance section requires any such deviation to be recorded, not silently
deferred. Recording it here per that requirement:

**Constitution Exceptions**

| Stack item | Constitution requirement | Exception | Rationale | Reconsider when |
|---|---|---|---|---|
| Celery | Technology Stack Constraints: "Background Jobs: Celery" | Not installed this phase | Spec's Out of Scope section explicitly excludes background/scheduled work; no code in this phase queues anything. Redis (the broker Celery would use) is already stood up as required infrastructure, so adding Celery now would mean an idle, untested worker container. | The first module whose spec requires queued/async work (broker is already running). |
| pgvector | Technology Stack Constraints: "PostgreSQL 16+ with the `pgvector` extension for embeddings/vector search" | Not installed this phase; `postgres:16-alpine` used instead of a pgvector-bundled image | No embedding or vector-search functionality exists in this spec (Out of Scope: "Vector search and embedding storage"). Installing the extension with nothing to test it against is untested surface area. | Module 7/8 (Prompt Library / LLM Services), whose spec first introduces embeddings — a base-image swap plus one additive `CREATE EXTENSION` migration, no rework of anything built here. |

Both exceptions are deferrals of stack *components* to the phase whose spec
first exercises them, not a rejection of the constraint — no Core Principle
(I–VI) is diluted, reinterpreted, or bypassed by either.

**Initial gate result: PASS.** No Core Principle violations. Two documented
Technology Stack Constraint exceptions above. Complexity Tracking table not
required (that table is for design/architectural complexity trade-offs, not
stack-constraint exceptions, which are recorded here instead).

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation-platform-skeleton/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # Feature specification (/speckit-specify output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── README.md
│   ├── health.md
│   ├── users.md
│   └── audit.md
├── checklists/
│   └── requirements.md  # (/speckit-checklist output, already present)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
config/                          # Django project (settings, root urls, wsgi/asgi)
├── __init__.py
├── settings/
│   ├── __init__.py
│   ├── base.py                  # shared settings; fail-fast required-env checks
│   ├── dev.py                   # local development
│   └── test.py                  # pytest settings (isolated DB, fast hasher)
├── urls.py                      # root URLconf; mounts /health/ and /api/
├── wsgi.py
└── asgi.py

apps/
├── __init__.py
├── core/                        # cross-cutting primitives reused by every module
│   ├── permissions.py           # HasRole — the single RBAC mechanism (FR-015)
│   ├── models.py                # TimeStampedModel base
│   └── tests/
├── accounts/                    # identity: custom User + Role enum + admin API
│   ├── models.py                # User (AbstractBaseUser), Role (TextChoices)
│   ├── managers.py              # UserManager
│   ├── serializers.py
│   ├── views.py                 # user create / role change (System Admin only)
│   ├── urls.py
│   ├── admin.py
│   ├── factories.py             # UserFactory + per-role traits (FR-030)
│   ├── migrations/
│   └── tests/
├── audit/                       # append-only audit log
│   ├── models.py                # AuditLog (immutable)
│   ├── services.py              # record_action() — the single write path
│   ├── serializers.py
│   ├── views.py                 # read-only history (Compliance Officer)
│   ├── urls.py
│   ├── factories.py
│   ├── migrations/              # incl. RunSQL immutability trigger
│   └── tests/
├── health/                      # unauthenticated dependency health probe
│   ├── checks.py                # bounded-timeout Postgres + Redis probes
│   ├── views.py
│   ├── urls.py
│   └── tests/
├── customers/                   # structural placeholder (Phase 2)
├── policies/                    # structural placeholder (Phase 2)
└── claims/                      # structural placeholder (Phase 2)

docker/
└── django/
    └── Dockerfile               # Python 3.13 slim image for the app service

tests/                           # cross-app integration tests
├── conftest.py                  # shared fixtures (api_client, user_in_role)
└── integration/

scripts/
└── entrypoint.sh                # wait-for-db, migrate, run server

docker-compose.yml               # web + db + redis services, named volumes
.env.example                     # every required setting, no real secrets (FR-004)
pyproject.toml                   # deps, pytest/coverage config
manage.py
```

**Structure Decision**: Single Django project rooted at the repository root,
with business modules under `apps/` — matching the BRD §9 suggested layout and
FR-006. The BRD's `backend/`/`frontend/` split is **not** adopted: there is no
frontend in this or any planned near-term phase (the platform is server-rendered
Django + DRF), and nesting the only backend inside `backend/` adds a path level
with nothing to distinguish it from. `apps/` sits at the root as the BRD shows.

The three placeholder apps (`customers`, `policies`, `claims`) are created now
with no business models, carrying only one deliberately role-restricted endpoint
each, per the spec's "Demonstration surface for access control" assumption. The
BRD's remaining apps (`fraud`, `risk`, `behavior`, `crm`, `reports`, `analytics`,
`llm`, `prompts`, `agents`) are **not** created — FR-006 names only customers,
policies, and claims, and empty unused packages are noise, not structure.

`apps/core` and `apps/audit` are additions beyond the BRD's list. `core` exists
because FR-015 requires a *single* reusable RBAC mechanism, which must live
somewhere no business module owns. `audit` exists because Principle II makes the
audit log first-class; the BRD scopes it under Module 12 (Administration), but
building it inside a not-yet-specified admin module would couple every later
module's audit writes to a module that doesn't exist yet.

## Complexity Tracking

> Not required — Constitution Check passed with no violations.

## Post-Design Constitution Re-Check

*Performed after Phase 1 artifacts (data-model.md, contracts/, quickstart.md)
were generated.*

The design introduced no new dependencies, no external service calls, and no
additional persisted models beyond `User` and `AuditLog`. Re-evaluating each
gate against the concrete design:

- **I (Local-First)**: Final dependency set is Django, DRF, psycopg, redis-py,
  django-environ, gunicorn, pytest stack. None performs a network call to a
  hosted service. **PASS**
- **II (Auditability)**: `data-model.md` specifies `AuditLog` with actor,
  action, target type/id, timestamp, outcome, and before/after JSON; immutability
  is enforced at two layers; `contracts/audit.md` defines chronological retrieval
  restricted to Compliance Officer and System Administrator. Every audit FR maps
  to a concrete field or constraint. **PASS**
- **III (RBAC)**: Every endpoint in `contracts/` declares its permitted roles and
  its unauthenticated behaviour explicitly; only `/health/` is public, and it is
  documented as disclosing nothing sensitive. `HasRole` is the sole enforcement
  point. **PASS**
- **IV (Explainable AI)**: Still no AI surface in the design. **N/A**
- **V (Test-First)**: `quickstart.md` defines the runnable validation scenarios
  that prove each user story, all executable via the single `pytest` command.
  Factory traits cover all nine roles. **PASS**
- **VI (Disposable Prototyping)**: No spike artifact appears in any Phase 1
  output. **PASS**

**Post-design gate result: PASS.** No violations introduced by the design; no
Constitution Exceptions to record.
