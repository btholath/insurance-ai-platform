# Implementation Plan: Automatic Risk Recompute

**Branch**: `006-automatic-risk-recompute` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-automatic-risk-recompute/spec.md`

## Summary

Close the trust gap Phase 3a deliberately left open: a risk assessment that
becomes stale is now visible (`is_stale: true`) but stays stale until a
human remembers to recompute it. This phase makes that recompute automatic
— a `post_save` signal on `Customer`, `Policy`, and `Claim` enqueues a
Celery task that calls the same `engine.score_customer()` /
`engine.persist()` pair every existing recompute path (manual API route,
`computerisk` batch command) already uses. No new scoring logic, no new
persistence logic, no new model. This is the platform's first use of
Celery — Redis has been provisioned and idle since Phase 1's Foundational
plan explicitly deferred it "to the first module whose spec requires
queued/async work."

Five decisions carry the design, each recorded in `research.md`:

1. **`post_save` signals, not explicit call sites.** This is a deliberate,
   named departure from `apps/audit/services.py`'s "no signals" stance and
   from Phase 3a's own T094 test asserting no signal handler exists in the
   codebase. Both were correct for their scope — Phase 3a is explicitly the
   phase where automatic recomputation does not exist. This is the phase
   that introduces it, and FR-004's requirement that the trigger be *broad*
   (any save on any of three models, present and future call sites alike)
   is only achievable at the model layer, not by auditing every view and
   management command by hand (§1).

2. **The task enqueues via `transaction.on_commit()`, never a bare
   `.delay()` inside the signal receiver.** A save that later rolls back
   inside a larger transaction must never enqueue a recompute for data that
   was never actually persisted. This is the one place this feature uses
   `on_commit` — and it is used for exactly the opposite reason
   `apps/audit/services.py` forbids it for the audit write (that write must
   share the triggering transaction so a failure rolls both back together;
   this enqueue must NOT share it, so a slow or failing recompute can never
   fail the write that triggered it) (§1, FR-018).

3. **One task, delegating entirely to existing code.**
   `recompute_customer_risk(customer_id)` re-fetches the customer (so it
   always acts on current data, never a stale snapshot from enqueue time),
   no-ops if no `RiskAssessment` exists yet (FR-005 — this is the *only*
   new business-rule branch this feature adds), and otherwise calls
   `engine.score_customer()` + `engine.persist(actor=None)` — the identical
   two calls the Phase 3a recompute route and `computerisk` already make.
   `persist()`'s existing `select_for_update()` already gives FR-013's
   "exactly one current assessment" guarantee for free (§2).

4. **Retry/backoff via Celery's own `autoretry_for`/`retry_backoff`
   machinery, not hand-rolled retry logic; exhaustion recorded through the
   platform's existing `record_action()` audit path, not a new model or
   external alert channel.** `outcome="refused"`, `action="risk.recompute_failed"`
   — one new *action value*, zero new tables (§3). This is the concrete
   answer to "what does 'alert' mean in a local-first, no-cloud-dependency
   project": a discoverable, queryable audit row.

5. **A new `celery-worker` docker-compose service, reusing the `web`
   image, broker = the already-required `REDIS_URL`.** No new Dockerfile,
   no new env var, no Celery Beat (nothing in this spec is scheduled —
   everything is signal-triggered) (§4).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15, psycopg
3.2 (all unchanged from Phase 3a) **+ Celery 5.x (new — this feature's
entire reason to introduce a new dependency)**. `redis` (the Python client
library) is already a dependency since Phase 1; Celery uses it as its
broker transport, no separate broker client needed.

**Storage**: PostgreSQL 16 — no new tables, no new migration (see
`data-model.md`: this feature's only database-visible effect is more rows
in the existing `risk_riskassessment`/`risk_riskfactor`/`audit_auditlog`
tables, via existing write paths). Redis — now used as a real message
broker for the first time, not just infrastructure sitting idle.

**Testing**: pytest 8 + pytest-django + Factory Boy, `--cov` per Principle
V, unchanged. New: `CELERY_TASK_ALWAYS_EAGER` for happy-path/idempotency
tests, real (non-eager) `task.apply()` for retry/backoff/exhaustion tests —
per the user description's explicit instruction that retry behavior be
tested, not just the happy path (research.md §5).

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose — now four
services (`web`, `db`, `redis`, `celery-worker`) instead of three.

**Project Type**: Django web service, API-only, now with one background
worker process.

**Performance Goals**: an automatic recompute completes within seconds to
low tens of seconds of the triggering save under normal load (SC-001) — not
real-time, since this is deliberately an eventually-consistent background
process, not a synchronous part of the request. A full `loaddataset` re-run
against the seeded 3,000-customer population enqueues a proportional
(~3,000) number of tasks and the book remains exactly correct once they
drain (SC-006) — throughput of that drain is not itself a performance goal
this spec sets a target for (FR-017 explicitly declines to require
coalescing/efficiency).

**Constraints**: Local-first (Principle I) — Celery + Redis are both local
containers, no cloud queue service. Server-side RBAC unaffected (Principle
III) — this feature adds no new role-checked surface; the existing
`RiskAssessmentViewSet` role checks are untouched (FR-015). Every automatic
recompute — success or permanent failure — audited via the existing
mechanism (Principle II, FR-014). A recompute must never fail, delay, or
roll back the triggering Customer/Policy/Claim write (FR-018).

**Scale/Scope**: 3 signal receivers (Customer, Policy, Claim
`post_save`), 1 Celery task, 1 new docker-compose service, 0 new database
tables, 1 new `AuditLog` action value (`risk.recompute_failed`).

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this feature satisfies it |
|---|---|---|
| **I. Local-First** | PASS | Celery and Redis are both named in the constitution's own Technology Stack Constraints — this feature activates already-mandated, already-locally-provisioned infrastructure, introducing no cloud service, no external queue, no SaaS dependency. The worker runs in the same Docker Compose network as everything else. |
| **II. Auditability by Default** | PASS | Every automatic recompute — successful or permanently failed — writes an `AuditLog` entry via the existing `record_action()` (FR-014). No new audit mechanism, no gap: a successful automatic recompute is indistinguishable in shape from a `computerisk` batch entry (both `risk.computed`, `actor=None`), and a permanently-failed one gets its own new action value (`risk.recompute_failed`) so it is discoverable and distinguishable, per FR-010. |
| **III. RBAC (NON-NEGOTIABLE)** | PASS | This feature introduces no new user-facing route and no new role-checked surface. The one existing route this feature touches by proximity — the manual recompute endpoint — is explicitly required to be byte-for-byte unchanged in its role enforcement (FR-012, FR-015). A background task has no "role" of its own; it runs with the same unattended, `actor=None` posture `computerisk` already established. |
| **IV. Explainable AI Outputs** | PASS | An automatically-recomputed assessment carries exactly the same explanation Phase 3a's Principle-IV-satisfying design already guarantees (factors sum to score, all five factors present, `computed_by=None` honestly recorded) — because it is produced by the identical `engine.persist()` call. This feature adds no new decision surface to explain; it only changes *when* the existing, already-explained decision gets recomputed. |
| **V. Test-First (NON-NEGOTIABLE)** | PASS | The user description names this explicitly: tests for retry/backoff and for loaddataset-triggers-redundant-but-correct-tasks are required, not optional, and not just the happy path. `research.md` §5 records the eager-vs-non-eager test split this requires. Factory Boy supplies fixtures throughout, matching Phase 3a's precedent. |
| **VI. Disposable Prototyping** | N/A | No Phase 0 spike code is involved. |

**Result: PASS.** No violations, so Complexity Tracking stays empty.

### Post-Phase-1 re-evaluation

Re-checked after research, data-model, contracts, and quickstart were
written. Still **PASS**. Two points are worth stating plainly:

- **Signals are used here after being explicitly rejected elsewhere in the
  codebase** (`apps/audit/services.py`'s docstring; Phase 3a's own T094
  test asserting their absence). This is not a constitution violation — no
  principle forbids signals — but it is a deliberate architectural
  departure from an established local convention, and research.md §1
  states plainly why the earlier rejection and this feature's use of them
  are both correct in their own scope, rather than letting the tension go
  unaddressed. Phase 3a's T094 test itself will be revised (not silently
  left contradicting reality) as part of this feature's tasks — asserting
  the narrower, still-true claim that no code path recomputes *synchronously
  inside a request*, rather than the now-outdated "no signal handler exists
  at all."
- **This feature adds a fourth long-running process** (`celery-worker`)
  to a platform that has run on three (`web`, `db`, `redis`) since Phase 1.
  This is not scope creep — it is the concrete fulfillment of Phase 1's own
  stated deferral ("Celery is added by the first module that requires
  queued/async work"), not a new architectural direction introduced without
  precedent.

## Project Structure

### Documentation (this feature)

```text
specs/006-automatic-risk-recompute/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output — no new tables, documents reuse
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── celery-task-contract.md   # the task's signature/behavior contract
├── checklists/
│   └── requirements.md   # existing, from /speckit-specify
└── tasks.md              # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
config/
├── celery.py                        # NEW: Celery("insurance_ai_platform") app factory
├── __init__.py                      # EDITED: import celery_app so @shared_task resolves
└── settings/
    └── base.py                      # EDITED: CELERY_BROKER_URL/CELERY_RESULT_BACKEND from REDIS_URL

apps/
├── risk/
│   ├── tasks.py                     # NEW: recompute_customer_risk(customer_id)
│   └── tests/
│       └── test_tasks.py            # NEW: happy path (eager), retry/backoff
│                                     #      (non-eager apply()), exhaustion,
│                                     #      no-op-when-unscored, loaddataset
│                                     #      redundancy-is-still-correct
│   # apps/risk/models.py, engine.py, views.py, management/commands/computerisk.py
│   # all UNCHANGED — this feature calls their existing public functions only.
├── customers/
│   └── apps.py                      # EDITED: ready() connects Customer post_save receiver
├── policies/
│   └── apps.py                      # EDITED: ready() connects Policy post_save receiver
├── claims/
│   └── apps.py                      # EDITED: ready() connects Claim post_save receiver
└── risk/tests/test_engine.py        # EDITED: T094's "no signal handler exists" assertion
                                      #         narrowed to "no synchronous-in-request
                                      #         recompute exists" — see Constitution Check
                                      #         post-Phase-1 note above

docker-compose.yml                   # EDITED: new celery-worker service
```

**Structure Decision**: No new Django app. The task and its tests live
inside `apps/risk/` because they are risk-domain orchestration, not a new
domain concern — `apps/risk/tasks.py` sits alongside `engine.py` the same
way `management/commands/computerisk.py` already does, as another *caller*
of the engine rather than a new layer. The three signal receivers live in
each *source* app's `apps.py` (`customers`, `policies`, `claims`) rather
than centralized in `apps/risk/`, because Django's own convention for
cross-app `post_save` wiring is for the app that *needs to react* to
register the receiver in its own `ready()` — this mirrors exactly how
`apps/core/audit_routes.register_defaults()` is deferred to `ready()`
for the same reason (the app registry must be populated first). Centralizing
all three receivers inside `apps/risk/apps.py` was considered and rejected:
it would make `apps.risk` reach into `customers`/`policies`/`claims` model
internals from the outside, whereas each source app importing
`apps.risk.tasks.recompute_customer_risk` and calling `.delay()` on its own
save is a one-directional dependency (risk is depended-upon, not
depending-on), matching the dependency direction those three apps already
have on `apps.risk` today (they know nothing about it; `apps.risk` reads
their models).

**Note on `config/celery.py` and `config/__init__.py`**: this is the
canonical Django+Celery integration layout from Celery's own documentation,
not a project-specific invention — using the standard shape here is
deliberate so a future contributor's prior Celery experience transfers
directly.

**Note on the docker-compose change**: `celery-worker` reuses the `web`
image (`build: context: ., dockerfile: docker/django/Dockerfile`) rather
than a new Dockerfile, so the worker's dependency set can never drift from
the web process's — both run literally the same installed code, which is
what makes FR-006's "exactly the same computation and persistence logic"
guarantee hold at the deployment level, not just the source level.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
