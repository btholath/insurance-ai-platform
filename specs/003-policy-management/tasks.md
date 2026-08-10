---

description: "Task list for Phase 2b — Policy Management"
---

# Tasks: Phase 2b — Policy Management

**Input**: Design documents from `/specs/003-policy-management/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **REQUIRED, not optional.** Constitution Principle V is non-negotiable for business-rule code, and SC-010 requires validation, relationship, permission, and audit tests written *before* the implementation they cover, at ≥95% measured coverage. Test tasks are ordered before their implementation and must be observed failing first.

**Organization**: Grouped by user story. See "Story independence — the same caveat as Phase 2a" below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5, mapping to spec.md user stories
- All paths are repo-relative from `/home/bijut/insurance-ai-platform/`

## Path Conventions

Single Django project, per-domain apps under `apps/`. `apps.policies` is already in `INSTALLED_APPS` and `config/urls.py` already routes `/api/policies/`, so this feature fills an existing app shell.

---

## Story independence — the same caveat as Phase 2a

US1 (read), US2 (load), and US3 (write) are genuinely independent phases. US5 (RBAC) and US4 (audit) are **properties of the endpoints US1 and US3 build**, not separate features:

- **US5** is applied inline as each route is written (T041, T053). Phase 8 proves the full matrix rather than introducing enforcement — deferring it would ship an interval where premium and coverage terms are unprotected.
- **US4** must be written **inside the same transaction** as each write (FR-033), so it cannot be bolted on afterward. Phase 9 verifies the trail; the refusal mechanism it depends on is built far earlier, in Phase 4.

**This feature adds a sixth grouping the template has no slot for**: the cross-entity archival guarantees (FR-008, FR-022, SC-008) belong to no single story — they are the contract between Customer and Policy. They get their own phase (Phase 10) rather than being scattered.

---

## Phase 1: Setup

- [X] T001 Create `apps/policies/migrations/__init__.py` (the app has no migrations package yet)
- [X] T002 [P] Verify baseline is green before any change: `docker compose exec web pytest` and record the passing count (expected: 389)
- [X] T003 [P] Record the current customer audit test count in `apps/customers/tests/test_audit.py` (expected: 22) — this is the regression suite for the Phase 4 handler refactor, and the number must not change

---

## Phase 2: Foundational — the Policy entity

**Purpose**: The `Policy` model and its factory. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase completes.

### Tests First (Principle V)

- [X] T004 [P] Write field and constraint tests in `apps/policies/tests/test_models.py`: all fields per data-model.md, `end_date > start_date` enforced by `CheckConstraint`, `premium_usd > 0` enforced, and `renewal_probability` range accepting **NULL** (the SQL three-valued-logic trap — a policy with no renewal probability must insert cleanly, or every API-created policy becomes impossible)
- [X] T005 [P] Write manager tests in `apps/policies/tests/test_models.py`: `Policy.objects` excludes archived rows, `Policy.all_objects` includes them, and `objects` is `_default_manager` (which is what keeps archived policies out of `customer.policies` traversal)
- [X] T006 Write live-scoped uniqueness tests in `apps/policies/tests/test_models.py`: a customer cannot hold two **live** policies of the same type; archiving one **releases the slot** so a new policy of that type succeeds. This is deliberately the opposite of Customer, where an archived `client_id` stays reserved forever — a constraint spanning archived rows would make a coverage type permanently unusable after one archival
- [X] T007 [P] Write FK behaviour tests in `apps/policies/tests/test_models.py`: `on_delete=PROTECT` refuses a hard customer delete that would destroy policies, and `related_name="policies"` resolves

### Implementation

- [X] T008 Create `Policy` model in `apps/policies/models.py` per data-model.md: 9 fields, `TimeStampedModel` base, FK to `Customer` with `PROTECT` and `related_name="policies"`
- [X] T009 Add the three `CheckConstraint`s to `apps/policies/models.py` — date ordering, positive premium, and renewal-probability range **with the `isnull` disjunction**
- [X] T010 Add `UniqueConstraint(["customer", "policy_type"], condition=Q(archived_at__isnull=True))` to `apps/policies/models.py`, plus indexes on `policy_type`, `end_date`, and `(customer, policy_type)`
- [X] T011 Add `PolicyManager` and dual managers to `apps/policies/models.py` — `objects` declared **first** so it stays `_default_manager`, `all_objects = models.Manager()` second
- [X] T012 Generate migration `apps/policies/migrations/0001_initial.py` via `makemigrations policies`; confirm with `sqlmigrate` that the partial unique index carries its `WHERE archived_at IS NULL` clause and that the renewal-probability CHECK contains `IS NULL OR`
- [X] T013 [P] Create `PolicyFactory` in `apps/policies/factories.py` per data-model.md, with `archived`, `expired`, and `scored` traits. Defaults must produce a **currently-in-force** policy (start past, end future) — without an explicit `expired` trait the FR-020 filter would pass vacuously

**Checkpoint**: `pytest apps/policies/tests/test_models.py` green.

---

## Phase 3: Foundational — Validation Layer

**Purpose**: The serializer, the **single definition of validity** shared by the API and the loader (FR-043).

### Tests First

- [X] T014 [P] Write validation tests in `apps/policies/tests/test_serializers.py` for FR-009 (unrecognized `policy_type`), FR-011 (zero and negative premium), FR-012 (renewal probability outside 0–1) — each asserting the **offending field is named** (FR-015)
- [X] T015 [P] Write date-coherence tests in `apps/policies/tests/test_serializers.py`: `end_date` equal to and before `start_date` are both refused, the error names **both dates** (FR-010), and a PATCH changing only `end_date` still checks against the stored `start_date`
- [X] T016 [P] Write customer-resolution tests in `apps/policies/tests/test_serializers.py`: a nonexistent customer is refused naming `customer` (FR-013); an **archived** customer is refused naming `customer` with a message distinguishing "archived" from "does not exist" (FR-014) — resolving through `Customer.objects` instead of `all_objects` would produce the misleading second message and send an underwriter hunting for a record that was deliberately removed
- [X] T017 [P] Write absent-vs-zero tests in `apps/policies/tests/test_serializers.py`: a policy created without a renewal probability has `renewal_probability is None` (asserted with `is None`, never truthiness), and `0.00` is distinguishable from absent. **13 rows in the source dataset carry a genuine `0.0`** — a truthiness check silently reclassifies all 13 as "not recorded"
- [X] T018 [P] Write boundary-acceptance tests in `apps/policies/tests/test_serializers.py`: premium `0.01`, renewal probability `0.00` and `1.00`, and `end_date` exactly one day after `start_date` are all accepted (SC-007)

### Implementation

- [X] T019 Create `PolicySerializer` in `apps/policies/serializers.py` — read + create + loader shape, `customer` as a `PrimaryKeyRelatedField` over `Customer.all_objects` with an explicit archived check layered on top
- [X] T020 Add cross-field date validation to `apps/policies/serializers.py` in `validate()` rather than a field validator — that is what lets the FR-010 error name both dates
- [X] T021 Add the embedded customer summary (`id`, `client_id`, `name`) to the read shape in `apps/policies/serializers.py`, so US1 needs no second request per row
- [X] T022 Create `PolicyUpdateSerializer` in `apps/policies/serializers.py` — all fields optional for PATCH, same rules

**Checkpoint**: `pytest apps/policies/tests/test_serializers.py` green. Validation defined once, ready to share with the loader.

---

## Phase 4: Generalize the refusal handler 🔴 HIGHEST RISK

**Purpose**: Turn the customer-specific refusal handler into a registry, so FR-031/FR-032 work for policies and Claims inherits it as configuration.

**⚠️ This phase modifies shipped, tested Phase 2a code.** It is sequenced here — before any policy route exists — so the change is purely behavior-preserving and verified solely by the existing customer suite. Doing it after policy routes emit refusals would tangle "did the refactor break customers?" with "is the new policy behaviour right?"

**The acceptance bar**: the 22 tests in `apps/customers/tests/test_audit.py` must pass **completely unmodified**. If any needs editing to accommodate the refactor, the refactor changed customer behaviour and is wrong — revert and rethink, do not adjust the test.

- [X] T023 Create `apps/core/audit_routes.py` with the `AuditedRoute` namedtuple (`prefix`, `target_type`, `action_prefix`, `view_roles`, `write_roles`) and a registry populated at app-ready rather than import time
- [X] T024 Register the customers entry in `apps/core/audit_routes.py` with **exactly** the values the shipped handler hardcodes: prefix `/api/customers/`, target type `customers.Customer`, action prefix `customer`, and the existing 7 view / 2 write roles
- [X] T025 Refactor `apps/core/exception_handlers.py` to look the request up in the registry instead of `_is_customer_route()`, deriving `target_type`, action names, and role sets from the matched entry
- [X] T026 Run `pytest apps/customers/tests/test_audit.py` and confirm **22 passed with zero test-file edits** — the gate for this phase
- [X] T027 Run the full suite (`pytest`) and confirm 389 passing, unchanged from the T002 baseline
- [X] T028 [P] Write registry tests in `apps/core/tests/test_audit_routes.py`: an unregistered path produces no audit entry, and a registered prefix resolves to the right target type and role set
- [X] T029 Register the policies entry in `apps/core/audit_routes.py`: prefix `/api/policies/`, target type `policies.Policy`, action prefix `policy`, **8 view roles** (everyone but Executive Leadership) and **Underwriter + Sys Admin** as write roles. The role sets differ per module and that difference is load-bearing — a Product Manager hitting a missing policy is an ordinary miss, while the same user hitting a missing customer is a refusal

**Checkpoint**: customer refusal behaviour unchanged; the mechanism now serves any registered module.

---

## Phase 5: User Story 2 — Seed Policies From the Dataset (Priority: P1) 🎯 MVP

**Goal**: Load customers and their policies together, idempotently, in one command.

**Independent Test**: Run the load, confirm 3,000 policies each attached to a distinct customer; re-run unchanged and confirm both counts identical with no duplicates.

**Why this is the MVP**: a policy API over an empty database demonstrates nothing. The loader delivers a populated book of business — demonstrable alone, and the precondition for verifying US1 at realistic volume.

### Tests First

- [X] T030 [P] [US2] Write happy-path loader tests in `apps/customers/tests/test_loaddataset.py` using a small fixture CSV: correct policy count, correct field mapping per the contract's column table, and every policy attached to the customer named on its row (FR-037)
- [X] T031 [P] [US2] Write policy idempotency tests in `apps/customers/tests/test_loaddataset.py`: a second run leaves the policy count identical, reports all-updated, and creates no duplicate `(customer, policy_type)` pairs (FR-038, SC-002); a changed source row updates in place (FR-040)
- [X] T032 [US2] Write the **match-key** test in `apps/customers/tests/test_loaddataset.py`: a customer holding two policies of different types reconciles as two distinct policies across re-runs. Matching on customer alone would overwrite one with the other on every run — silently, and only for customers this export cannot produce (FR-039)
- [X] T033 [US2] Write the **archived-customer reconciliation** test in `apps/customers/tests/test_loaddataset.py`: archive a loaded customer, re-run the load, and confirm the policy reconciles against the existing archived customer rather than creating a duplicate customer or an unattached policy (FR-041)
- [X] T034 [US2] Write **row-atomicity** tests in `apps/customers/tests/test_loaddataset.py`: a row whose policy fails validation leaves **neither** a customer nor a policy behind, and is reported as refused with its row number and field (FR-045). A half-landed row is the state an operator cannot reason about
- [X] T035 [P] [US2] Write archived-policy tests in `apps/customers/tests/test_loaddataset.py`: a load after a policy archival creates a **fresh live policy** rather than resurrecting the archived one — silently undoing a deliberate removal would be worse than a new record
- [X] T036 [P] [US2] Write failure-mode tests in `apps/customers/tests/test_loaddataset.py`: a file missing **policy** columns now fails before writing any customer (a behaviour change from Phase 2a), plus missing/unreadable/headerless files — each creating nothing (FR-046)
- [X] T037 [P] [US2] Write loader audit tests in `apps/customers/tests/test_loaddataset.py`: each created policy writes an entry with `actor=None` and `context={"source": "loaddataset", ...}` (FR-048)
- [X] T038 [P] [US2] Write alias tests in `apps/customers/tests/test_loaddataset.py`: `loadcustomers` still runs and produces identical behaviour to `loaddataset`, including policy creation

### Implementation

- [X] T039 [US2] Create `apps/customers/management/commands/loaddataset.py` extending the Phase 2a loader: add the five policy columns to `COLUMN_MAP` and `REQUIRED_COLUMNS`, keeping the four claim columns ignored (FR-042)
- [X] T040 [US2] Implement per-row processing in `loaddataset.py`: **validate the policy before writing either record**, then create/update both inside **one** `transaction.atomic()`, matching policies on `(customer, policy_type)` among live rows only, with `record_action(actor=None, ...)` for each record inside that transaction
- [X] T041 [US2] Add separate customer and policy count reporting to `loaddataset.py` (FR-044), with per-refusal row number and field
- [X] T042 [US2] Reduce `apps/customers/management/commands/loadcustomers.py` to a thin subclass of `loaddataset` so the Phase 2a command name keeps working, and update its module docstring to say it now loads policies too

**Checkpoint**: `loaddataset data/Insurance_Dataset.csv` → 3000 customers + 3000 policies. Re-run → all updated, zero duplicates. **Demonstrable product.**

---

## Phase 6: User Story 1 — Underwriter Reviews Coverage (Priority: P1)

**Goal**: A searchable, filterable book of business over the loaded data.

**Independent Test**: Open a customer's policies; filter the full list by type and by expiry.

**Note**: RBAC is applied inline at T049, not deferred.

### Tests First

- [X] T043 [P] [US1] Write read-permission tests in `apps/policies/tests/test_permissions.py`: the eight viewing roles get 200 on list; Executive Leadership and anonymous get **403 on the collection route** (FR-026)
- [X] T044 [P] [US1] Write list and pagination tests in `apps/policies/tests/test_views.py`: page size 50, `count` reflects total matches, ordering by `id` stable across repeated requests (FR-018)
- [X] T045 [P] [US1] Write customer-filter tests in `apps/policies/tests/test_views.py`: `?customer=<id>` returns only that customer's policies (FR-019)
- [X] T046 [P] [US1] Write type and expiry filter tests in `apps/policies/tests/test_views.py`: `?policy_type=` exact match, `?expired=true` returns only policies whose `end_date` is before today, and the two combine (FR-020). Use the factory's `expired` trait — expiry is derived per request, never stored
- [X] T047 [P] [US1] Write retrieve tests in `apps/policies/tests/test_views.py`: 200 with the full record and embedded customer summary; **404** for a nonexistent id and for an unpermitted requester, indistinguishable (FR-023)
- [X] T048 [P] [US1] Write query-count tests in `apps/policies/tests/test_views.py` asserting the embedded customer summary does not cause N+1 across a 50-record page (`select_related`)

### Implementation

- [X] T049 [US1] Create `PolicyViewSet` in `apps/policies/views.py` with list and retrieve, queryset from `Policy.objects` with `select_related("customer")`, ordered by `id`, and `HasRole(...)` for the eight viewing roles
- [X] T050 [US1] Add `PolicyPagination` (page size 50) to `apps/policies/views.py`, matching the existing pagination idiom
- [X] T051 [US1] Implement `get_queryset()` filtering in `apps/policies/views.py` for `customer`, `policy_type`, and `expired` (comparing `end_date` to `timezone.localdate()`)
- [X] T052 [US1] Register the router in `apps/policies/urls.py`

**Checkpoint**: quickstart §5, §6 pass. A readable book of business over 3,000 real policies.

---

## Phase 7: User Story 3 — Underwriter Creates and Corrects Policies (Priority: P2)

**Goal**: Create, partially update, and archive policies, with incoherent entries refused.

**Independent Test**: Create a policy for an existing customer and retrieve it from that customer's list; attempt incoherent entries and confirm each is refused with a clear reason.

### Tests First

- [X] T053 [P] [US3] Write write-permission tests in `apps/policies/tests/test_permissions.py`: only Underwriter and System Administrator may POST/PATCH/DELETE; the six view-only roles are refused (**404** on detail routes) and the data is unchanged. Note this is the **reverse** of the customer module, where Customer Service writes and Underwriter does not
- [X] T054 [P] [US3] Write create tests in `apps/policies/tests/test_views.py`: 201 with the embedded customer, immediately retrievable, and `renewal_probability` null (FR-004)
- [X] T055 [US3] Write multi-policy tests in `apps/policies/tests/test_views.py`: a second policy of a **different** type for the same customer succeeds (FR-003, SC-009); a second **live** policy of the same type is refused naming `policy_type`. Pass `customer=` explicitly — the factory's `SubFactory` would otherwise give each policy its own customer and never exercise this
- [X] T056 [P] [US3] Write partial-update tests in `apps/policies/tests/test_views.py`: patching only `premium_usd` changes that field and leaves every other field byte-identical (FR-017)
- [X] T057 [US3] Write archive tests in `apps/policies/tests/test_views.py`: DELETE returns 204 and sets `archived_at`; the row survives in `all_objects`; re-DELETE returns 404; and the `(customer, policy_type)` slot is **released** so a new policy of that type succeeds (FR-021, SC-012)

### Implementation

- [X] T058 [US3] Add create, update, and destroy mixins plus `get_serializer_class()` to `PolicyViewSet` in `apps/policies/views.py`
- [X] T059 [US3] Split permissions per action in `apps/policies/views.py` so write actions require Underwriter or System Administrator while reads keep the eight viewing roles (FR-026)
- [X] T060 [US3] Override `create`/`partial_update`/`destroy` in `apps/policies/views.py`, each wrapped in `transaction.atomic()` with `record_action()` **inside** the same block (FR-033)
- [X] T061 [US3] Implement `destroy()` as a soft delete in `apps/policies/views.py` — set `archived_at`, never call `.delete()` (FR-021)

**Checkpoint**: quickstart §7, §8, §10 pass.

---

## Phase 8: User Story 5 — Roles Enforced on Every Operation (Priority: P1)

**Goal**: Prove the complete FR-026 matrix. Enforcement already exists from T049/T059; this phase makes it *verified*.

**Independent Test**: Every policy operation attempted as each of the nine roles and once unauthenticated; 100% match FR-026.

- [X] T062 [US5] Write the exhaustive matrix test in `apps/policies/tests/test_permissions.py` — parametrized over all 9 roles × 5 operations plus the anonymous case, asserting the exact status from the FR-026 table (SC-005)
- [X] T063 [P] [US5] Write the **cross-module asymmetry** test in `apps/policies/tests/test_permissions.py`: a Product Manager gets 200 on the policy list and 403 on the customer list, and a Customer Service user gets 200 reading policies but is refused writing them. These two differences from Phase 2a are deliberate, and a test pins them so neither module is later "harmonized" into the other
- [X] T064 [P] [US5] Write superuser-non-bypass tests in `apps/policies/tests/test_permissions.py`: a superuser whose role is `executive_leadership` still gets 403 on list and 404 on detail (FR-027)
- [X] T065 [P] [US5] Write role-freshness tests in `apps/policies/tests/test_permissions.py`: changing a user's role changes the next request's outcome (FR-025). Watch the Phase 1 `force_authenticate` staleness gotcha — re-authenticate rather than reusing the stale user object

**Checkpoint**: SC-005 satisfied.

---

## Phase 9: User Story 4 — Compliance Officer Traces Changes (Priority: P2)

**Goal**: Prove the policy audit trail end to end, including refusals.

**Independent Test**: Create, update, and delete a policy, then retrieve its history and confirm three entries with actor, timestamp, and before/after values.

### Tests First

- [X] T066 [P] [US4] Write audit-content tests in `apps/policies/tests/test_audit.py`: create writes `policy.created` with full `after`; update writes `policy.updated` with **only changed fields** (FR-029) — patching `premium_usd` must not list `policy_type`; delete writes `policy.deleted` with full `before` at removal (FR-030)
- [X] T067 [P] [US4] Write atomicity tests in `apps/policies/tests/test_audit.py`: force the audit write to fail and assert the policy change rolls back — neither persists (FR-033)
- [X] T068 [P] [US4] Write no-audit-on-read tests in `apps/policies/tests/test_audit.py`: list, filter, and retrieve produce zero audit entries (FR-035)
- [X] T069 [US4] Write **refusal-vs-miss** tests in `apps/policies/tests/test_audit.py`: a permission-denied operation writes `outcome="refused"` with the policy unchanged (FR-031); a **permitted** user's 404 on a nonexistent id writes **no** entry (FR-032). Include the Product Manager case specifically — permitted on policies, so their 404 is a miss, unlike on customers
- [X] T070 [P] [US4] Write append-only tests in `apps/policies/tests/test_audit.py`: no policy operation updates or deletes an existing `AuditLog` row (FR-034)

### Implementation

- [X] T071 [US4] Verify the Phase 4 registry emits correct policy refusal entries end to end by running `pytest apps/policies/tests/test_audit.py`; if `target_type` or action names are wrong, fix the policies entry in `apps/core/audit_routes.py`, never the shared handler in `apps/core/exception_handlers.py`

**Checkpoint**: quickstart §12 passes.

---

## Phase 10: Cross-Entity Archival Guarantees

**Purpose**: The Customer↔Policy contract (FR-008, FR-022, SC-008). This belongs to no single user story — it is the interaction between two features — so it gets its own phase rather than being scattered across them.

- [X] T072 Write archived-customer tests in `apps/policies/tests/test_relationships.py`: archiving a customer leaves their policies **live, readable, and linked**, with the customer summary still resolving in the API response (FR-008, FR-022, SC-008). This is the guarantee that stops customer removal from destroying coverage history
- [X] T073 [P] Write the reverse-direction test in `apps/policies/tests/test_relationships.py`: an archived **policy** is hidden from `customer.policies` traversal while its customer stays live. The two directions fail independently, so they are asserted separately
- [X] T074 [P] Write archived-customer create tests in `apps/policies/tests/test_relationships.py`: creating a policy for an archived customer is refused naming `customer` (FR-014), with a message distinguishing "archived" from "does not exist"
- [X] T075 Write Phase 2a regression tests in `apps/policies/tests/test_relationships.py`: archiving a customer who holds policies still returns 204 and still writes its `customer.deleted` audit entry — this feature must not have made customer removal fail

**Checkpoint**: quickstart §9 passes. SC-008 satisfied.

---

## Phase 11: Remove the Phase 1 Placeholder

- [X] T076 Delete `PlaceholderView` from `apps/policies/views.py` and its route from `apps/policies/urls.py` (FR-049)
- [X] T077 Delete the Phase 1 placeholder tests from `apps/policies/tests/test_views.py` — the module asserts `{"module": "policies", "status": "placeholder"}` and covers nothing else, so it is replaced rather than amended
- [X] T078 Add a test asserting `GET /api/policies/placeholder/` returns **404** in `apps/policies/tests/test_views.py` (SC-011)

---

## Phase 12: Polish & Cross-Cutting Concerns

- [X] T079 Run the full suite: `docker compose exec web pytest`. Every Phase 1 and Phase 2a test must still pass — the Phase 4 handler refactor is the highest-risk change here, so any failure in `apps/customers/` or `apps/core/` is a regression, not an intended change
- [X] T080 Verify coverage: `pytest --cov=apps.policies --cov=apps.core --cov-report=term-missing` shows **≥95%** (SC-010). Close gaps with real assertions, never `# pragma: no cover`; delete genuinely dead code rather than testing it
- [X] T081 [P] Verify performance against the full dataset per `specs/003-policy-management/quickstart.md` §5: single retrieve <1s (SC-003), customer's policies and filtered list <2s (SC-004)
- [X] T082 [P] Confirm `data/Insurance_Dataset.csv` remains gitignored and unstaged (FR-047)
- [ ] T083 **DEFERRED (awaiting user)** — Execute [quickstart.md](./quickstart.md) end to end, all 14 scenarios, against a real running stack. **Ask before any dev-database write** — prefer the test suite where it proves the same property, and leave any records created for verification in place rather than deleting them
- [X] T084 [P] Update `README.md`: rename the load command to `loaddataset` (noting the `loadcustomers` alias), and add the policy endpoints with their permission matrix
- [X] T085 [P] Add a note to `README.md` recording the two deliberate divergences from the customer module — Underwriter (not Customer Service) writes policies, and Product Manager may read policies but not customers

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Model)**: depends on Phase 1 — **blocks everything**
- **Phase 3 (Serializer)**: depends on Phase 2 — **blocks US2 and US3**
- **Phase 4 (Handler refactor)**: depends only on Phase 1. **Deliberately early** — must land before any policy route exists
- **Phase 5 (US2 loader)**: depends on Phase 3
- **Phase 6 (US1 read)**: depends on Phase 2; *practically* wants Phase 5 for realistic volume
- **Phase 7 (US3 write)**: depends on Phase 3 and Phase 6 (extends the same viewset)
- **Phase 8 (US5 RBAC proof)**: depends on Phases 6 and 7
- **Phase 9 (US4 audit)**: depends on Phase 7 and Phase 4
- **Phase 10 (Cross-entity)**: depends on Phase 7
- **Phase 11 (Placeholder)**: depends on Phase 6
- **Phase 12 (Polish)**: depends on all above

### Critical Path

```
Setup → Model → Serializer → Loader (US2) → Read (US1) → Write (US3) ┬→ RBAC proof (US5)
          │                                                          ├→ Audit (US4)
          └→ Handler refactor (early, independent) ──────────────────┴→ Cross-entity
                                                    → Placeholder → Polish
```

The handler refactor runs on its own track and can proceed in parallel with Phases 2–3, provided it lands before Phase 9.

### Within Each Phase

- Tests written and **observed failing** before implementation (Principle V, SC-010)
- Model → serializer → view → integration

---

## Parallel Opportunities

**Phase 2** — T004, T005, T007 in parallel (T006 separately: live-scoped uniqueness is the subtle one).

**Phase 3** — all five test tasks (T014–T018) are independent.

**Phase 5 (US2)** — T030, T031, T035, T036, T037, T038 in parallel. T032, T033, T034 are deliberately **not** parallel: the match key, archived reconciliation, and row atomicity each deserve focused attention.

**Phase 6 (US1)** — T043–T048 all independent.

**Phase 9 (US4)** — T066, T067, T068, T070 in parallel; T069 separately, since the refusal/miss distinction is the subtle one.

---

## Implementation Strategy

### MVP: Phases 1–5 (Setup → Model → Serializer → Handler → Loader)

Delivers a populated book of business: 3,000 customers with 3,000 policies, idempotent, with refusal auditing generalized. **Stop and validate**: quickstart §2, §3, §4, §14.

### Increment 2: Phase 6 (US1 read)

Adds the readable, filterable policy list. Combined with the MVP this is a coherent demo. **Validate**: quickstart §5, §6.

### Increment 3: Phases 7–10 (write + RBAC + audit + cross-entity)

Completes the module. These ship together by necessity: write endpoints without RBAC would expose commercial terms, and without in-transaction audit would violate FR-033. **Validate**: quickstart §7–§12.

### Increment 4: Phases 11–12

Placeholder removal and polish. **Validate**: full quickstart, coverage ≥95%.

---

## Notes

- `[P]` = different files, no dependencies on incomplete work
- Verify tests fail before implementing — Principle V is non-negotiable
- **The Phase 4 gate is absolute**: if a customer audit test needs editing, the refactor is wrong. Revert and rethink rather than adjusting the test to match new behaviour
- **Dev database**: ask before any write. The test database is disposable and needs no permission
- The four subtle failures this list guards against, each with a dedicated non-parallel test: the handler refactor silently changing customer behaviour (T026), the loader matching on customer alone (T032), archived-customer reconciliation (T033), and a uniqueness constraint that would permanently consume a coverage slot (T006)
