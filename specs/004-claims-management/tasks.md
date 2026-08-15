---
description: "Task list for Phase 2c — Claims Management"
---

# Tasks: Phase 2c — Claims Management

**Input**: Design documents from `/specs/004-claims-management/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED. Constitution Principle V is NON-NEGOTIABLE and SC-009 requires
business-rule behavior be covered by tests that fail before the behavior exists.
Test tasks precede their implementation within every phase.

**Organization**: Tasks are grouped by user story so each can be implemented and
tested independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Include exact file paths in descriptions

## Path Conventions

Django web service, API-only. Apps live under `apps/`, tests under
`apps/<app>/tests/`. Paths below are repository-root-relative and match the
Project Structure in plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the existing `apps/claims/` placeholder app to become real.

`apps/claims/` already exists, is already in `INSTALLED_APPS`
(`config/settings/base.py:38`), and its URLs are already mounted at `/api/claims/`
(`config/urls.py:11`). This phase fills in an app rather than scaffolding one.

- [X] T001 Create the test module files that Phase 2+ will populate, as empty stubs, in `apps/claims/tests/`: `test_models.py`, `test_serializers.py`, `test_permissions.py`, `test_relationships.py`, `test_anomalies.py`, `test_audit.py` (leave the existing `test_views.py` in place until T020 replaces the placeholder route)
- [X] T002 Verify the claims baseline is green before any change: run `docker compose exec web pytest apps/claims/ -v` and record that the placeholder test currently passes, so a later failure is attributable to this feature
- [X] T003 Capture the FR-030/SC-008 baseline: record the current `git rev-parse HEAD:apps/core/exception_handlers.py` blob hash in the implementation notes, so the empty-diff check at T068 compares against a recorded value rather than a remembered one

**Checkpoint**: Test files exist, baseline recorded, no behavior changed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `Claim` model, its managers, and the migration. Every user story
reads or writes claims, so nothing can proceed until these exist.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundational ⚠️

> Write these FIRST and confirm they FAIL before implementing T007–T010.

- [X] T004 [P] Write model tests for `Claim` field shape, `ordering = ["id"]`, and `TimeStampedModel` inheritance in `apps/claims/tests/test_models.py` (FR-001, FR-005, FR-017)
- [X] T005 [P] Write model tests asserting `ClaimStatus.choices` is exactly `["Approved", "Denied", "Filed"]` and that `No Claim` is unrepresentable, in `apps/claims/tests/test_models.py` (FR-004, FR-012)
- [X] T006 [P] Write model tests for both DB check constraints — `claim_amount_non_negative` (accepting `0.00`, rejecting negative) and `claim_status_valid` (rejecting a raw-ORM `No Claim` write) — in `apps/claims/tests/test_models.py` (FR-011, FR-010)

### Implementation for Foundational

- [X] T007 Create the `ClaimStatus` TextChoices with exactly three values and the `Claim` model in `apps/claims/models.py`, inheriting `apps.core.models.TimeStampedModel`, with `policy` FK (`on_delete=PROTECT`, `related_name="claims"`, indexed), `claim_status` CharField(16), `claim_amount_usd` DecimalField(10,2) non-nullable, and `archived_at` nullable (FR-001, FR-002, FR-005, FR-006, FR-021)
- [X] T008 Add `Claim.Meta` in `apps/claims/models.py` with `ordering = ["id"]`, the `claim_amount_non_negative` (`gte=0`, NOT `gt=0`) and `claim_status_valid` check constraints, and the `["policy", "claim_status"]` composite index — and add NO `UniqueConstraint` or `unique_together` (FR-007, FR-010, FR-011, FR-017)
- [X] T009 Add the dual managers to `Claim` in `apps/claims/models.py`: `objects = ClaimManager()` declared FIRST so it stays `_default_manager`, filtering `archived_at__isnull=True`, and `all_objects = models.Manager()`, mirroring `apps/policies/models.py:32` (FR-021, FR-028)
- [X] T010 [P] Create `ClaimFactory` in `apps/claims/factories.py` using Factory Boy, per Principle V
- [X] T011 Generate and review the migration in `apps/claims/migrations/0001_initial.py` via `makemigrations claims`, confirming both check constraints and the composite index are present and that no unique constraint was emitted

**Checkpoint**: `Claim` exists and is queryable. User stories can now begin.

---

## Phase 3: User Story 1 — Claims Adjuster Reviews Claims Against a Policy (Priority: P1) 🎯 MVP

**Goal**: A Claims Adjuster can list claims filtered to one policy or status, and
retrieve a single claim showing its policy's coverage type, in one request.

**Independent Test**: Seed a policy with claims, request the claim list filtered
to that policy as a Claims Adjuster, and confirm exactly that policy's claims are
returned, each with status and amount.

### Tests for User Story 1 ⚠️

- [X] T012 [P] [US1] Write serializer tests for the read shape — embedded policy summary carrying `policy_type` and nested customer — in `apps/claims/tests/test_serializers.py` (FR-023, SC-001)
- [X] T013 [P] [US1] Write view tests for `GET /api/claims/` list, pagination at 50, and stable `id` ordering across pages with no omission or repetition, in `apps/claims/tests/test_views.py` (FR-017, SC-010)
- [X] T014 [P] [US1] Write view tests for the `policy` and `claim_status` query filters in `apps/claims/tests/test_views.py` (FR-018, FR-019)
- [X] T015 [P] [US1] Write view tests for `GET /api/claims/{id}/` retrieval, and for archived claims returning 404 from both list and detail, in `apps/claims/tests/test_views.py` (FR-016, FR-021)
- [X] T016 [P] [US1] Write a relationship test asserting a live claim against an **archived** policy still appears in list and detail — the reverse of the instinct to hide it — in `apps/claims/tests/test_relationships.py` (FR-008)

### Implementation for User Story 1

- [X] T017 [US1] Create `ClaimSerializer` in `apps/claims/serializers.py` as the single definition of claim validity, with the nested read-only policy summary (id, policy_type, nested customer) (FR-023)
- [X] T018 [US1] Implement the claims ViewSet list and retrieve actions in `apps/claims/views.py`, replacing `PlaceholderView`, with `select_related("policy", "policy__customer")` to avoid N+1 across a 50-record page (FR-016, FR-017)
- [X] T019 [US1] Add `policy` and `claim_status` filtering to the list action in `apps/claims/views.py` (FR-018, FR-019)
- [X] T020 [US1] Replace the placeholder route with the router registration in `apps/claims/urls.py`, removing `/api/claims/placeholder/` (FR-049)

**Checkpoint**: US1 is fully functional — claims are readable, filterable, and paged.

---

## Phase 4: User Story 5 — Roles Are Enforced on Every Claim Operation (Priority: P1)

**Goal**: Read is permitted to exactly five roles, write to exactly two, and a
caller who may not read a claim cannot tell whether it exists.

**Independent Test**: Attempt each claim operation once per role across all nine
roles and confirm the permitted set is allowed and every other role is refused,
with the refusal recorded.

**Note on ordering**: US5 is sequenced before US3 (both P1 vs P2) because RBAC is
NON-NEGOTIABLE per Principle III, and because the write role sets it establishes
are the ones US3's write routes must enforce.

### Tests for User Story 5 ⚠️

- [X] T021 [P] [US5] Write a full nine-role read permission matrix test — 200 for Claims Adjuster, Fraud Analyst, Compliance Officer, Risk Manager, Sys Admin; 403 for Customer Service, Underwriter, Product Manager, Executive Leadership — in `apps/claims/tests/test_permissions.py` (FR-026, SC-005)
- [X] T022 [P] [US5] Write a full nine-role write permission matrix test confirming write is Claims Adjuster + Sys Admin only, and that read-permitted-but-write-refused roles (notably Fraud Analyst) are refused and store nothing, in `apps/claims/tests/test_permissions.py` (FR-027, SC-005)
- [X] T023 [P] [US5] Write tests that unauthenticated callers are refused on every claim route in `apps/claims/tests/test_permissions.py` (FR-025)
- [X] T024 [P] [US5] Write non-disclosure tests: a read-refused role gets an identical 404 for an existing claim and a nonexistent id on detail routes, and collection routes return 403, in `apps/claims/tests/test_permissions.py` (FR-028, SC-006)
- [X] T025 [P] [US5] Write a test that a **permitted** user's 404 on a missing claim is NOT recorded as a refusal, in `apps/claims/tests/test_permissions.py` (FR-032)

### Implementation for User Story 5

- [X] T026 [US5] Define the claim `VIEW_ROLES` (five) and `WRITE_ROLES` (two) and apply `HasRole` to every route in `apps/claims/views.py` — deliberately NOT inheriting the Phase 1 placeholder's three-role set (FR-025, FR-026, FR-027)
- [X] T027 [US5] Ensure detail routes return 404 rather than 403 for refused callers so refusal is indistinguishable from nonexistence, in `apps/claims/views.py` (FR-028)

**Checkpoint**: RBAC is enforced and verified across all nine roles.

---

## Phase 5: User Story 2 — Administrator Seeds Claims From the Source Dataset (Priority: P1)

**Goal**: One `loaddataset` run produces customers, policies, and claims from the
same file, retains the 390 self-contradicting rows as queryable anomalies, and is
safe to re-run.

**Independent Test**: Run the load, confirm claims exist tied to the correct
policies, run it again, and confirm the claim and anomaly counts are unchanged.

**Note**: This story carries the `ClaimLoadAnomaly` model because the loader is
the only writer of anomalies (per the anomalies contract).

### Tests for User Story 2 ⚠️

- [X] T028 [P] [US2] Write `ClaimLoadAnomaly` model tests — field shape, `policy` uniqueness as the idempotency key, `source_status` accepting the free-text `"No Claim"` the `Claim` model refuses, and the `["status", "cleared_reason"]` index — in `apps/claims/tests/test_models.py` (FR-042, FR-043)
- [X] T029 [P] [US2] Write loader tests for the `No Claim` branch taken **before** `ClaimSerializer` is constructed: zero amount → `skipped`, non-zero amount → `anomaly`, neither creating a claim nor refusing the row, in `apps/claims/tests/test_anomalies.py` (FR-004, FR-041, FR-045)
- [X] T030 [P] [US2] Write loader tests for claim reconciliation matching on `policy` among live rows only, so a re-run updates rather than duplicates, in `apps/claims/tests/test_anomalies.py` (FR-035, SC-003)
- [X] T031 [P] [US2] Write a loader test that a file omitting the claim columns fails in `_read_rows()` before the row loop, leaving no customer or policy written, in `apps/claims/tests/test_anomalies.py` (FR-037)
- [X] T032 [P] [US2] Write a loader test that a row with invalid claim data is refused in full — no customer, no policy, no claim persists — and the run continues, in `apps/claims/tests/test_anomalies.py` (FR-038)
- [X] T033 [P] [US2] Write the anomaly lifecycle tests — raise, clear-as-corrected, clear-as-absent, and re-raise resetting `cleared_reason`/`cleared_at` to null — in `apps/claims/tests/test_anomalies.py` (FR-044, FR-044a, FR-044b)
- [X] T034 [P] [US2] Write an idempotency test running the load three times over an unchanged file and asserting the anomaly count after run three equals the count after run one, in `apps/claims/tests/test_anomalies.py` (FR-043, SC-012)
- [X] T035 [P] [US2] Write `--dry-run` tests asserting the claim and anomaly counts (including the clearing breakdown) are reported while nothing is written — no claim, no anomaly, no clearing, no audit entry, in `apps/claims/tests/test_anomalies.py` (FR-040, FR-046)

### Implementation for User Story 2

- [X] T036 [US2] Create the `ClaimLoadAnomaly` model in `apps/claims/models.py` with `policy` FK (`PROTECT`, `related_name="claim_load_anomalies"`, `unique=True`), `source_status`/`source_amount_usd` as unconstrained quotations of the source, `status`, nullable `cleared_reason`/`cleared_at`, `first_observed_at`, `last_observed_at`, `source_file`, and the composite index — with NO `cleared_count` or history JSON field (FR-042, FR-043, FR-044)
- [X] T037 [US2] Extend the migration in `apps/claims/migrations/0001_initial.py` to include `ClaimLoadAnomaly` (regenerate if T011 already ran)
- [X] T038 [US2] Add `CLAIM_COLUMN_MAP` and fold it into `REQUIRED_COLUMNS` in `apps/customers/management/commands/loaddataset.py`, and update the stale comment at `loaddataset.py:75` to name the remaining unconsumed columns (`Last_Interaction`, `Client_Feedback`) (FR-037)
- [X] T039 [US2] Implement per-row claim handling in `apps/customers/management/commands/loaddataset.py`: branch on `No Claim` **before** constructing `ClaimSerializer`, validate real claims through the same `ClaimSerializer` the API uses, and reconcile on `policy` among live rows — all inside the existing per-row transaction (FR-035, FR-038, FR-004)
- [X] T040 [US2] Implement anomaly recording in `apps/customers/management/commands/loaddataset.py` using `update_or_create` on `policy`, tracking the `policies_seen` and `policies_conflicting` sets, with the three cases: new → insert + audit `claim_anomaly.recorded`; existing open → refresh observation fields with **no** new audit entry; existing cleared → re-raise + audit `claim_anomaly.reraised` (FR-041, FR-043, FR-044b)
- [X] T041 [US2] Implement anomaly clearing in `apps/customers/management/commands/loaddataset.py` **after the row loop in its own transaction**, deciding the reason by whether the policy was in `policies_seen` — in → `corrected`, not in → `absent` — since "not seen this run" cannot be known until the run ends (FR-044, FR-044a)
- [X] T042 [US2] Implement the extended output format in `apps/customers/management/commands/loaddataset.py`: claims on one line with `created`/`updated`/`refused`/`skipped`, anomalies on their **own** line with the clearing breakdown always split by reason even at zero (FR-036, FR-045)
- [X] T043 [US2] Extend `--dry-run` in `apps/customers/management/commands/loaddataset.py` to compute both sets and the clearing decision and report them without persisting anything (FR-040, FR-046)

**Checkpoint**: The dataset loads end to end and is safe to re-run.

---

## Phase 6: User Story 3 — Claims Adjuster Records and Corrects a Claim (Priority: P2)

**Goal**: A Claims Adjuster can create, amend, and reversibly remove a claim, with
every validation refusal naming the offending field.

**Independent Test**: Create a claim against a live policy, retrieve it, amend its
status, and confirm the change is reflected and the original is recoverable from
the audit trail.

### Tests for User Story 3 ⚠️

- [X] T044 [P] [US3] Write serializer validation tests for each refusal in the contract's 400 table — status not in choices, `No Claim` specifically, negative amount, nonexistent policy, archived policy, omitted policy — each naming the offending field, in `apps/claims/tests/test_serializers.py` (FR-010 through FR-015)
- [X] T045 [P] [US3] Write a serializer test that the `No Claim` refusal message explains the absence of a claim is represented by the absence of a record, rather than only "not a valid choice", in `apps/claims/tests/test_serializers.py` (FR-012)
- [X] T046 [P] [US3] Write serializer tests that `"0.00"` is accepted and remains distinguishable from an omitted amount (which is a 400), in `apps/claims/tests/test_serializers.py` (FR-011)
- [X] T047 [P] [US3] Write view tests for `POST`, `PATCH`, and `DELETE`, including that `DELETE` sets `archived_at` rather than deleting the row and that the claim remains in `all_objects`, in `apps/claims/tests/test_views.py` (FR-020, FR-021)
- [X] T048 [P] [US3] Write tests that `policy` is read-only on `PATCH` — supplying it is ignored rather than erroring — and that no status transition is enforced (`Approved → Filed` is permitted), in `apps/claims/tests/test_views.py` (FR-022, FR-024)
- [X] T049 [P] [US3] Write a relationship test that hard-deleting a policy carrying claims is prevented by `PROTECT`, in `apps/claims/tests/test_relationships.py` (FR-009, SC-007)

### Implementation for User Story 3

- [X] T050 [US3] Add write validation to `ClaimSerializer` in `apps/claims/serializers.py`, including the `ArchivedAwarePrimaryKeyRelatedField` pattern (mirroring `apps/policies/serializers.py:31`) resolving through `Policy.all_objects` so an archived policy is reported as *archived* rather than *nonexistent* (FR-013, FR-014)
- [X] T051 [US3] Override the `No Claim` choice-field error message in `apps/claims/serializers.py` to explain the absence-of-a-record rule (FR-012)
- [X] T052 [US3] Implement `create`, `partial_update`, and `destroy` (archival via `archived_at`) in `apps/claims/views.py`, with `policy` read-only after creation (FR-020, FR-021, FR-022)

**Checkpoint**: Full CRUD works and every refusal names its field.

---

## Phase 7: User Story 4 — Compliance Officer Traces a Claim's History (Priority: P2)

**Goal**: Every claim create, amend, remove, and refused access attempt is
recorded with actor, action, time, and before/after values — and the registry
addition requires no handler change.

**Independent Test**: Perform a create, an amendment, a removal, and a refused
access attempt, then read the audit trail as a Compliance Officer and confirm all
four are present.

### Tests for User Story 4 ⚠️

- [X] T053 [P] [US4] Write audit tests for `claim.created`, `claim.updated`, and `claim.deleted` recording actor, action, time, and affected values, in `apps/claims/tests/test_audit.py` (FR-029, SC-004)
- [X] T054 [P] [US4] Write an audit test that an amendment records only fields that actually changed, and that a PATCH setting a status to the value it already has writes an empty diff rather than a fabricated one, in `apps/claims/tests/test_audit.py` (FR-033)
- [X] T055 [P] [US4] Write audit tests that every refused claim access writes an entry with `outcome="refused"` without altering the response the caller receives, in `apps/claims/tests/test_audit.py` (FR-031)
- [X] T056 [P] [US4] Write audit tests that loader-written claim and anomaly entries are attributed to the system (`actor=None`) rather than a person, in `apps/claims/tests/test_audit.py` (FR-039, FR-048)
- [X] T057 [P] [US4] Write audit tests for the two distinct clearing actions `claim_anomaly.cleared_corrected` and `claim_anomaly.cleared_absent` as separate indexed action names, and that a cleared → re-raised → cleared anomaly's full history is recoverable from the trail by `(target_type, target_id)`, in `apps/claims/tests/test_audit.py` (FR-048a, SC-013)
- [X] T058 [P] [US4] Write a test that audit entries cannot be altered or removed after the fact, in `apps/claims/tests/test_audit.py` (FR-034)

### Implementation for User Story 4

- [X] T059 [US4] Add the claims audit writes to `apps/claims/views.py` using the existing `record_action`, inside the same transaction as each write, computing `before_diff`/`after_diff` the way `apps/policies/views.py:154` does (FR-029, FR-033, FR-034)
- [X] T060 [US4] Add the single `register(AuditedRoute(prefix="/api/claims/", target_type="claims.Claim", action_prefix="claim", view_roles=..., write_roles=...))` call to `register_defaults()` in `apps/core/audit_routes.py`, using the **claim** role sets and adding no second entry for the nested anomaly routes (FR-030)
- [X] T061 [US4] Add the loader's anomaly audit writes (`claim_anomaly.recorded`, `.reraised`, `.cleared_corrected`, `.cleared_absent`) with `actor=None` and `context={"source": "loaddataset", "file": path}` in `apps/customers/management/commands/loaddataset.py` (FR-048, FR-048a)

**Checkpoint**: The full audit trail is in place and the registry prediction is testable.

---

## Phase 8: Anomalies Read API

**Purpose**: Expose the retained anomalies as the queryable signal FR-041 requires.
Serves US2's retention and inherits US5's read role set; sequenced after both.

### Tests ⚠️

- [X] T062 [P] Write view tests for `GET /api/claims/anomalies/` list and detail, pagination at 50, and `id` ordering, in `apps/claims/tests/test_views.py`
- [X] T063 [P] Write tests for the `policy`, `status`, and `cleared_reason` filters — specifically that `?status=cleared&cleared_reason=corrected` excludes every absent-cleared anomaly, in `apps/claims/tests/test_views.py` (FR-044a, SC-013)
- [X] T064 [P] Write permission tests that the anomaly routes enforce exactly the claim read set with no write set, in `apps/claims/tests/test_permissions.py` (FR-047)

### Implementation

- [X] T065 Create `ClaimLoadAnomalySerializer` in `apps/claims/serializers.py` with the nested policy summary and `cleared_reason` null while open
- [X] T066 Implement the read-only anomalies ViewSet with its three filters in `apps/claims/views.py`, exposing no create, update, or destroy action
- [X] T067 Register the nested anomalies route under `/api/claims/anomalies/` in `apps/claims/urls.py`

**Checkpoint**: The 390 anomalies are queryable by policy and by clearing reason.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T068 Verify FR-030/SC-008: run `git diff --stat apps/core/exception_handlers.py` and confirm **empty output** against the T003 baseline. A non-empty diff is a **finding to record**, not a line to quietly commit
- [X] T069 Verify the first two registry consumers are unaffected: run `docker compose exec web pytest apps/customers/tests/test_audit.py apps/policies/tests/test_audit.py -v` and confirm all pass **unmodified** (SC-008)
- [X] T070 [P] Add the single-claim-per-export reconciliation limitation to the loader docstring in `apps/customers/management/commands/loaddataset.py`, so it lives in the code rather than tribal memory (research §2)
- [X] T071 Confirm the placeholder is fully gone: no `PlaceholderView` in `apps/claims/views.py`, no `/api/claims/placeholder/` route, and `apps/claims/tests/test_views.py` asserts the real routes instead (FR-049)
- [X] T072 Run the full suite and confirm no regression across all apps: `docker compose exec web pytest`
- [X] T073 Confirm `apps/claims` coverage is **≥ 95%**: `docker compose exec web pytest --cov=apps.claims --cov-report=term-missing` (SC-009)
- [X] T074 Execute the quickstart.md validation steps 1–8 end to end, including the dataset load and the anomaly clearing scenarios

**Note on T074**: quickstart steps 4–7 write to the **dev database**. Confirm with
the operator before running them; steps 1–3 and 8 are test-only and safe.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational
- **US5 (Phase 4)**: Depends on Foundational; shares `views.py` with US1
- **US2 (Phase 5)**: Depends on Foundational; needs `ClaimSerializer` from T017
- **US3 (Phase 6)**: Depends on Foundational; extends US1's serializer and views
- **US4 (Phase 7)**: Depends on US3 — auditing writes requires the writes to exist
- **Anomalies API (Phase 8)**: Depends on US2 (the model) and US5 (the role sets)
- **Polish (Phase 9)**: Depends on all preceding phases

### Critical Path

```
Setup → Foundational → US1 → US5 → US3 → US4 → Polish
                         └──→ US2 ─────────→ Anomalies API ──┘
```

### Within Each User Story

- Tests MUST be written and MUST FAIL before implementation (Principle V)
- Models before serializers, serializers before views, views before routes
- Audit writes come after the operations they record

### Parallel Opportunities

- T004–T006 (foundational model tests) — all [P], same-file coordination needed on `test_models.py`
- T012–T016 (US1 tests) — all [P] across four files
- T021–T025 (US5 permission tests) — all [P] in `test_permissions.py`
- T028–T035 (US2 loader/anomaly tests) — all [P], mostly in `test_anomalies.py`
- T044–T049 (US3 validation tests) — all [P]
- T053–T058 (US4 audit tests) — all [P] in `test_audit.py`
- **US2 (Phase 5) can run fully in parallel with US1/US5/US3** once Foundational and T017 are done — it touches the loader, a different file from the API surface

**Same-file caution**: tasks marked [P] within one test file are parallel in the
sense of being independent units of work, but concurrent edits to the same file
need coordination. The genuinely file-disjoint parallelism is across phases:
`views.py` (US1/US5/US3), `loaddataset.py` (US2), and `test_audit.py` (US4).

---

## Parallel Example: User Story 1

```bash
# Launch the US1 tests together — four distinct files:
Task: "Serializer read-shape tests in apps/claims/tests/test_serializers.py"
Task: "List/pagination tests in apps/claims/tests/test_views.py"
Task: "Filter tests in apps/claims/tests/test_views.py"
Task: "Archived-policy visibility test in apps/claims/tests/test_relationships.py"
```

---

## Implementation Strategy

### MVP First (US1 + US5)

1. Phase 1: Setup
2. Phase 2: Foundational (CRITICAL — blocks everything)
3. Phase 3: US1 — claims are readable
4. Phase 4: US5 — and only by the right roles
5. **STOP and VALIDATE**: quickstart steps 1–3

US1 alone is not a safe MVP for this feature. Claim data is financially and
legally sensitive, and Principle III is non-negotiable, so the smallest
defensible increment is US1 **plus** US5 — readable claims with enforced roles.

### Incremental Delivery

1. Setup + Foundational → the `Claim` record exists
2. + US1 + US5 → claims readable, RBAC enforced (**MVP**)
3. + US2 → 2,246 claims and 390 anomalies seeded from the dataset
4. + US3 → adjusters can record and correct claims
5. + US4 → the full audit trail, and FR-030 becomes testable
6. + Anomalies API → the retained signal is queryable
7. + Polish → SC-008 verified, coverage confirmed, placeholder gone

### Parallel Team Strategy

Once Foundational and T017 are complete:

- Developer A: US1 → US5 → US3 (the API surface, `views.py`/`serializers.py`)
- Developer B: US2 (the loader, `loaddataset.py`) — genuinely disjoint files
- Developer C joins for US4 and the Anomalies API once A and B land

---

## Notes

- **`gte=0`, not `gt=0`** — 1,507 of 3,000 rows carry exactly `0.00`. A
  positive-only constraint would refuse half the dataset (T008)
- **Three status choices, not four** — `No Claim` is unrepresentable by
  construction; this is the feature's most consequential modeling decision (T007)
- **Branch on `No Claim` before the serializer** — getting this backwards would
  refuse 754 valid rows (T039)
- **Clearing runs after the row loop, in its own transaction** — "not seen this
  run" is a whole-file conclusion a per-row transaction cannot express (T041)
- **The counts must sum**: `2,246 + 364 + 390 = 3,000`
- Expected coverage target: ≥ 95% on `apps/claims`
- Commit after each task or logical group
