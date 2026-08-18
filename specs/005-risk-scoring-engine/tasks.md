---
description: "Task list for Phase 3a — Risk Scoring Engine"
---

# Tasks: Phase 3a — Risk Scoring Engine

**Input**: Design documents from `/specs/005-risk-scoring-engine/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED, and non-negotiable here. Constitution Principle V names risk
scoring as its **first** example of business-rule code requiring test-first
development, and SC-015 requires every band and both sides of every tier boundary
be covered. Test tasks precede their implementation within every phase.

**Organization**: Tasks are grouped by user story so each can be implemented and
tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Include exact file paths in descriptions

## Path Conventions

Django web service, API-only. Apps live under `apps/`, tests under
`apps/<app>/tests/`. Paths below are repository-root-relative and match the
Project Structure in plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new `apps/risk/` app. Unlike Phase 2c, this app does
**not** already exist — there is no placeholder to replace, so this phase creates
a module rather than filling one in.

- [ ] T001 Create the app package skeleton: `apps/risk/__init__.py`, `apps/risk/apps.py` with `RiskConfig` (`name = "apps.risk"`, `label = "risk"`, `default_auto_field = "django.db.models.BigAutoField"`), `apps/risk/migrations/__init__.py`, `apps/risk/tests/__init__.py`, and `apps/risk/management/__init__.py` + `apps/risk/management/commands/__init__.py`
- [ ] T002 Register the app: add `"apps.risk"` to `INSTALLED_APPS` in `config/settings/base.py` (after `"apps.claims"`), and mount `path("api/risk/", include("apps.risk.urls"))` in `config/urls.py`
- [ ] T003 [P] Create empty test module stubs in `apps/risk/tests/`: `test_rules.py`, `test_engine.py`, `test_models.py`, `test_serializers.py`, `test_views.py`, `test_permissions.py`, `test_staleness.py`, `test_audit.py`, `test_computerisk.py`
- [ ] T004 Verify the baseline is green before any change: run `docker compose exec web pytest` and record the current pass count (**842 tests** as of 2026-08-17), so a later failure is attributable to this feature
- [ ] T005 Capture the FR-041/SC-009 baseline: record the current `git rev-parse HEAD:apps/core/exception_handlers.py` blob hash in the implementation notes, so the empty-diff check at T081 compares against a recorded value rather than a remembered one

**Checkpoint**: App registered and importable, baseline recorded, no behavior changed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The rule set, the two models, and the migration. Every user story
reads or writes an assessment, so nothing can proceed until these exist.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for the rule set ⚠️

> Write these FIRST and confirm they FAIL before implementing T012–T014. These are
> pure-function tests requiring no database — they are the fastest and highest-value
> tests in the feature (research §6).

- [ ] T006 [P] Write band tests for the `age` factor covering **both sides of every boundary** — 18, 24, 25, 34, 35, 49, 50, 64, 65, 75 — asserting lower-inclusive/upper-exclusive banding, in `apps/risk/tests/test_rules.py` (FR-007, FR-009, SC-015)
- [ ] T007 [P] Write band tests for `policy_type` (Auto 15, Health 10, Property 5, Life 0) and for the multi-policy rule taking the **highest-scoring live policy type**, in `apps/risk/tests/test_rules.py` (FR-008, FR-010)
- [ ] T008 [P] Write band tests for `claims_history` asserting three distinct outcomes — no claim (0), zero-amount claim only (5), one or more non-zero claims (20) — so a `0.00` claim is scored as neither of the other two, in `apps/risk/tests/test_rules.py` (FR-011, FR-013)
- [ ] T009 [P] Write band tests for `claims_ratio` covering both sides of 1.0, 3.0 and 5.0, plus the bounding case (a 155× ratio contributes exactly the top band's 30, never more), in `apps/risk/tests/test_rules.py` (FR-012)
- [ ] T010 [P] Write band tests for `denied_claim` (any denied claim 10, otherwise 0), asserting it is scored independently of `claims_history`, in `apps/risk/tests/test_rules.py` (FR-014)
- [ ] T011 [P] Write tier tests covering both sides of every threshold — scores 0, 19, 20, 39, 40, 59, 60, **90**, 100 — asserting every score in 0–100 maps to exactly one tier with no gap or overlap, in `apps/risk/tests/test_rules.py` (FR-006, FR-007). **90 is the reachable maximum** (`max_score()`, research.md §5); 100 is the outer bound of the `risk_score_range` DB constraint and is unreachable under rule set 1.0.0, so both belong in the list for different reasons — 90 pins real scoring behaviour, 100 pins the constraint envelope. Assert `tier_for(max_score()) == "high"` rather than hard-coding 90, so a future point-value change moves the test with the table
- [ ] T011a [P] Write a factor-set test asserting **exact equality** — `set(rules.FACTORS) == {"age", "policy_type", "claims_history", "claims_ratio", "denied_claim"}` — in `apps/risk/tests/test_rules.py`. **Equality, not containment**: a subset check would let an unapproved sixth factor through, and a superset check would let an approved one be silently dropped. This is the enforcement point for FR-017, which forbids gender and location as scoring factors and forbids any non-discriminating factor. Without it FR-017 lives only in prose (spec Assumptions, research §5, the T091 docstring) and nothing fails when someone adds a `gender` band. Gender is a protected characteristic and its use in insurance risk scoring carries regulatory exposure, so this assertion must fail loudly and name FR-017 in its failure message (FR-017, FR-009 – FR-014)

### Implementation of the rule set

- [ ] T012 Create `apps/risk/rules.py` with `RULE_SET_VERSION = "1.0.0"` and the five-factor band table as **one declarative structure** serving both computation and explanation, per research §5. Each band carries its label, its bounds, and its points (FR-001, FR-003, FR-004). The factor set is pinned by T011a's equality assertion; adding or removing a factor here without amending FR-017 and T011a will fail the suite by design
- [ ] T013 Implement the pure `evaluate(customer_data) -> list[FactorResult]` function in `apps/risk/rules.py`, returning exactly five results — one per factor, each with factor name, status, observed value, band label, and points. **No ORM access in this module** (FR-001, FR-002, research §6)
- [ ] T014 Implement `tier_for(score)` and `max_score()` in `apps/risk/rules.py`, with band boundaries lower-inclusive and upper-exclusive and the top band closed (FR-005, FR-006, FR-007)

### Tests for the models ⚠️

- [ ] T015 [P] Write model tests for `RiskAssessment` field shape, the `risk_score_range` (0–100) and `risk_tier_valid` check constraints, `ordering = ["id"]`, and that `computed_at` is **explicitly set** rather than `auto_now`, in `apps/risk/tests/test_models.py` (FR-005, FR-027)
- [ ] T016 [P] Write model tests for `RiskFactor` asserting the `UniqueConstraint(assessment, factor)` and the `factor_reason_matches_status` check constraint — a `not_evaluable` row without a reason must be **rejected by the database**, and an `evaluated` row carrying one likewise, in `apps/risk/tests/test_models.py` (FR-018, FR-022, FR-023)
- [ ] T017 [P] Write a model test asserting `RiskAssessment.customer` is one-to-one, so a second assessment for the same customer is rejected — the basis of FR-033's idempotency, in `apps/risk/tests/test_models.py`

### Implementation of the models

- [ ] T018 Create the `RiskTier`, `RiskFactorName` and `FactorStatus` TextChoices plus the `RiskAssessment` model in `apps/risk/models.py`, inheriting `apps.core.models.TimeStampedModel`, with `customer` OneToOneField (`on_delete=PROTECT`, `related_name="risk_assessment"`), `score` PositiveSmallIntegerField, `tier` indexed CharField, `rule_set_version` indexed CharField, `computed_at` DateTimeField, and `computed_by` nullable FK (`on_delete=SET_NULL`) (data-model.md)
- [ ] T019 Add `RiskAssessment.Meta` in `apps/risk/models.py` with `ordering = ["id"]`, the `risk_score_range` and `risk_tier_valid` check constraints, and the `(tier, score)` index
- [ ] T020 Create the `RiskFactor` model in `apps/risk/models.py` with `assessment` FK (**`on_delete=CASCADE`** — the one deliberate cascade in this feature; a factor has no meaning apart from its assessment, see data-model.md), `factor`, `status`, `observed_value`, `band_label`, `points` (SmallIntegerField), and `unevaluable_reason`
- [ ] T021 Add `RiskFactor.Meta` in `apps/risk/models.py` with `ordering = ["id"]`, `UniqueConstraint(assessment, factor)`, the `factor_reason_matches_status` and `factor_points_non_negative` check constraints, and the `(factor, points)` index
- [ ] T022 [P] Create `RiskAssessmentFactory` and `RiskFactorFactory` in `apps/risk/factories.py` using Factory Boy, per Principle V
- [ ] T023 Generate and review the migration in `apps/risk/migrations/0001_initial.py` via `makemigrations risk`, confirming all four check constraints, the unique constraint, and both indexes are present

**Checkpoint**: The rule set is testable in isolation and the models are queryable. User stories can now begin.

---

## Phase 3: User Story 1 — Risk Manager Sees Why a Customer Scored As They Did (Priority: P1) 🎯 MVP

**Goal**: A Risk Manager can retrieve a customer's assessment and see the score,
its tier, and the specific factors that produced it — with contributions summing
exactly to the score.

**Independent Test**: Compute an assessment for a customer with known
characteristics, retrieve it, and confirm the response carries score, tier, and
one entry per factor naming the factor, the observed value, the band, and the
points — with the contributions summing to the score.

**This is the constitutional core.** Principle IV is satisfied or violated here.

### Tests for User Story 1 ⚠️

- [ ] T024 [P] [US1] Write engine tests asserting the **sum invariant** — `sum(factor.points) == assessment.score` — across every fixture combination, in `apps/risk/tests/test_engine.py` (FR-021, SC-001)
- [ ] T025 [P] [US1] Write engine tests asserting **exactly five factor rows** per assessment, including zero-contribution factors, so no factor is silently omitted, in `apps/risk/tests/test_engine.py` (FR-022, SC-002)
- [ ] T026 [P] [US1] Write engine tests for the **not-evaluable** path: a customer whose factor cannot be assessed gets a `not_evaluable` row with a stated reason and 0 points — distinct from an `evaluated` row with 0 points, in `apps/risk/tests/test_engine.py` (FR-018, FR-023)
- [ ] T027 [P] [US1] Write engine tests for **determinism**: scoring the same customer twice with unchanged data yields identical score, tier, and factor rows, in `apps/risk/tests/test_engine.py` (FR-002, SC-004)
- [ ] T028 [P] [US1] Write serializer tests for the assessment read shape — nested `factors`, `tier_label`, `factor_label`, and `rule_set_version` — asserting the explanation is readable without reference to code, in `apps/risk/tests/test_serializers.py` (FR-020, FR-025, FR-026)
- [ ] T029 [P] [US1] Write view tests for `GET /api/risk/assessments/{id}/` and `GET /api/risk/assessments/by-customer/{customer_id}/` returning score, tier and factors, in `apps/risk/tests/test_views.py` (FR-019)
- [ ] T030 [P] [US1] Write a view test asserting **no route returns a score without its factors** — including the list route, which carries `factors` by design — in `apps/risk/tests/test_views.py` (FR-019, FR-024, contracts/risk-assessment-api.md)
- [ ] T031 [P] [US1] Write a view test asserting `by-customer` for an unassessed customer returns 404 with a body distinguishable from a low score, in `apps/risk/tests/test_views.py` (FR-029)

### Implementation for User Story 1

- [ ] T032 [US1] Implement `score_customer(customer) -> AssessmentResult` in `apps/risk/engine.py`: read the customer's live policies and claims through their **default managers** (so archival exclusion falls out of the existing dual-manager design, FR-016), build the factor input, and delegate to `rules.evaluate()`. Reads only — no writes (research §6)
- [ ] T033 [US1] Implement `persist(customer, result, actor)` in `apps/risk/engine.py`: inside `transaction.atomic()` with `select_for_update()` on the customer, upsert the `RiskAssessment`, **fully replace** the factor rows, set `computed_at`, mirror `Customer.risk_score = score / 100`, and call `record_action` writing `risk.computed` with `before={"score": <prev or null>}` and `after={"score", "tier", "rule_set_version"}` — all or nothing (FR-035, FR-037, FR-048, FR-052, FR-053, FR-054). **The audit write belongs here, not in Phase 8**: FR-053 requires it share this transaction, and this is the sole write path for scores — deferring it would leave every computation between Phase 3 and Phase 8 unaudited, violating Principle II
- [ ] T034 [P] [US1] Create `RiskFactorSerializer` in `apps/risk/serializers.py` exposing factor, `factor_label`, status, `observed_value`, `band_label`, `points`, and `unevaluable_reason` (present only when not evaluable) (FR-020, FR-023)
- [ ] T035 [US1] Create `RiskAssessmentSerializer` in `apps/risk/serializers.py` with nested read-only `factors`, `client_id`, `tier_label`, `computed_by` as email, and `rule_set_version` (FR-019, FR-026, FR-027)
- [ ] T036 [US1] Create `RiskAssessmentViewSet` in `apps/risk/views.py` with list and retrieve, `queryset` using `select_related("customer", "computed_by").prefetch_related("factors")` to keep factors off the N+1 path, and pagination at 50 (FR-019)
- [ ] T037 [US1] Add the `by-customer/{customer_id}/` detail route to `apps/risk/views.py`, returning `{"detail": "This customer has not been assessed."}` on 404 **only for callers holding the read role** (FR-029, and FR-045 — the message must not become an existence oracle)
- [ ] T038 [US1] Create `apps/risk/urls.py` with a `DefaultRouter` registering the assessments viewset, mounted under `/api/risk/`
- [ ] T039 [US1] Add filters to `RiskAssessmentViewSet.get_queryset()` in `apps/risk/views.py` for `tier`, `customer`, `min_score` and `max_score`, ordered by `id` for stable paging

**Checkpoint**: An assessment can be computed in a test and retrieved with a complete, summing explanation. Principle IV is demonstrably satisfied.

---

## Phase 4: User Story 6 — Roles Are Enforced on Every Risk Operation (Priority: P1)

**Goal**: Only the five read roles may see an assessment, only the two recompute
roles may trigger one, and a refusal on a detail route discloses nothing about
existence.

**Independent Test**: Attempt every risk operation as each of the nine roles and
confirm permitted roles succeed, non-permitted roles are refused, and refusals are
byte-identical whether or not the record exists.

**Sequenced immediately after US1 deliberately**: a risk assessment is a judgment
about a person, more sensitive than the customer record it derives from. Readable
assessments without enforced roles is not a shippable increment.

### Tests for User Story 6 ⚠️

- [ ] T040 [P] [US6] Write permission tests sweeping **all nine roles** against the assessment read routes, asserting exactly Risk Manager, Underwriter, Fraud Analyst, Compliance Officer and System Administrator succeed, in `apps/risk/tests/test_permissions.py` (FR-042, SC-009)
- [ ] T041 [P] [US6] Write a permission test asserting **Customer Service may read a customer but not that customer's assessment** — the divergence that makes the fourth registry entry meaningful, in `apps/risk/tests/test_permissions.py` (research §7)
- [ ] T042 [P] [US6] Write a permission test asserting Underwriter may read but **not** recompute, and that the refused recompute changes no score, in `apps/risk/tests/test_permissions.py` (FR-043, US6 scenario 3)
- [ ] T043 [P] [US6] Write a non-disclosure test asserting an unpermitted caller's response for an **existing** and a **non-existent** assessment are identical **body included**, not merely in status, in `apps/risk/tests/test_permissions.py` (FR-045, SC-010)
- [ ] T044 [P] [US6] Write a permission test asserting unauthenticated callers are refused every risk route, in `apps/risk/tests/test_permissions.py` (FR-046)
- [ ] T045 [P] [US6] Write a permission test asserting a risk read role grants **no** write access to customer, policy or claim records, in `apps/risk/tests/test_permissions.py` (FR-047)

### Implementation for User Story 6

- [ ] T046 [US6] Define `VIEW_ROLES` (Risk Manager, Underwriter, Fraud Analyst, Compliance Officer, System Administrator) and `RECOMPUTE_ROLES` (Risk Manager, System Administrator) in `apps/risk/views.py`, with a comment recording why this is a **fourth distinct** role shape against Customer's 7, Policy's 8 and Claim's 5 (FR-042, FR-043)
- [ ] T047 [US6] Wire `get_permissions()` in `apps/risk/views.py` to return `HasRole(*RECOMPUTE_ROLES)()` for the recompute action and `HasRole(*VIEW_ROLES)()` otherwise (FR-044)
- [ ] T048 [US6] Override `get_object()` in `apps/risk/views.py` to normalise DRF's `Http404` to `NotFound()`, so a refusal 404 and a genuine-miss 404 are indistinguishable body-included — following `ClaimViewSet.get_object()` and **not** by editing the shared exception handler (FR-045, FR-041)

**Checkpoint**: US1 + US6 together are the minimum defensible increment — assessments are readable, only by the right roles, and every computation is already audited (T033). Principles II, III and IV all hold at this checkpoint.

---

## Phase 5: User Story 2 — Risk Manager Recomputes Scores Across the Book (Priority: P1)

**Goal**: A single command scores the whole customer base and reports what it did.

**Independent Test**: Run the recompute across a seeded population and confirm
every eligible customer ends with a score, a tier, and a stored assessment, with
counts of scored and skipped that account for every customer.

### Tests for User Story 2 ⚠️

- [ ] T049 [P] [US2] Write command tests asserting `computerisk` scores every eligible customer and that **`scored + skipped + failed` equals the total considered**, in `apps/risk/tests/test_computerisk.py` (FR-031, SC-006)
- [ ] T050 [P] [US2] Write a command test asserting a customer with **no live policy** is skipped with a stated reason, **no assessment row is created**, and the run continues rather than aborting (FR-018, FR-032, SC-007), in `apps/risk/tests/test_computerisk.py`
- [ ] T051 [P] [US2] Write a command test asserting **idempotency**: a second run over unchanged data produces identical scores and factor rows and creates no duplicate assessments, in `apps/risk/tests/test_computerisk.py` (FR-033, SC-004)
- [ ] T052 [P] [US2] Write a command test asserting a failure on one customer leaves already-scored customers with **complete, valid** assessments and never a score with missing factors, in `apps/risk/tests/test_computerisk.py` (FR-032, US2 scenario 6)
- [ ] T053 [P] [US2] Write a command test asserting archived customers, archived policies and archived claims are excluded from scoring, in `apps/risk/tests/test_computerisk.py` (FR-016)
- [ ] T054 [P] [US2] Write a command test asserting `--dry-run` writes **no assessment, no factor row, no mirror and no audit entry**, in `apps/risk/tests/test_computerisk.py`

### Implementation for User Story 2

- [ ] T055 [US2] Create `apps/risk/management/commands/computerisk.py` with `--customer`, `--tier`, `--dry-run` and `--limit` arguments per contracts/computerisk-command.md (FR-030)
- [ ] T056 [US2] Implement the batch loop in `apps/risk/management/commands/computerisk.py`: iterate `Customer.objects` in chunks with `select_related`/`prefetch_related` over policies and claims, calling `engine.score_customer()` then `engine.persist()`, with **each customer in its own transaction** so a failure never aborts the run (FR-032, FR-035)
- [ ] T057 [US2] Implement skip handling in `apps/risk/management/commands/computerisk.py`: a customer with no live policy is recorded as skipped **with its reason** and is not scored, and no assessment row is created (FR-018, SC-007)
- [ ] T058 [US2] Implement the counts report and tier distribution output in `apps/risk/management/commands/computerisk.py`, with exit codes 0 / 1 / 2 per the contract, and add a test over a seeded population asserting **every tier holds at least 5% of scored customers** — the only check that the rules discriminate rather than collapsing the book into one band, which per-band tests cannot catch (FR-031, SC-005)
- [ ] T059 [US2] Use `bulk_create` for factor rows in `engine.persist()` in `apps/risk/engine.py` and confirm the full-book run stays **under 60s** — a naive per-customer implementation issues ~12,000 queries (plan.md Performance Goals)

**Checkpoint**: The full 3,000-customer book can be scored in one command.

---

## Phase 6: User Story 3 — Underwriter Triggers a Fresh Assessment for One Customer (Priority: P2)

**Goal**: One customer's score can be recomputed immediately without a batch run.

**Independent Test**: Change a customer's data, trigger a recompute for that
customer alone, and confirm their score updates while no other customer's changes.

### Tests for User Story 3 ⚠️

- [ ] T060 [P] [US3] Write view tests for `POST /api/risk/assessments/recompute/` recalculating one customer from current data, in `apps/risk/tests/test_views.py` (FR-034)
- [ ] T061 [P] [US3] Write a view test asserting a single-customer recompute **modifies no other customer's** assessment, in `apps/risk/tests/test_views.py` (FR-034, US3 scenario 2)
- [ ] T062 [P] [US3] Write a view test asserting a recompute for a customer with **no prior assessment creates one** rather than failing, in `apps/risk/tests/test_views.py` (US3 scenario 5)
- [ ] T063 [P] [US3] Write a view test asserting a customer who cannot be scored returns **422** with a stated reason — distinct from a 400 validation error and from a 404, in `apps/risk/tests/test_views.py` (FR-018)

### Implementation for User Story 3

- [ ] T064 [US3] Add the `recompute` action to `RiskAssessmentViewSet` in `apps/risk/views.py`, accepting `{"customer": <id>}`, calling `engine.score_customer()` + `engine.persist(actor=request.user)`, and returning the full assessment payload (FR-034)
- [ ] T065 [US3] Implement the 422 path in the recompute action in `apps/risk/views.py` for a customer with no live policy, with the reason in the response body (FR-018)

**Checkpoint**: Both computation entry points work — batch and per-customer.

---

## Phase 7: User Story 5 — Stale Assessments Are Visibly Stale (Priority: P2)

**Goal**: A reader can tell whether an assessment reflects current data.

**Independent Test**: Compute an assessment, change scoring-relevant data without
recomputing, retrieve it, and confirm it is identifiable as possibly out of date
while still returning its stored score and factors.

**This is the phase boundary made safe.** On-demand-only computation necessarily
lets a score lag its inputs; without this story that scope decision becomes a
correctness defect.

### Tests for User Story 5 ⚠️

- [ ] T066 [P] [US5] Write staleness tests asserting a freshly computed assessment reports `is_stale: false` and carries `computed_at`, in `apps/risk/tests/test_staleness.py` (FR-027, FR-039, US5 scenario 3)
- [ ] T067 [P] [US5] Write staleness tests asserting an assessment becomes stale when the **customer**, a **live policy**, or a **live claim** is changed after computation, in `apps/risk/tests/test_staleness.py` (FR-038, FR-039, SC-012)
- [ ] T068 [P] [US5] Write a staleness test asserting a stale assessment **still returns its stored score and factors** and is **not** recalculated as a side effect of being read, in `apps/risk/tests/test_staleness.py` (FR-040)
- [ ] T069 [P] [US5] Write a staleness test documenting the accepted over-reporting: changing a field no factor reads (e.g. `phone`) still marks the assessment stale, asserting the **safe direction** rather than treating it as a bug, in `apps/risk/tests/test_staleness.py` (research §4)

### Implementation for User Story 5

- [ ] T070 [US5] Implement derived staleness in `apps/risk/serializers.py` (or a model property), comparing `computed_at` against the customer's `updated_at` and the `updated_at` of their live policies and claims. **No stored flag** — research §4 records why a flag has no honest writer in a phase that forbids automatic recomputation (FR-038, FR-039)
- [ ] T071 [US5] Add `is_stale` and conditional `stale_reason` to `RiskAssessmentSerializer` in `apps/risk/serializers.py`, and add `prefetch_related` on policies and claims to the viewset queryset in `apps/risk/views.py` so the list route does not become an N+1 (FR-039)

**Checkpoint**: A stale score is visibly stale, and 3a's scope boundary is safe.

---

## Phase 8: User Story 4 — Compliance Officer Establishes What Was Decided and When (Priority: P2)

**Goal**: Every computation is attributable, versioned, and permanently recorded.

**Independent Test**: Trigger several recomputes over time, retrieve the audit
history for that customer, and confirm each computation appears with actor, time,
and score before and after.

**Depends on US2 and US3** — auditing computations requires the computations to exist.

### Tests for User Story 4 ⚠️

- [ ] T072 [P] [US4] Write audit tests asserting every computation writes a `risk.computed` entry with actor, timestamp, **previous score** and **new score**, in `apps/risk/tests/test_audit.py` (FR-048, SC-008)
- [ ] T073 [P] [US4] Write an audit test asserting a recompute that leaves the score **unchanged is still recorded**, in `apps/risk/tests/test_audit.py` (FR-049)
- [ ] T074 [P] [US4] Write an audit test asserting a batch run writes one `risk.batch_computed` entry carrying counts in `context`, distinguishable from the per-customer entries within it, in `apps/risk/tests/test_audit.py` (FR-050)
- [ ] T075 [P] [US4] Write an audit test asserting every entry carries the **rule-set version** (FR-054), and that the assessment itself records the version that produced it (FR-026, US4 scenario 2), in `apps/risk/tests/test_audit.py`
- [ ] T076 [P] [US4] Write an audit test asserting the audit write happens **inside the same transaction** as the score — forcing the audit write to fail must leave the score uncommitted, in `apps/risk/tests/test_audit.py` (FR-053)
- [ ] T077 [P] [US4] Write an audit test asserting refused risk operations are recorded with actor and attempted action, and that risk audit entries remain **append-only** (update/delete raise), in `apps/risk/tests/test_audit.py` (FR-051, FR-052, US4 scenario 4)

### Implementation for User Story 4

- [ ] T078 [US4] Verify the `risk.computed` audit write added in T033 satisfies US4 in full: confirm it reuses the existing append-only `record_action` path with no new audit mechanism, that `before`/`after` carry previous and new score, and that `rule_set_version` is present on every entry, in `apps/risk/engine.py` (FR-048, FR-052, FR-053, FR-054)
- [ ] T079 [US4] Write the `risk.batch_computed` entry at the end of the batch run in `apps/risk/management/commands/computerisk.py`, carrying scored/skipped/failed counts and `dry_run` in `context` (FR-050)
- [ ] T080 [US4] Register the risk route in `apps/core/audit_routes.py` `register_defaults()` — prefix `/api/risk/`, target type `risk.RiskAssessment`, action prefix `risk`, the five view roles and two write roles. **This should be a single `register(...)` call and nothing else** (FR-041)
- [ ] T081 [US4] Verify FR-041/SC-009: run `git diff --stat apps/core/exception_handlers.py` and confirm **empty output** against the T005 baseline. A non-empty diff is a **finding to record**, not a line to quietly commit — the Phase 2b registry bet is what is under test
- [ ] T082 [US4] Update `apps/core/tests/test_audit_routes.py`: swap the now-registered `/api/risk/1/` example in `test_unregistered_path_matches_nothing` (line 34) for a still-unregistered prefix, keeping the assertion intact, and add assertions for the risk entry's target type and five-role view set. **This edit is predicted, not a regression** — Phase 2c made the identical swap for `/api/claims/1/`
- [ ] T083 [US4] Verify the first three registry consumers are unaffected: run `docker compose exec web pytest apps/customers/tests/test_audit.py apps/policies/tests/test_audit.py apps/claims/tests/test_audit.py -v` and confirm all pass **unmodified**

**Checkpoint**: The full audit trail exists and the registry's fourth-consumer prediction is settled either way.

---

## Phase 9: Replacing the Stored Field (FR-055 – FR-057)

**Purpose**: Make `Customer.risk_score` stop carrying uninterpreted source data.
Sequenced last among functional work because it depends on the engine being the
field's new writer.

### Tests ⚠️

- [ ] T084 [P] Write a test asserting `CustomerSerializer.risk_score` is **read-only** — an API client cannot set a score directly, since that would create a score with no assessment and no explanation, in `apps/customers/tests/test_serializers.py` (FR-056, Principle IV)
- [ ] T085 [P] Write a loader test asserting `loaddataset` **does not** write `risk_score` from the CSV, and that re-running the load leaves computed scores untouched, in `apps/customers/tests/test_loaddataset.py` (FR-057)
- [ ] T086 [P] Write a test asserting the mirror holds: `Customer.risk_score == round(assessment.score / 100, 2)` after every computation, in `apps/risk/tests/test_engine.py` (FR-055)

### Implementation

- [ ] T087 Remove the `"Risk_Score": "risk_score"` entry from `COLUMN_MAP` at `apps/customers/management/commands/loaddataset.py:81`, so a later load cannot reintroduce source scores. The CSV column stays in the file and is simply ignored, per the documented unmapped-column behavior (FR-057)
- [ ] T088 Make `risk_score` read-only in `CustomerSerializer` in `apps/customers/serializers.py`, and remove it from any write path (FR-056)
- [ ] T089 Create a data migration in `apps/customers/migrations/` setting `risk_score = NULL` for all rows, reversible as a **no-op** — the reverse cannot restore source values and must not pretend to (FR-056, SC-013)
- [ ] T090 Update the `risk_score` comment block in `apps/customers/models.py:122-126`, which currently reads "Stored only. Nothing in this feature computes, derives, or interprets these — that is Phase 3 (Risk) and Phase 5 (Fraud) work". Phase 3 has now arrived: record that the field is a **denormalised mirror** of `RiskAssessment.score`, written only by the risk engine, and that `RiskAssessment` is the record of truth

**Checkpoint**: No customer carries a source-derived risk score.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T091 [P] Add a module docstring to `apps/risk/rules.py` recording the rule table's provenance — the measured distributions in research §5, the simulated tier split (33.4/32.0/16.9/17.7%), and the boundary convention (lower-inclusive, upper-exclusive) — so the next person changing a band knows what validated the current one
- [ ] T092 [P] Add a module docstring to `apps/risk/engine.py` recording the pure-evaluation/persistence split and **why**: Phase 3b calls the same `persist()` from a Celery task, so the boundary is what makes 3b additive rather than a rewrite (research §6)
- [ ] T093 [P] Add a comment in `apps/risk/urls.py` (or `views.py`) recording why risk is mounted at `/api/risk/` rather than nested under `/api/customers/`: the nested path resolves to the **customer** registry entry, mis-auditing every risk refusal under the wrong module and role set (research §1). This is the single most likely decision for a future reader to "simplify" without knowing what it cost
- [ ] T094 Verify FR-036/SC-011 explicitly: write a test in `apps/risk/tests/test_engine.py` asserting that creating, modifying or archiving a customer, policy or claim leaves the stored score **and `computed_at`** unchanged. Confirm the codebase contains **no** signal handler, `post_save` hook, Celery task or scheduler touching risk — the absence is a requirement, not an omission
- [ ] T095 Verify FR-028 across `apps/risk/`: confirm no code path takes a business action on a score — nothing declines cover, prices a premium, opens an investigation, or notifies
- [ ] T096 Run the full suite and confirm no regression across all apps: `docker compose exec web pytest` — expect **842 + new** tests passing (T004 baseline)
- [ ] T097 Confirm coverage: `docker compose exec web pytest --cov=apps.risk --cov-report=term-missing`, requiring **100%** on `apps/risk/rules.py` and `apps/risk/engine.py` (the business-rule core Principle V names) and **≥ 95%** on `apps/risk` overall (SC-015)
- [ ] T098 Execute `specs/005-risk-scoring-engine/quickstart.md` steps 1–9 end to end, including the real double-run that verifies idempotency empirically rather than by assertion
- [ ] T099 Execute `specs/005-risk-scoring-engine/quickstart.md` step 10 (the unscoreable-customer path) — **against the test database**, or with operator confirmation if run against dev

**Note on T098/T099**: quickstart steps 5–10 write to the **dev database**.
Confirm with the operator before running them; steps 1–4 are test-only and safe.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational
- **US6 (Phase 4)**: Depends on US1 — shares `views.py`
- **US2 (Phase 5)**: Depends on Foundational + `engine.persist()` from T033
- **US3 (Phase 6)**: Depends on US1 (the viewset) and US6 (the role sets)
- **US5 (Phase 7)**: Depends on US1 (the serializer)
- **US4 (Phase 8)**: Depends on US2 and US3 — auditing computations requires computations
- **Field replacement (Phase 9)**: Depends on US2 — the engine must be the field's writer first
- **Polish (Phase 10)**: Depends on all preceding phases

### Critical Path

```
Setup → Foundational → US1 → US6 → US3 → US4 → Phase 9 → Polish
                         │      └──→ US5 ──┘
                         └──→ US2 ─────────┘
```

### Within Each User Story

- Tests MUST be written and MUST FAIL before implementation (Principle V — and here it is the constitution's own headline example)
- Rules before engine, engine before serializers, serializers before views, views before routes
- Audit writes come after the operations they record

### Parallel Opportunities

- **T006–T011** (rule-set band tests) — all [P], and the highest-value parallel block in the feature: pure functions, no database, no fixtures
- **T015–T017** (model tests) — all [P]
- **T024–T031** (US1 tests) — all [P] across three files
- **T040–T045** (US6 permission tests) — all [P] in `test_permissions.py`
- **T049–T054** (US2 command tests) — all [P] in `test_computerisk.py`
- **T066–T069** (US5 staleness tests) — all [P] in `test_staleness.py`
- **T072–T077** (US4 audit tests) — all [P] in `test_audit.py`
- **US2 (Phase 5) can run in parallel with US6/US3/US5** once Foundational and T033 land — it touches the management command, a file disjoint from the API surface

**Same-file caution**: tasks marked [P] within one test file are parallel as units
of work, but concurrent edits to the same file need coordination. The genuinely
file-disjoint parallelism is across phases: `views.py` (US1/US6/US3),
`computerisk.py` (US2), `test_staleness.py` (US5), and `test_audit.py` (US4).

---

## Parallel Example: Foundational Rule Set

```bash
# Launch all six band/tier test tasks together — pure functions, no DB:
Task: "Age band boundary tests in apps/risk/tests/test_rules.py"
Task: "Policy type + multi-policy rule tests in apps/risk/tests/test_rules.py"
Task: "Claims history three-outcome tests in apps/risk/tests/test_rules.py"
Task: "Claims ratio boundary + bounding tests in apps/risk/tests/test_rules.py"
Task: "Denied claim independence tests in apps/risk/tests/test_rules.py"
Task: "Tier threshold boundary tests in apps/risk/tests/test_rules.py"
```

---

## Implementation Strategy

### MVP First (US1 + US6)

1. Phase 1: Setup
2. Phase 2: Foundational (CRITICAL — blocks everything)
3. Phase 3: US1 — scores are explainable
4. Phase 4: US6 — and only the right roles can see them
5. **STOP and VALIDATE**: quickstart steps 1–4

US1 alone is not a safe MVP. A risk assessment is a judgment about a person,
more sensitive than the customer record it derives from, and Principle III is
non-negotiable — so the smallest defensible increment is US1 **plus** US6.

Note the MVP has no way to populate scores at scale (that is US2) — it is
demonstrable on test fixtures, which is what "independently testable" means here.

### Incremental Delivery

1. Setup + Foundational → the rule set and records exist
2. + US1 + US6 → explainable scores, RBAC enforced (**MVP**)
3. + US2 → the full 3,000-customer book is scored
4. + US3 → single-customer recompute on demand
5. + US5 → stale scores are visibly stale
6. + US4 → the full audit trail, and FR-041 becomes testable
7. + Phase 9 → the legacy field stops carrying source data
8. + Polish → SC-011 verified, coverage confirmed, decisions documented

### Parallel Team Strategy

Once Foundational and T033 are complete:

- Developer A: US1 → US6 → US3 (the API surface, `views.py`/`serializers.py`)
- Developer B: US2 (the command, `computerisk.py`) — genuinely disjoint files
- Developer C joins for US5 and US4 once A and B land

---

## Notes

- **Principle IV is satisfied or violated in Phase 3.** If any route can return a
  score without the factors that produced it, the principle fails — this is the
  first phase in the project where it applies at all (T030)
- **The sum invariant is the feature's central assertion**: `sum(points) == score`
  for every assessment, checked per-test (T024) and across the whole population
  (quickstart step 6)
- **Three factor states, not two** — contributed, contributed zero, not evaluable.
  Collapsing the last two makes "adds no risk" indistinguishable from "unknown"
  (T016, T026)
- **`/api/risk/`, not nested under customers** — the nested path is swallowed by
  the existing customer registry entry, silently mis-auditing every risk refusal
  (T093)
- **No stored staleness flag** — it would have no honest writer until Phase 3b,
  and a flag that says "fresh" forever is worse than no flag (T070)
- **`on_delete=CASCADE` on `RiskFactor` is deliberate**, against the platform's
  `PROTECT` habit: a factor has no meaning apart from its assessment (T020)
- **T082 is a predicted test edit, not a regression** — the registry test used
  `/api/risk/1/` as its unregistered example, exactly as Phase 2c inherited
  `/api/claims/1/`
- Expected coverage: **100%** on `rules.py` and `engine.py`, ≥ 95% on `apps/risk`
- Commit after each task or logical group
