---
description: "Task list for Phase 3b — Automatic Risk Recompute"
---

# Tasks: Phase 3b — Automatic Risk Recompute

**Input**: Design documents from `/specs/006-automatic-risk-recompute/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED, and non-negotiable here. The user description names test-first
explicitly under Principle V and calls out two behaviors — retry/backoff and
loaddataset-triggers-redundant-but-correct-tasks — that MUST be tested beyond
the happy path. Test tasks precede their implementation within every phase.

**Organization**: Tasks are grouped by user story so each can be implemented and
tested independently, following research.md's decisions and the celery-task
contract.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Include exact file paths in descriptions

## Path Conventions

Django web service, API-only, now with one background worker process. Paths
below are repository-root-relative, matching plan.md's Project Structure.

---

## Phase 1: Setup (Celery Scaffolding)

**Purpose**: Stand up Celery as platform infrastructure — the app factory,
settings, dependency, and worker process — before any risk-specific code
exists. This is the first time Celery is introduced to the project.

- [X] T001 Add `celery>=5.4,<6.0` to `pyproject.toml`'s `[project].dependencies` (research.md §4)
- [X] T002 Create `config/celery.py`: `Celery("insurance_ai_platform")` app instance, `app.config_from_object("django.conf:settings", namespace="CELERY")`, `app.autodiscover_tasks()` — the canonical Django+Celery layout (research.md §4)
- [X] T003 Edit `config/__init__.py` to import `celery_app` from `config.celery` as `__all__ = ("celery_app",)`, so `@shared_task` resolves correctly across the project
- [X] T004 Add `CELERY_BROKER_URL = REDIS_URL` and `CELERY_RESULT_BACKEND = REDIS_URL` to `config/settings/base.py`, reusing the existing required `REDIS_URL` setting — no new environment variable (research.md §4)
- [X] T005 Add `CELERY_TASK_ALWAYS_EAGER = True` and `CELERY_TASK_EAGER_PROPAGATES = True` to `config/settings/test.py` (research.md §5) — this governs the *default* test behavior; retry/exhaustion tests override it per-test (see Phase 4)
- [X] T006 Add a `celery-worker` service to `docker-compose.yml`: same `build` as `web` (no new Dockerfile), `command: celery -A config worker --loglevel=info`, `env_file: .env`, `depends_on: db` and `redis` both `condition: service_healthy` (research.md §4, plan.md Project Structure)
- [X] T007 Verify the stack boots clean: `docker compose up -d`, confirm `celery-worker` reaches a healthy/running state and its logs show a successful "ready" line with no import errors (quickstart.md Prerequisites)

**Checkpoint**: Celery is live infrastructure — a worker process exists, connects to Redis, and can run a task — but no risk-specific behavior exists yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The task itself and the signal-to-task wiring. Every user story
below depends on `recompute_customer_risk` existing and being reachable from
a real model save — nothing in Phase 3+ can be implemented, let alone
tested, until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for the task and its trigger wiring ⚠️

> Write these FIRST and confirm they FAIL before implementing T012–T017. Eager
> mode (T005) makes these fast, synchronous, in-process assertions — no real
> worker or Redis interaction needed for this phase's tests.

- [X] T008 [P] Write a task test asserting `recompute_customer_risk(customer_id)` is a no-op (no `engine.persist()` call, no `AuditLog` entry) when the customer has no existing `RiskAssessment`, in `apps/risk/tests/test_tasks.py` (FR-005, celery-task-contract.md)
- [X] T009 [P] Write a task test asserting `recompute_customer_risk(customer_id)` is a no-op when `customer_id` does not resolve to a live `Customer` (archived or nonexistent), in `apps/risk/tests/test_tasks.py` (spec.md edge case: archived customer)
- [X] T010 [P] Write a task test asserting `recompute_customer_risk(customer_id)`, when the customer already has a `RiskAssessment`, produces a result identical in shape to calling `engine.score_customer()` + `engine.persist(actor=None)` directly — same score, same tier, same five factor rows, `computed_by is None` — in `apps/risk/tests/test_tasks.py` (FR-006, FR-007)
- [X] T011 [P] Write signal-wiring tests asserting saving a `Customer`, a `Policy`, and a `Claim` (three separate tests) each enqueue exactly one `recompute_customer_risk` call for the correct `customer_id` (`Customer.id` directly; `Policy.customer_id`; `Claim.policy.customer_id`) — using eager mode's synchronous execution and asserting on the resulting `RiskAssessment` state (since the customer already has one) rather than inspecting the queue, in `apps/risk/tests/test_signals.py` (FR-003, data-model.md's trigger table)

### Implementation of the task and trigger wiring

- [X] T012 Create `apps/risk/tasks.py` with `recompute_customer_risk`, decorated `@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=5)`: re-fetch `Customer.objects.get(pk=customer_id)` (default manager — archived/missing customers raise `DoesNotExist`, caught and treated as a no-op, never retried), return early if `RiskAssessment.objects.filter(customer=customer).exists()` is `False`, otherwise call `engine.score_customer(customer)` then `engine.persist(customer, result, actor=None)` (celery-task-contract.md, FR-005, FR-006)
- [X] T013 Create `apps/risk/signals.py` with three `post_save` receiver functions — `on_customer_saved`, `on_policy_saved`, `on_claim_saved` — each resolving the affected `customer_id` and enqueueing via `transaction.on_commit(lambda: recompute_customer_risk.delay(customer_id))`, never a bare `.delay()` (research.md §1, celery-task-contract.md's trigger contract)
- [X] T014 Add a `ready()` method to `apps/customers/apps.py`'s `CustomersConfig` (no `ready()` currently exists) that imports and connects `apps.risk.signals.on_customer_saved` to `post_save` for the `Customer` model (plan.md Project Structure: receivers live in the source app, not centralized in `apps.risk`)
- [X] T015 Add a `ready()` method to `apps/policies/apps.py`'s `PoliciesConfig` (no `ready()` currently exists) that connects `apps.risk.signals.on_policy_saved` to `post_save` for the `Policy` model
- [X] T016 Add a `ready()` method to `apps/claims/apps.py`'s `ClaimsConfig` (no `ready()` currently exists) that connects `apps.risk.signals.on_claim_saved` to `post_save` for the `Claim` model
- [X] T017 [P] Create `RiskAssessmentFactory`-adjacent test fixtures needed by `test_tasks.py`/`test_signals.py` if not already covered by Phase 3a's existing `apps/risk/factories.py` — extend that file only if a genuinely new fixture shape is needed (e.g. a customer-with-no-assessment-yet convenience), not a duplicate of existing factories

**Checkpoint**: A Customer/Policy/Claim save enqueues a task; the task correctly no-ops or recomputes. This is the mechanism every user story below exercises from a different angle.

---

## Phase 3: User Story 1 — A Risk Manager Trusts an Assessment Without Manually Recomputing (Priority: P1) 🎯 MVP

**Goal**: Changing a customer's own data, a live policy, or a live claim
automatically recomputes that customer's existing risk assessment, without
any manual trigger — including changes to fields no scoring factor reads,
which still trigger a recompute (over-reporting is deliberate).

**Independent Test**: Compute an assessment for a customer, change a live
policy's premium via the real API, wait, and confirm the stored assessment's
score, tier, and `computed_at` reflect the new data with `is_stale` back to
`false` — no manual recompute call anywhere in the test.

**This is the feature's entire reason to exist** — Phase 3a made staleness
visible; this closes the gap between "visible" and "fixed."

### Tests for User Story 1 ⚠️

- [X] T018 [P] [US1] Write an eager-mode test asserting a `Policy` update (e.g. `premium_usd` change) for a customer with an existing assessment results in that assessment's `computed_at` advancing and its score/tier reflecting the new premium, in `apps/risk/tests/test_signals.py` (FR-003, Acceptance Scenario 1)
- [X] T019 [P] [US1] Write an eager-mode test asserting a new `Claim` filed against a live policy for an already-assessed customer triggers a recompute reflecting that claim, in `apps/risk/tests/test_signals.py` (Acceptance Scenario 2)
- [X] T020 [P] [US1] Write an eager-mode test asserting a `Customer` field change (e.g. `age`) for an already-assessed customer triggers a recompute, in `apps/risk/tests/test_signals.py` (Acceptance Scenario 3)
- [X] T021 [P] [US1] Write an eager-mode test asserting a change to a field NO scoring factor reads (e.g. `Customer.phone`, `Policy.renewal_probability`) still triggers a recompute — asserting `computed_at` advances even though score/tier are unchanged — in `apps/risk/tests/test_signals.py` (FR-004, Acceptance Scenario 4, the deliberate over-triggering philosophy)
- [X] T022 [P] [US1] Write a test asserting `is_stale` on the assessment serializer reads `false` immediately after an automatic recompute, reusing Phase 3a's `apps/risk/serializers.py` staleness derivation unchanged, in `apps/risk/tests/test_signals.py` (Independent Test criterion)

### Implementation for User Story 1

- [X] T023 [US1] Verify Phase 2's `apps/risk/signals.py` + `apps/risk/tasks.py` already satisfy every acceptance scenario in this story with no additional code — this story is a verification checkpoint on top of the Foundational phase, not new production code, since FR-003/FR-004's broad-trigger requirement was already implemented in T012–T016

**Checkpoint**: The primary user-facing promise of Phase 3b — automatic, trustworthy recompute — is demonstrably true. This alone, atop Phase 2, is a viable MVP.

---

## Phase 4: User Story 2 — The Platform Recovers From a Transient Recompute Failure (Priority: P1)

**Goal**: A recompute attempt that fails transiently is retried automatically
with increasing delay between attempts, and succeeds without any human
noticing the earlier failure.

**Independent Test**: Force a recompute to fail once, then succeed on retry;
confirm the retry was delayed (not immediate) and the assessment ends up
correctly recomputed.

**Sequenced as P1, immediately after US1**: automatic recompute that silently
stops working on the first transient error is not meaningfully "automatic" —
this closes the reliability gap the moment the happy path exists.

### Tests for User Story 2 ⚠️

> These tests deliberately run OUTSIDE eager mode (research.md §5) — eager
> mode disables Celery's retry machinery, so exercising FR-008/FR-009 for
> real requires calling the task through Celery's own `apply()`/retry path.

- [X] T024 [P] [US2] Write a test that monkeypatches `apps.risk.engine.persist` to raise on its first call and succeed on its second, invokes `recompute_customer_risk.apply(args=[customer_id])` (non-eager, real retry path), and asserts the task ultimately succeeds and the assessment reflects the correct result, in `apps/risk/tests/test_tasks.py` (Acceptance Scenario 2)
- [X] T025 [P] [US2] Write a test asserting the delay before a retry is nonzero and that a second forced failure's computed backoff is longer than the first's — inspecting the task's own `retry_backoff`-computed countdown (via `self.request.retries` and Celery's backoff calculation, not a real `sleep()`) rather than measuring wall-clock time, in `apps/risk/tests/test_tasks.py` (FR-008, Acceptance Scenario 1). Note: exercising two real retries through `task.apply()` required `override_settings(CELERY_TASK_EAGER_PROPAGATES=False)`, not just `apply(throw=False)` — Celery's own recursive retry step in `Task.apply()` (`retval.sig.apply(retries=retries + 1)`) doesn't forward `throw`, so it reverts to the settings-derived default past the first retry
- [X] T026 [P] [US2] Write a test asserting that after a failed-then-succeeded retry sequence, exactly one `RiskAssessment` row exists for the customer and no partial/inconsistent state is visible at any point a caller could observe it (query before and after, not mid-retry) — in `apps/risk/tests/test_tasks.py` (Acceptance Scenario 2, "no trace of the earlier failed attempt")

### Implementation for User Story 2

- [X] T027 [US2] Verify Phase 1's `@shared_task(autoretry_for=(Exception,), retry_backoff=True, ...)` decorator (T012) already satisfies FR-008/FR-009 — this story, like US1, is primarily a verification checkpoint; if T024–T026 fail, the fix is tuning the decorator's arguments in `apps/risk/tasks.py`, not new architecture. Confirmed: no decorator changes were needed, all three tests pass against the existing configuration.

**Checkpoint**: Transient failures self-heal. Combined with US1, automatic recompute is now both correct and resilient.

---

## Phase 5: User Story 5 — Manual Recompute Still Works Exactly As Before (Priority: P1)

**Goal**: The Phase 3a on-demand recompute route, its response shape, its
role enforcement, and its audit behavior are completely unaffected by this
feature's existence.

**Independent Test**: Trigger a manual recompute while automatic recompute
is active platform-wide; confirm identical behavior to Phase 3a.

**Sequenced as P1, third**: this is a regression guarantee that must hold
from the moment any of this feature's code can run, not a nice-to-have
checked at the end — placed here (rather than last) so a Foundational-phase
regression is caught immediately, before US3/US4 add more surface.

### Tests for User Story 5 ⚠️

- [X] T028 [P] [US5] Write a test asserting `POST /api/risk/assessments/recompute/` (Phase 3a's existing route) succeeds with the same response shape, status code, and role restrictions as Phase 3a's own `test_views.py::TestRecompute` suite, run with automatic recompute's signals connected (not disabled), in `apps/risk/tests/test_views.py` (extend, do not duplicate, Phase 3a's existing tests) (FR-012, Acceptance Scenario 1). Note: signals are connected unconditionally at Django startup for every test process (no "disabled" mode exists to compare against), so this is `TestRecomputeWithAutomaticRecomputeActive` asserting Phase 3a's response shape/status/refusal-path under that always-on state.
- [X] T029 [P] [US5] Write a test asserting a manual recompute (via the API) and an automatic recompute (via a concurrent Policy save for the same customer) both resolve to exactly one current, internally-consistent `RiskAssessment` — reusing `engine.persist()`'s existing `select_for_update()` guarantee from Phase 3a, verified here under the new automatic-trigger condition specifically — in `apps/risk/tests/test_views.py` (FR-013, Acceptance Scenario 2, SC-008)

### Implementation for User Story 5

- [X] T030 [US5] Verify Phase 3a's `apps/risk/views.py` `RiskAssessmentViewSet.recompute` action requires zero changes — confirm by running Phase 3a's full `apps/risk/tests/test_views.py` and `apps/risk/tests/test_permissions.py` suites unmodified and green under this feature's new signals/task code (FR-012, FR-015). Confirmed: 70/70 pass, `apps/risk/views.py` at 100% coverage, zero changes to views.py. En route, found and fixed an unrelated pre-existing gap: `test_no_business_actions.py`'s AST allowlist never added `"update"` when commit 9c17e5d switched `engine.persist()`'s Customer risk-mirror write from `.save()` to `.update()` (avoiding signal re-entrancy) — one-line allowlist fix, confirmed safe (same mirror-write the allowlist already permitted via `"save"`).

**Checkpoint**: Both recompute paths — manual and automatic — coexist correctly. Three of five user stories (the two P1s that aren't this one, plus this one) are now complete: the platform automatically recomputes, recovers from transient failure, and never regresses the existing manual path.

---

## Phase 6: User Story 3 — An Operator Learns a Recompute Permanently Failed (Priority: P2)

**Goal**: When every retry for a recompute is exhausted, a durable,
discoverable record is created — using the platform's existing audit
mechanism, not a new alerting channel — and that customer remains eligible
for future automatic recompute attempts.

**Independent Test**: Force every retry to fail, let retries exhaust, and
confirm a discoverable `AuditLog` entry exists naming the customer and the
failure; confirm a later change to that customer still enqueues a fresh
attempt.

### Tests for User Story 3 ⚠️

- [X] T031 [P] [US3] Write a non-eager test that forces every retry attempt to fail (monkeypatch `engine.persist` to always raise), drives the task to `max_retries` exhaustion via `apply(throw=False)`, and asserts one `AuditLog` entry exists with `action="risk.recompute_failed"`, `outcome="refused"`, and `context` naming the customer id, in `apps/risk/tests/test_tasks.py` (FR-010, Acceptance Scenario 1). Note: reaching true 5-retry exhaustion inside `apply()` needed `override_settings(CELERY_TASK_EAGER_PROPAGATES=False)` rather than a bare `apply(throw=False)` -- same `apply()`-recursion quirk T025 already documented (the `throw` kwarg doesn't survive past the first retry). Currently RED (expected): fails on `entries.count() == 1` (0 rows) since T035's `on_failure` handler doesn't exist yet.
- [X] T032 [P] [US3] Write a test asserting the same exhausted-retry scenario does NOT raise an unhandled exception out of the task (the worker process must not crash) and does NOT modify the customer's existing `RiskAssessment` in any way, in `apps/risk/tests/test_tasks.py` (Acceptance Scenario 1, "without raising an unhandled error"). Currently GREEN even pre-T035: `apply()` returning a failed-not-raised result and leaving the prior assessment row untouched are both inherent to Celery's own exhaustion handling, not something the `on_failure` handler adds -- this test guards that property, T031/T034 guard the audit side.
- [X] T033 [P] [US3] Write a test asserting that after an exhausted-retry failure record exists for a customer, a fresh `recompute_customer_risk` invocation for that same customer (simulating a later data change) proceeds normally and is not blocked or short-circuited by the earlier failure record, in `apps/risk/tests/test_tasks.py` (FR-011, Acceptance Scenario 2). Currently RED (expected): asserts one prior `risk.recompute_failed` row (T035 not yet implemented) before exercising the fresh invocation.
- [X] T034 [P] [US3] Write a test asserting the exhausted-retry `AuditLog` entry is queryable and distinguishable from a successful `risk.computed` entry by action name alone, in `apps/risk/tests/test_audit.py` (extending Phase 3a's existing audit test file) (SC-005, data-model.md's action-value table)

### Implementation for User Story 3

- [X] T035 [US3] Implement the `on_failure` handler for `recompute_customer_risk` in `apps/risk/tasks.py` (Celery's `Task.on_failure(self, exc, task_id, args, kwargs, einfo)` override, or an `after_task_publish`/`task_failure` signal scoped to this task — whichever the T031–T034 tests actually require): on final-retry exhaustion, call `apps.audit.services.record_action(actor=None, action="risk.recompute_failed", target_type="risk.RiskAssessment", target_id=<customer's existing assessment id>, outcome="refused", context={"customer_id": args[0], "exception": str(exc), "attempts": self.request.retries})` (FR-010, research.md §3, celery-task-contract.md). Implemented as a `RecomputeCustomerRiskTask(Task)` subclass passed via `base=` (bind=True's `self` in `on_failure` is the task instance, so `self.request.retries` and a `RiskAssessment.objects.filter(customer_id=...).first()` lookup for target_id both work as documented). All of T031-T034 green.
- [X] T036 [US3] Add a structured `logger.error(...)` call alongside the audit write in the `on_failure` handler, carrying the same customer id and exception detail, for operators who tail logs rather than query the audit table (research.md §3, spec.md Assumptions' "alert" definition)

**Checkpoint**: Every failure mode this feature can produce is now observable through the platform's existing tools — no silent, permanently-stuck stale assessment.

---

## Phase 7: User Story 4 — Loading the Source Dataset Never Corrupts a Score (Priority: P2)

**Goal**: Re-running `loaddataset` against the full seeded population enqueues
a proportional number of recompute tasks — one per record written — and the
risk book remains exactly correct afterward, with the redundant volume of
same-answer tasks accepted as a known, documented tradeoff rather than
something this feature suppresses.

**Independent Test**: Run the loader against a population where every
customer already has an assessment; confirm the resulting task count is
proportional to records written, every assessment is unchanged in content,
and no duplicates exist.

**Depends on Phase 2 and benefits from US1's trigger tests already existing**
— this story specifically stresses the same trigger path at realistic
dataset-loader volume and asserts correctness holds, not new trigger logic.

### Tests for User Story 4 ⚠️

- [X] T037 [P] [US4] Write a test seeding several customers with existing assessments, re-running `loaddataset` against unchanged source data for those customers (eager mode), and asserting each resulting recompute produces output identical to the customer's pre-load assessment — same score, tier, and factor rows — in `apps/risk/tests/test_loaddataset_integration.py` (new file) (FR-016, Acceptance Scenario 1)
- [X] T038 [P] [US4] Write a test asserting that after a full reload touching N already-assessed customers, exactly N `RiskAssessment` rows exist (no duplicates created by N redundant recompute enqueues), in `apps/risk/tests/test_loaddataset_integration.py` (Acceptance Scenario 2, SC-006)
- [X] T039 [P] [US4] Write a test explicitly asserting the NUMBER of recompute tasks enqueued by a reload is proportional to (not deduplicated below) the number of records the loader wrote — asserting the redundant-but-correct behavior directly rather than only its end state, per the user description's explicit instruction to test "the loaddataset-triggers-redundant-but-correct-tasks behavior explicitly, not just the happy path," in `apps/risk/tests/test_loaddataset_integration.py` (FR-017). Patches `recompute_customer_risk.delay` and asserts `call_count == 3 * customer_count` (customer + policy + claim saves per row, each unconditional per FR-004) — verified this actually exercises the trigger path (initially passed vacuously at 0 calls until `django_capture_on_commit_callbacks(execute=True)` was added; without it pytest-django's rolled-back outer transaction discards every `on_commit` callback silently, per test_signals.py's documented gotcha).
- [X] T040 [P] [US4] Write a test asserting every assessment's factors still sum to its score after a full reload-and-drain cycle (reusing Phase 3a's sum-invariant assertion pattern from `apps/risk/tests/test_engine.py`), in `apps/risk/tests/test_loaddataset_integration.py` (SC-002, SC-006)

### Implementation for User Story 4

- [X] T041 [US4] Verify Phase 2's signal wiring (T013–T016) already handles this correctly with zero new code — `loaddataset`'s existing per-row `Customer.objects.create_with_reference`/`update` and `Policy`/`Claim` serializer-backed writes already fire `post_save` like any other write; this story's tasks are verification, and any T037–T040 failure indicates a Foundational-phase bug to fix in `apps/risk/signals.py` or `apps/risk/tasks.py`, not new loaddataset-specific code. Confirmed: T037-T040 all pass with zero changes to `apps/risk/signals.py` or `apps/risk/tasks.py` — the existing `on_customer_saved`/`on_policy_saved`/`on_claim_saved` receivers and their `transaction.on_commit()` wiring handle loaddataset's per-row serializer writes exactly like any other write path, with no loaddataset-specific code needed.

**Checkpoint**: The platform's most routine, highest-volume write operation is proven safe under this feature's broad triggering, with the resulting inefficiency explicitly demonstrated (not just asserted away) as the accepted tradeoff FR-017 names.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T042 Revise Phase 3a's `apps/risk/tests/test_engine.py::test_no_signal_handler_or_scheduled_task_touches_risk_scoring` (T094) to assert the narrower, still-true claim this feature leaves intact: no code path recomputes *synchronously inside a request or another model's save* — replacing the now-outdated "the codebase contains no signal handler at all," per plan.md's Constitution Check post-Phase-1 note. Found and fixed a real bug while doing this: `Signal._live_receivers()` in this project's pinned Django returns a `(sync_receivers, async_receivers)` 2-tuple of LISTS, not a flat list — the original test's `for receiver in receivers:` iterated over the 2-tuple itself, binding `receiver` to each inner list rather than a function, so `getattr(receiver, "__module__", "")` silently fell through to `""` and the assertion passed vacuously regardless of what was actually connected, on both sides of Phase 3b's signal wiring. Renamed to `test_no_signal_handler_or_scheduled_task_touches_risk_scoring_synchronously`; now correctly unpacks the tuple and asserts no connected receiver's module is `apps.risk.engine` and no receiver is `recompute_customer_risk` itself (only a `signals.py` wrapper calling `.delay()` inside `on_commit()` may be connected). Also revised the adjacent `TestNoAutomaticRecomputation` class (renamed `TestNoSynchronousRecomputation`) to stop asserting the now-false Phase-3a claim ("nothing recomputes, ever") that only kept passing because plain `pytest.mark.django_db` tests never fire `on_commit()` callbacks — each of its 5 tests now has a paired `..._does_recompute_once_committed` test using `django_capture_on_commit_callbacks(execute=True)`, except the customer-archival case, which correctly asserts a committed no-op instead (the task's `Customer.objects.get()` lookup uses the live-only default manager, so an archived customer's own recompute enqueue can never find it and returns early — verified this is the real mechanism, not asserted blindly).
- [X] T043 [P] Add a module docstring to `apps/risk/tasks.py` recording why signals are used here after being rejected for audit writes (`apps/audit/services.py`'s "no signals" stance) — the two requirements are opposite (audit must share the triggering transaction; recompute enqueue must NOT), per research.md §1, so the next reader doesn't "fix" this into consistency with the audit module's convention. Already done — this docstring was written in the original Phase 3b Foundational commit (4d86b16); checkbox was simply never reconciled.
- [X] T044 [P] Add a module docstring to `apps/risk/signals.py` recording the `transaction.on_commit()` requirement and why a bare `.delay()` inside a receiver would be wrong (enqueueing for data that might be rolled back), per research.md §1. Already done — same commit (4d86b16) as T043; checkbox reconciliation only.
- [X] T045 Update `specs/005-risk-scoring-engine/spec.md` or its plan.md with a forward-reference note that FR-036/SC-011 ("nothing recomputes automatically") was Phase-3a-scoped and is superseded by this feature's explicit, tested introduction of automatic recompute — so a future reader of 005 alone isn't misled into thinking automatic recompute still doesn't exist platform-wide. Added blockquote notes directly under both FR-036 and SC-011 in spec.md, at the point each claim is stated.
- [X] T046 Run the full suite and confirm no regression across all apps: `docker compose exec web pytest` — expect the platform's prior full-suite count plus every test added in this feature's phases. 1080 passed, 0 failed.
- [X] T047 Confirm coverage: `docker compose exec web pytest --cov=apps.risk --cov-report=term-missing`, requiring the same bar Phase 3a set for business-rule code — 100% on `apps/risk/tasks.py` and `apps/risk/signals.py` (the new business-rule-adjacent orchestration this feature adds), consistent with Constitution Principle V naming risk scoring's business-rule code explicitly. Both at 100%; all of apps/risk/ at 100% except serializers/views/urls (0% here, exercised by other test modules not included in this narrower `apps/risk`-only run).
- [X] T048 Execute `specs/006-automatic-risk-recompute/quickstart.md` steps 1–3 end to end against the real dev stack (real worker, real Redis) — these are read-only/additive and safe to run without additional confirmation. Confirmed with the operator before writing throwaway quickstart users/policy/customer to dev (same standing dev-DB rule as every prior phase), then ran all three steps for real: Step 1 — 239/239 risk tests green, full suite 1084 passed. Step 2 — PATCHed policy 1's premium via a real Underwriter session; customer 1's RiskAssessment.computed_at advanced from 2026-08-20 20:02:18 to 2026-08-31 22:30:22 (~16s after the PATCH) with computed_by=None, and the API's by-customer endpoint confirmed is_stale:false. Step 3 — created customer CL-90001 (never scored) and a live policy for it; after waiting, RiskAssessment.objects.filter(customer=c).exists() is False, confirming FR-005/SC-003 hold against the real worker.
- [X] T049 Execute `specs/006-automatic-risk-recompute/quickstart.md` steps 4–6 — step 4 deliberately forces a failure (safe: it's monkeypatched inside a `manage.py shell` invocation, not a persistent code change) and step 5 re-runs `loaddataset` against the dev DB, which writes to the persistent database — confirm with the operator before running step 5 against dev, or run its equivalent assertion via the T037–T040 test suite instead. Confirmed with the operator before running against dev. Step 4 — forced `engine.persist` to raise via monkeypatch inside `recompute_customer_risk.apply(...)`; task state `FAILURE`, one `risk.recompute_failed` audit row (`outcome=refused`, `attempts=5`, exception text and `customer_id=1` in context), customer 1's assessment left byte-for-byte unchanged (score 25, `computed_at` unmoved) proving no partial write; retriggering without the patch recomputed normally (`computed_at` advanced), proving the earlier permanent failure did not disable the customer (FR-011). Step 5 — captured a SHA-256 hash + count (3001) of all `(customer_id, score, tier)` rows, ran `loaddataset` for real against dev (3000 customers/policies updated, 2246 claims updated, exit 0), waited for the resulting task flood to drain (celery queue length back to 0), re-hashed: identical hash and count — SC-006 holds despite ~3000 redundant recomputes each running for real. Step 6 — POSTed `/api/risk/assessments/recompute/` for customer 1 as a real Risk Manager session; 200, response shape matches Phase 3a's, `computed_by` is the risk manager's email (unlike the automatic path's `None`), and the resulting `risk.computed` audit row's `actor_id` is populated exactly like Phase 3a's manual-recompute entries — manual path is unaffected by this feature (FR-012/SC-007). Throwaway quickstart users and cookie jars deleted afterward.

Post-hoc investigation (prompted by the operator questioning the 3001-vs-3000 row count in step 5's snapshot rather than accepting the note as-is): traced it to a real doc bug, not noise. quickstart.md's step 3 created a scratch `Customer` (`CL-90001`) and its `Policy` but never deleted them — the doc's cleanup only ever covered the throwaway `qs.*` auth users, never the data rows step 3 itself creates. That same gap was repeated in this session's own step-3 run (`CL-90002`), so two leaked customer+policy pairs were sitting in dev, inflating `RiskAssessment.objects.count()` by exactly the amount a stray *scored* customer would (a third, unrelated `CL-90000` row — a `CustomerFactory`-sequence artifact predating this feature, out of scope here — accounts for the remaining +1 and was left alone). Deleted both leaked `CL-9000{1,2}` customer+policy pairs from dev after confirming neither had a `RiskAssessment` to lose, restoring the true count. Fixed quickstart.md step 3 to delete its own scratch customer+policy at the end of the step, closing the gap for future runs.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — stands up Celery as infrastructure only
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational
- **US2 (Phase 4)**: Depends on Foundational; independent of US1's specific tests, but naturally follows it as the MVP's reliability companion
- **US5 (Phase 5)**: Depends on Foundational; independent of US1/US2, sequenced early (P1, third) as a regression gate
- **US3 (Phase 6)**: Depends on Foundational; reuses US2's non-eager testing approach
- **US4 (Phase 7)**: Depends on Foundational; benefits from US1's trigger tests existing as a pattern, but is independently testable on its own
- **Polish (Phase 8)**: Depends on all preceding phases

### Critical Path

```
Setup → Foundational → US1 → US2 → US5 → US3 → US4 → Polish
```

### Within Each User Story

- Tests MUST be written and MUST FAIL before implementation (Principle V, per the user description's explicit instruction)
- Signal wiring before task logic before user-story-level verification
- US1, US2, and US5's "Implementation" tasks are primarily verification checkpoints on top of Phase 2 — this is deliberate: Foundational is where the real new code lives, and the P1 stories confirm that code satisfies each angle of the spec rather than duplicating it

### Parallel Opportunities

- **T008–T011** (Foundational task/signal tests) — all [P], different test files or independent test functions within one file
- **T018–T022** (US1 trigger tests) — all [P] within `test_signals.py`
- **T024–T026** (US2 retry tests) — all [P] within `test_tasks.py`
- **T028–T029** (US5 regression tests) — all [P]
- **T031–T034** (US3 exhaustion tests) — all [P]
- **T037–T040** (US4 loaddataset tests) — all [P]
- **T001–T006** (Setup) — mostly sequential (each depends on the prior file existing), except T006 (docker-compose) can proceed in parallel with T001–T005 since it doesn't depend on Python code existing yet

**Same-file caution**: tasks marked [P] within one test file are parallel as
units of work, but concurrent edits to the same file need coordination.
`apps/risk/tasks.py` and `apps/risk/signals.py` are each touched by multiple
phases (Foundational creates them; US2 and US3 extend `tasks.py`) — these are
NOT marked [P] against each other for that reason.

---

## Parallel Example: Foundational Task/Signal Tests

```bash
# Launch all four Foundational test tasks together — independent test
# functions, eager mode, no shared mutable state:
Task: "No-op-when-unscored test in apps/risk/tests/test_tasks.py"
Task: "No-op-when-archived-or-missing test in apps/risk/tests/test_tasks.py"
Task: "Identical-to-manual-recompute test in apps/risk/tests/test_tasks.py"
Task: "Signal-wiring tests (Customer/Policy/Claim) in apps/risk/tests/test_signals.py"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1)

1. Phase 1: Setup — Celery exists as infrastructure
2. Phase 2: Foundational (CRITICAL — blocks everything) — the task and signal wiring exist
3. Phase 3: US1 — automatic recompute demonstrably works
4. **STOP and VALIDATE**: quickstart.md steps 1–3

US1 alone, atop Foundational, is the feature's core value: a changed policy
or claim results in an automatically-refreshed assessment. US2 (retry) and
US5 (manual-path regression safety) are the next two P1s because a
production-credible "automatic" feature needs both resilience and a proven
non-regression before it's genuinely done — not because US1 alone is unsafe
to ship the way Phase 3a's US1 alone was judged unsafe (that judgment was
about RBAC; this feature adds no new RBAC surface, per FR-015).

### Incremental Delivery

1. Setup + Foundational → the task and trigger exist, testable in isolation
2. + US1 → automatic recompute works (**MVP**)
3. + US2 → automatic recompute survives transient failure
4. + US5 → manual recompute proven unaffected
5. + US3 → permanent failures become discoverable
6. + US4 → the platform's highest-volume write operation proven safe
7. + Polish → Phase 3a's T094 test reconciled, docstrings recording the
   deliberate signals departure, full-suite and coverage confirmed

### Parallel Team Strategy

Once Foundational is complete:

- Developer A: US1 → US5 (the trigger-correctness and regression-safety axis, both touching `test_signals.py`/`test_views.py`)
- Developer B: US2 → US3 (the failure-handling axis, both touching `test_tasks.py`'s non-eager suite)
- Developer C: US4 (the loaddataset-volume axis — genuinely disjoint test file)

---

## Notes

- **This feature's Foundational phase carries unusually more weight than its
  user-story phases.** Unlike Phase 3a (where each user story added new
  models/views/serializers), three of this feature's five user stories
  (US1, US2, US5) are primarily *verification* that Phase 2's task and
  signal wiring already satisfies the spec from a different angle — this is
  expected, not a sign the task breakdown is wrong. The real new code is
  concentrated in Phase 2 (`tasks.py`, `signals.py`, three `apps.py` edits)
  and Phase 6 (`on_failure` handling).
- **Signals are a deliberate, documented departure**, not an oversight —
  see T042/T043/T044 in Polish, and research.md §1/plan.md's Constitution
  Check post-Phase-1 note for the full rationale.
- **The `on_commit()` requirement (T013) is the single most important line
  in the Foundational phase to get right.** A bare `.delay()` inside a
  `post_save` receiver would enqueue recomputes for rolled-back writes —
  wrong, silent, and exactly the class of bug `on_commit()` exists to
  prevent (research.md §1, FR-018).
- **`loaddataset`'s redundant task volume (US4) is accepted, not
  optimized** — T037–T040 prove correctness under that volume; no task
  in this list adds coalescing, deduplication, or debouncing (FR-017,
  explicitly out of scope).
- Commit after each task or logical group.
