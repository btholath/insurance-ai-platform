# Phase 0 Research: Automatic Risk Recompute

**Feature**: 006-automatic-risk-recompute | **Date**: 2026-08-21

Five decisions carry this design. Each was verified against the current
codebase rather than assumed from the spec text alone.

---

## §1. How to hook into "a Customer, Policy, or Claim record changes"

**Decision**: `post_save` signals, one receiver per model, each resolving the
owning customer and calling a single `enqueue_recompute(customer_id)` helper
in `apps/risk/tasks.py`. Connected in each app's `AppConfig.ready()`
(`apps/customers/apps.py`, `apps/policies/apps.py`, `apps/claims/apps.py`),
matching the platform's existing app-ready registration convention (compare
`apps/risk/apps.py`... — actually `apps/core/audit_routes.register_defaults()`
is the precedent: registration deferred to `ready()` because it needs the app
registry populated first, documented in `audit_routes.py`'s own module
docstring).

**Rationale**: This is the one point where this feature deliberately departs
from an explicit prior decision, and that departure needs to be named, not
smoothed over. `apps/audit/services.py`'s module docstring states plainly:
"No signals, no on_commit hooks, no async dispatch" for audit writes, and
Phase 3a's T094 (`apps/risk/tests/test_engine.py`,
`test_no_signal_handler_or_scheduled_task_touches_risk_scoring`) asserts *the
codebase contains no signal handler at all* as a Phase-3a-scoped requirement
(FR-036/SC-011: nothing recomputes automatically). Both of those were correct
for their scope — Phase 3a is explicitly the phase where automatic
recomputation does not exist yet. This spec is exactly the phase where it is
introduced, and the FR-036/SC-011 test in `apps/risk/tests/test_engine.py`
will need to be revised (not deleted) to assert the *narrower* claim Phase 3b
actually requires: no code path recomputes synchronously inside a request or
outside the new, deliberate, tested signal-to-task path. That revision is
itself part of this feature's tasks, not a silent scope creep.

Signals are still the right mechanism for *this* trigger, and the reason is
symmetrical with why they were rejected for the audit write: `record_action`
must execute inside the same transaction as the change it describes, so that
a failure rolls the whole thing back together (`apps/audit/services.py`'s own
rationale) — synchronous, in-transaction, unconditionally executed. Automatic
recompute is the opposite shape on purpose: it must NOT execute inside the
triggering transaction (a slow or failing recompute must never be able to
fail the customer/policy/claim write that triggered it — see FR-018), and it
is explicitly allowed to be eventually consistent (SC-001's "short, bounded
time," not synchronous). `post_save` is the correct hook precisely because
Django only fires it after the row is actually written, and the actual task
enqueue happens via `transaction.on_commit()` inside the receiver — so a
save that gets rolled back (e.g., a serializer validation failure that saves
then rolls back inside a larger transaction, or a factory-in-a-test
`atomic()` block) never enqueues a task for data that was never really
persisted. This is the one place this feature uses `on_commit`, and it is
used for exactly the reason `apps/audit/services.py` says NOT to use it for
audit writes — the two requirements are opposite, so the two decisions are
both correct in their own scope.

**Alternatives considered**:
- **Explicit calls from each view/serializer/loader call site** (the
  "no signals" pattern the rest of the codebase uses). Rejected: FR-004
  requires the trigger to be broad — *any* save on *any* of the three
  models, including saves the codebase does not yet route through a single
  chokepoint (the CSV loader writes Policy/Claim rows through their
  serializers per Phase 2's "loader validates through the serializer"
  convention, but a future write path — an admin action, a data-fix script —
  would silently miss an explicit call site). A `post_save` receiver on the
  model itself is the only mechanism that is structurally as broad as FR-004
  requires without auditing every current and future call site by hand.
- **`pre_save` instead of `post_save`**: rejected — the row is not yet
  committed, so resolving `customer_id` for a *new* Policy/Claim (where the
  FK might not be validated yet) is less reliable than acting after the
  row exists.
- **Celery Beat polling `updated_at` on a schedule** instead of signals:
  rejected outright — this is a slower, coarser-grained version of exactly
  what `post_save` already gives precisely and immediately (well, immediately
  enqueued; the recompute itself still runs asynchronously). It would also
  reintroduce the "how fresh is 'the schedule'" question Phase 3a's staleness
  design (research.md §4 of 005) deliberately avoided by deriving staleness
  from timestamps rather than a maintained flag.

---

## §2. What the Celery task actually does, and where it lives

**Decision**: One task, `apps/risk/tasks.py::recompute_customer_risk(customer_id)`.
Body:

```text
1. Look up the customer (apps.customers.models.Customer.objects — the
   archival-filtering default manager. An archived customer is invisible
   here, matching the edge case in spec.md: a recompute must not
   resurrect state for a customer no longer live).
2. If no RiskAssessment exists for this customer: return immediately,
   no-op (FR-005). This is the ONLY new business-rule branch this feature
   adds; everything else is orchestration around existing engine.py code.
3. Otherwise: engine.score_customer(customer), then
   engine.persist(customer, result, actor=None) — the exact same two
   calls apps/risk/views.py's recompute action and
   apps/risk/management/commands/computerisk.py already make. No new
   scoring logic, no new persistence logic (FR-006).
```

**Rationale**: `engine.persist()` already IS the single write path FR-006
requires reusing — Phase 3a's own engine.py docstring states this explicitly
("Phase 3b calls the same `persist()` from a Celery task... the boundary is
what makes 3b additive rather than a rewrite"). This spec's implementation
is validating a boundary Phase 3a's authors already designed for, not
inventing one. `persist()`'s existing `transaction.atomic()` +
`select_for_update()` on the customer already gives FR-013's "exactly one
current, internally consistent assessment" guarantee for free — two
recomputes (manual + automatic, or two automatic) for the same customer
serialize on that row lock exactly as two manual recomputes already do
today. Nothing new is needed here; this is Phase 3a's existing concurrency
story, unchanged.

`actor=None` for every automatic recompute, matching `computerisk`'s
existing convention exactly (`apps/risk/management/commands/computerisk.py`:
"`computed_by` and the audit `actor` are null for an unattended command
run... That is honest: no user triggered it"). FR-014's audit requirement is
satisfied without new code: `persist()` already writes `risk.computed` via
`record_action(actor=actor, ...)`, and `record_action` already handles
`actor=None` honestly (`apps/audit/services.py`:
`actor_identifier = actor.email if actor is not None else ""`).

**Alternatives considered**:
- **A Celery task per (Customer, Policy, Claim) model** with model-specific
  logic: rejected. It would triple the surface for no behavioral gain — all
  three ultimately resolve to "recompute this customer," and FR-004 already
  requires that resolution to be uniform regardless of which model changed.
- **The task doing the customer/RiskAssessment-exists check itself vs. the
  signal receiver doing it before enqueueing**: the check belongs in the
  task, not the receiver. The receiver's job is cheap and synchronous
  (resolve an id, call `.delay()`); putting a `RiskAssessment.objects.filter(...).exists()`
  query in the receiver would add a synchronous DB read to every
  Customer/Policy/Claim save just to decide whether to enqueue — a violation
  of the same "don't let recompute overhead touch the triggering write" goal
  that motivated `on_commit()` in §1. Enqueueing unconditionally and having
  the task itself no-op is the cheaper, simpler design, and it is also what
  makes FR-016/FR-017 (the loaddataset tradeoff) an accepted cost rather
  than a design flaw: the "wasted" work is one Celery task consuming one
  no-op-fast-exit or one idempotent-recompute, not a synchronous query added
  to 3,000 writes.

---

## §3. Retry, backoff, and the permanent-failure record

**Decision**: Celery's built-in autoretry mechanism —
`@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=5)`
— rather than hand-rolled retry logic. `retry_backoff=True` gives Celery's
standard exponential backoff (roughly 1s, 2s, 4s, 8s, 16s... capped by
`retry_backoff_max`); `max_retries=5` bounds it per FR-009.

On the final failure (the `max_retries`th attempt has been exhausted),
Celery's own `on_failure` hook — not a `try/except` around the task body
that would defeat `autoretry_for` — is where the permanent-failure record is
written: one `record_action(actor=None, action="risk.recompute_failed",
target_type="risk.RiskAssessment", target_id=<assessment id if known, else
customer id>, outcome="refused", context={"customer_id": ..., "exception":
str(exc), "attempts": ...})` call via `apps.audit.services.record_action` —
the same function every other write path in the platform already uses. This
satisfies FR-010's "durable, discoverable record... distinguishable from a
successful recompute record" using the platform's own existing audit
mechanism, with zero new infrastructure: no new model, no new table, no new
log sink. A structured log line (`logger.error(..., extra={...})`) is
written alongside it for operators who tail logs rather than query the
audit table, but the audit entry is the durable, queryable record FR-010
and SC-005 require.

**Rationale**: This is the direct, deliberate answer to the user
description's "define what 'alert' means concretely for a local-first,
no-cloud-dependency project" — and the spec's own Assumptions section
already settled on "the existing audit log and/or structured application
logs," so research here is choosing the mechanism, not re-litigating the
decision. Reusing `record_action` rather than inventing a
`RecomputeFailure` model keeps FR-014's "same append-only mechanism...
already established" literal, and avoids a second table nobody queries
differently than `AuditLog` already supports (`action="risk.recompute_failed"`
is a filter, not a schema).

`max_retries=5` with `retry_backoff_max=600` (10 minutes) is a deliberately
generous ceiling for a local, single-worker development/demo environment —
transient failures here are far more likely to be "the DB was momentarily
locked" than "an external service is down," so most retries should resolve
within the first 2-3 attempts (seconds), and the cap exists mainly to bound
FR-009's "not indefinitely," not to model a real production SLA.

**Alternatives considered**:
- **Hand-written retry loop inside the task body** (catch, sleep,
  re-invoke): rejected. Celery's `autoretry_for`/`retry_backoff` is the
  documented, tested mechanism for exactly this; reimplementing it invites
  the class of bug (off-by-one on attempt count, backoff math errors) that
  using the library avoids, and the constitution's Technology Stack
  Constraints already bind the project to Celery — using its retry
  machinery is using the stack as intended, not an extra dependency.
- **A dedicated `RecomputeFailure` Django model**: rejected in favor of
  reusing `AuditLog` per FR-014's explicit instruction to use "the same
  append-only mechanism... already established," and because Phase 2c's
  `ClaimLoadAnomaly` precedent (a *current-state* table, deliberately
  separate from the *append-only* `AuditLog`) does not apply here — a
  permanent recompute failure is a historical event ("this happened, once,
  at this time"), not ongoing reconciled state a later success should
  clear. It belongs in the append-only trail, not a second mutable table.
- **Dead-letter queue** (a separate Celery queue for exhausted tasks):
  rejected as unnecessary infrastructure for what FR-010 actually asks
  for — a discoverable record, not a mechanism to later re-process failed
  tasks by hand. If that need arises, it is exactly the kind of future
  operational tooling the constitution's local-first, no-cloud framing
  does not require this spec to anticipate.

---

## §4. Worker process and broker configuration

**Decision**: A new `config/celery.py` (the standard Django+Celery app
factory, `Celery("insurance_ai_platform")`, `config_from_object` reading
`CELERY_` — prefixed Django settings, `autodiscover_tasks()`), imported from
`config/__init__.py` so `@shared_task` resolves correctly everywhere,
exactly as the official Celery/Django integration guide's canonical layout
specifies. `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` both set from the
already-required `REDIS_URL` setting in `config/settings/base.py` (no new
env var — `REDIS_URL` already exists and is already validated as required
at settings-import time). A new `celery-worker` service in
`docker-compose.yml`: same image as `web` (so no separate Dockerfile),
command `celery -A config worker --loglevel=info`, `depends_on: redis` and
`db` (both `service_healthy`), same `env_file`. No separate Celery Beat
service — this feature has no scheduled/periodic task, only signal-triggered
ones, so Beat is out of scope (a future spec introducing a genuinely
scheduled job is the first consumer of Beat, mirroring how Phase 1 deferred
Celery itself until a spec actually needed queued work).

**Rationale**: Redis is already provisioned (`docker-compose.yml`'s `redis`
service, healthchecked, with `redis_data` volume) specifically anticipating
this — Phase 1's plan states outright: "Redis is stood up now as required
infrastructure; Celery is added by the first module that [needs queued/async
work]." This is that module. Reusing the existing `web` image for the
worker (rather than a second Dockerfile) keeps the dependency surface
identical between the two processes — a task that imports `apps.risk.engine`
runs the exact same code the web process would run, with the exact same
installed packages, which matters directly for FR-006's "exactly the same
computation and persistence logic" guarantee holding at the *deployment*
level, not just the *code* level.

**Alternatives considered**:
- **RabbitMQ as the broker instead of Redis**: rejected — Redis is already
  provisioned, already required in settings, and the constitution names
  Redis (not RabbitMQ) as the binding cache/queue-broker technology.
  Introducing a second broker technology when one is already standing up
  unused would be pure waste.
- **`django-celery-results` / `django-celery-beat` packages** for
  DB-backed result/schedule storage: rejected. This feature's task has no
  caller that needs its return value (the signal receiver fires-and-forgets;
  nothing polls a task result), so a result backend is unnecessary
  complexity; `CELERY_RESULT_BACKEND` is left unset (or pointed at Redis
  with a short TTL, purely for `flower`/debugging visibility during
  development) rather than adding a persistence dependency for a value
  nothing reads. No Beat schedule exists, so `django-celery-beat` has
  nothing to manage.
- **A single combined `web` process running Celery inline** (e.g.,
  `--pool=solo` in the same container as gunicorn): rejected — conflates two
  independently-scaling, independently-restartable concerns, and makes it
  impossible to observe "is the worker actually running and healthy"
  separately from "is the web server up," which SC-001's "short bounded
  time" claim needs to be independently verifiable against.

---

## §5. Testing strategy for Celery tasks (Principle V)

**Decision**: `CELERY_TASK_ALWAYS_EAGER = True` and
`CELERY_TASK_EAGER_PROPAGATES = True` in `config/settings/test.py` for the
*happy-path and idempotency* tests (User Stories 1, 4, 5) — this makes
`.delay()` execute synchronously in-process, so a test can assert on the
resulting `RiskAssessment` state immediately with no worker, no Redis, no
polling or `sleep()`. Retry/backoff behavior (User Story 2) and the
permanent-failure record (User Story 3) are tested **without** eager mode —
calling the task function directly (not through `.delay()`) with Celery's
`task.apply()` / by invoking `recompute_customer_risk.run(...)` inside a
test that monkeypatches `engine.persist` to raise, and asserting on
`self.request.retries`, the computed backoff delay, and (for the exhausted
case) the audit entry written by the `on_failure` handler — Celery's own
public testing utilities (`task.apply(throw=True)`, inspecting
`AsyncResult`) are used rather than reimplementing retry counting by hand.

**Rationale**: Eager mode is the standard, documented way to unit-test "does
calling this task produce the right side effect" without standing up a real
broker in the test environment — matching this project's existing
`--reuse-db` fast-test philosophy (`pyproject.toml`'s `[tool.pytest.ini_options]`).
But eager mode *also* disables retries by default (an eager task that raises
just raises, immediately, in the calling thread) — so testing FR-008/FR-009's
actual backoff behavior, and FR-010's exhausted-retry record, requires
exercising the real (non-eager) retry path per test, which is exactly what
the user description asks for explicitly: "tests proving the retry/backoff
behavior... explicitly, not just the happy path." This is a deliberate,
named split in the test suite, not an inconsistency — `test_tasks.py`
documents which tests run eager and why in its module docstring.

**Alternatives considered**:
- **A real Celery worker + real Redis in the test environment** (e.g., via
  `pytest-celery`'s worker fixtures): rejected for this feature's test
  suite as unnecessary weight — it would make every task test slow and
  flaky (timing-dependent) for behavior `apply()`/eager mode already
  exercises deterministically. Reserved as a possible *future* addition for
  a true end-to-end smoke test (this spec's `quickstart.md` covers that
  live, against the real worker, the same way Phase 3a's quickstart
  exercised the real dev server) — not for the unit-level Principle V
  suite.
- **Mocking `engine.persist` in every task test**: used selectively (the
  retry-failure tests need a controllable failure), but NOT used for the
  happy-path tests — those call the real `engine.score_customer`/`persist`
  in eager mode against the test database, matching Phase 3a's own
  precedent of testing `engine.py` against real Factory Boy-built rows
  rather than mocks.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| 1 | Trigger mechanism | `post_save` signals + `transaction.on_commit()`, connected in each app's `AppConfig.ready()` |
| 2 | Task shape | One task, `recompute_customer_risk(customer_id)`, delegating entirely to existing `engine.score_customer()`/`persist()` |
| 3 | Retry/backoff | Celery `autoretry_for` + `retry_backoff=True`, `max_retries=5`; exhaustion recorded via existing `record_action` (no new model) |
| 4 | Worker/broker | New `celery-worker` docker-compose service (same image as `web`), broker = existing `REDIS_URL`, no Beat |
| 5 | Testing | `CELERY_TASK_ALWAYS_EAGER` for happy-path/idempotency; real (non-eager) `apply()` for retry/backoff/exhaustion tests |
