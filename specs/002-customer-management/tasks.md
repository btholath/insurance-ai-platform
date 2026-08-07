---

description: "Task list for Phase 2a — Customer Management"
---

# Tasks: Phase 2a — Customer Management

**Input**: Design documents from `/specs/002-customer-management/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **REQUIRED, not optional.** Constitution Principle V is non-negotiable for business-rule code, and SC-009 requires validation, identity, permission, and audit tests written *before* the implementation they cover, with ≥95% measured coverage. Test tasks below are ordered before their implementation and must be observed failing first.

**Organization**: Grouped by user story. See "Story Independence — an honest caveat" below for where independence is real and where it is nominal.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US5, mapping to spec.md user stories
- All paths are repo-relative from `/home/bijut/insurance-ai-platform/`

## Path Conventions

Single Django project, per-domain apps under `apps/` — the Phase 1 layout. `apps.customers` is already in `INSTALLED_APPS` and `config/urls.py` already routes `/api/customers/`, so this feature fills an existing app shell.

---

## Story Independence — an honest caveat

The template assumes user stories are independently implementable. Three of these five genuinely are. Two are not, and pretending otherwise would produce a task list that misleads whoever executes it:

- **US1 (read), US2 (load), US3 (write)** are independently implementable and testable. Real phases.
- **US5 (RBAC)** is a *property of every endpoint* US1 and US3 build, not a separate feature. It cannot be built after them without shipping an interval where real personal data is unprotected — which the spec itself calls out as the reason US5 is P1. It is therefore applied **inline** as each endpoint is written (T027, T038), with Phase 7 dedicated to proving the full matrix rather than to introducing enforcement.
- **US4 (audit)** is likewise a property of the write path. Audit is written **inside the same transaction** as each write (FR-031) — it cannot be bolted on afterward without violating that requirement. Phase 8 proves the trail and adds refusal logging, which is the one genuinely new mechanism.

This ordering is deliberate and matches the plan's Implementation Sequence. Phases 7 and 8 are verification-and-completion phases for cross-cutting properties, not deferred implementation.

---

## Phase 1: Setup

**Purpose**: App scaffolding that does not exist yet

- [X] T001 Create `apps/customers/migrations/__init__.py` (the app has no migrations package yet)
- [X] T002 [P] Create `apps/customers/management/__init__.py` and `apps/customers/management/commands/__init__.py`
- [X] T003 [P] Verify baseline is green before any change: run `pytest` and record the passing count in the commit message

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The `Customer` entity and its test factory. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase completes.

### Tests First (Principle V)

- [X] T004 [P] Write model tests in `apps/customers/tests/test_models.py` covering: field presence per data-model.md, `age` 18/120 accepted and 17/121 rejected by `CheckConstraint`, score range constraints accepting `NULL` (the SQL three-valued-logic trap — a customer with no scores must insert cleanly), and `client_id` uniqueness holding across archived rows
- [X] T005 [P] Write manager tests in `apps/customers/tests/test_models.py` asserting `Customer.objects` excludes archived rows, `Customer.all_objects` includes them, and `Customer._default_manager` is `objects` (this is what keeps archived customers from surfacing through future `policy.customer` traversal)
- [X] T006 [P] Write reference-generation tests in `apps/customers/tests/test_models.py`: format `CL-#####`, max+1 continuation, no reissue of an **archived** record's reference, and correct ordering past 5 digits (seed a `CL-100000` row and assert the next is `CL-100001`, not a collision — the lexicographic-sort bug from research.md §2)

### Implementation

- [X] T007 Create `Customer` model in `apps/customers/models.py` per data-model.md: all 13 fields, `TimeStampedModel` base, three `CheckConstraint`s with the `isnull` disjunction, and indexes on `lead_source`/`fraud_risk_flag`/`archived_at`
- [X] T008 Add `CustomerManager` and dual managers to `apps/customers/models.py` — `objects` declared **first** so it stays `_default_manager`, `all_objects = models.Manager()` second
- [X] T009 Implement `client_id` generation in `apps/customers/models.py` using `select_for_update()` over `all_objects`, ordered on `Cast(Substr("client_id", 4), IntegerField())`, with one retry on `IntegrityError`
- [X] T010 Generate and review migration `apps/customers/migrations/0001_initial.py` via `python manage.py makemigrations customers`; confirm constraints and indexes appear in the generated SQL with `sqlmigrate`
- [X] T011 [P] Create `CustomerFactory` in `apps/customers/factories.py` per data-model.md, with `client_id` sequence starting at `CL-90000` and `archived`/`scored` traits

**Checkpoint**: `pytest apps/customers/tests/test_models.py` green. Model and managers ready.

---

## Phase 3: Foundational — Validation Layer

**Purpose**: The serializer, which is the **single definition of validity** shared by the API and the CSV loader (FR-038). Both US2 and US3 depend on it.

### Tests First

- [X] T012 [P] Write serializer validation tests in `apps/customers/tests/test_serializers.py` covering FR-009 (name absent/empty), FR-010 (malformed email), FR-011 (age 17 and 121 rejected; 18 and 120 accepted), FR-012 (unrecognized gender/lead_source/fraud_risk_flag), FR-013 (scores outside 0–1) — each asserting the **offending field is named** in the error (FR-014)
- [X] T013 [P] Write absent-vs-zero tests in `apps/customers/tests/test_serializers.py`: a customer created without scores has `risk_score is None` (asserted with `is None`, never truthiness), and a customer with `cross_sell_score = 0.00` is distinguishable from it. The source data contains genuine `0.0` cross-sell scores, so this distinction is exercised by real loaded rows, not just synthetic ones
- [X] T014 [P] Write duplicate-handling tests in `apps/customers/tests/test_serializers.py`: two customers sharing an email both validate (FR-004); a `client_id` colliding with an existing **or archived** record is refused naming `client_id` (FR-003, FR-021)

### Implementation

- [X] T015 Create `CustomerSerializer` in `apps/customers/serializers.py` — read + create + loader shape, with `id`/`created_at`/`updated_at`/`archived_at` read-only and `client_id` optional on create
- [X] T016 Create `CustomerUpdateSerializer` in `apps/customers/serializers.py` — all fields optional for PATCH, `client_id` writable with uniqueness validation against `all_objects`

**Checkpoint**: `pytest apps/customers/tests/test_serializers.py` green. Validation is defined once and ready to be shared.

---

## Phase 4: User Story 2 — Administrator Seeds the Platform (Priority: P1) 🎯 MVP

**Goal**: Load the 3,000-record source dataset in one command, idempotently.

**Independent Test**: Run the load against the source file, confirm 3,000 customers; run it again unchanged and confirm the count is identical with zero duplicate references.

**Why this is the MVP rather than US1**: US1 (read) over an empty database demonstrates nothing. The loader delivers a populated, reproducible dataset — a demonstrable product on its own, and the precondition for verifying US1's search and pagination at realistic volume.

### Tests First

- [X] T017 [P] [US2] Write loader happy-path tests in `apps/customers/tests/test_loadcustomers.py` using a small fixture CSV: correct row count created, correct field mapping per the contract's column table, and reported created/updated/refused counts (FR-039)
- [X] T018 [P] [US2] Write idempotency tests in `apps/customers/tests/test_loadcustomers.py`: second run on unchanged input leaves the count identical, reports all-updated, and produces zero duplicate `client_id` (FR-035, SC-002); a changed source row updates in place rather than duplicating (FR-036)
- [X] T019 [US2] Write the **archived-reconciliation** test in `apps/customers/tests/test_loadcustomers.py`: archive a loaded customer, re-run the load, assert the archived row reconciles in place with no duplicate and no `IntegrityError` (FR-021, SC-011). This is the test that fails if the loader looks up through `objects` instead of `all_objects` — the failure is invisible in ordinary use, so it gets its own named test
- [X] T020 [P] [US2] Write loader failure-mode tests in `apps/customers/tests/test_loadcustomers.py`: missing file, unreadable file, missing required columns, empty/headerless file — each exits non-zero with a clear message and creates **zero** customers (FR-040)
- [X] T021 [P] [US2] Write loader validation tests in `apps/customers/tests/test_loadcustomers.py`: an invalid row is refused with its 1-based row number and offending field named, valid rows in the same file still persist (per-row atomicity), and extra unmapped columns cause no error (FR-037, FR-038)
- [X] T022 [P] [US2] Write loader audit tests in `apps/customers/tests/test_loadcustomers.py`: each created row writes an `AuditLog` with `actor=None` and `context={"source": "loadcustomers", ...}` (FR-042)

### Implementation

- [X] T023 [US2] Implement `loadcustomers` in `apps/customers/management/commands/loadcustomers.py` per contracts/loadcustomers-command.md: required positional `csv_path` with **no default** (FR-034), `--dry-run` flag, `csv.DictReader` streaming
- [X] T024 [US2] Add up-front column validation to `loadcustomers.py` inspecting `DictReader.fieldnames` **before** the row loop, raising `CommandError` so a structurally wrong file cannot write a partial load (FR-040)
- [X] T025 [US2] Add per-row processing to `loadcustomers.py`: own `transaction.atomic()` per row, `CustomerSerializer` for validation (not direct model writes — FR-038), match on `client_id` via `all_objects` (FR-021), and `record_action(actor=None, ...)` inside the row transaction (FR-042)
- [X] T026 [US2] Add completion reporting to `loadcustomers.py`: created/updated/refused counts and per-refusal row number plus field (FR-039); exit 0 with refusals present, exit 1 only on `CommandError`

**Checkpoint**: `python manage.py loadcustomers data/Insurance_Dataset.csv` → `Created: 3000`. Re-run → `Updated: 3000`, zero duplicates. Quickstart §2, §3, §4, §13 pass. **Demonstrable product.**

---

## Phase 5: User Story 1 — CSR Looks Up a Customer (Priority: P1)

**Goal**: Searchable, filterable, paginated customer directory over the loaded data.

**Independent Test**: Search by name fragment, by email, and by reference; open a returned record.

**Note**: RBAC is applied inline at T027, not deferred — see the caveat above.

### Tests First

- [X] T027 [P] [US1] Write read-permission tests in `apps/customers/tests/test_permissions.py`: the seven roles permitted to view get 200 on list; Product Manager, Executive Leadership, and anonymous get **403 on the collection route** (FR-024)
- [X] T028 [P] [US1] Write list/pagination tests in `apps/customers/tests/test_views.py`: `page_size` 50, `count` reflects total matches, ordering by `id` is stable across repeated requests to the same page (FR-017)
- [X] T029 [P] [US1] Write search tests in `apps/customers/tests/test_views.py`: partial name, full email, and `client_id`, all case-insensitive; a shared email returns **both** holders (FR-018, SC-008); a no-match search returns 200 with empty results, not an error
- [X] T030 [P] [US1] Write filter tests in `apps/customers/tests/test_views.py`: `lead_source`, `gender`, `fraud_risk_flag` individually and combined (FR-019)
- [X] T031 [P] [US1] Write retrieve tests in `apps/customers/tests/test_views.py`: 200 with the full record including stored scores; **404** for a nonexistent id and for an unpermitted requester, indistinguishable (FR-022)
- [X] T032 [US1] Write archived-invisibility tests in `apps/customers/tests/test_views.py`: an archived customer is absent from list, search, and detail (404) (FR-020)

### Implementation

- [X] T033 [US1] Create `CustomerViewSet` in `apps/customers/views.py` with `ListModelMixin` + `RetrieveModelMixin`, queryset from `Customer.objects` (archived excluded automatically), `.order_by("id")`
- [X] T034 [US1] Add `CustomerPagination` (`page_size = 50`) to `apps/customers/views.py`, matching the existing `AuditPagination`/`UserListPagination` idiom
- [X] T035 [US1] Implement `get_queryset()` search and filtering in `apps/customers/views.py` via explicit `query_params` — `Q(name__icontains) | Q(email__icontains) | Q(client_id__icontains)` for search, exact match for the three filters (no new dependency; matches `apps/audit/views.py`)
- [X] T036 [US1] Apply `HasRole(...)` for the seven viewing roles to `CustomerViewSet` in `apps/customers/views.py` (FR-023, FR-024)
- [X] T037 [US1] Register the router in `apps/customers/urls.py` for list and detail routes

**Checkpoint**: Quickstart §5, §6 pass. A searchable directory over 3,000 real records. **Combined with Phase 4, this is a coherent demo.**

---

## Phase 6: User Story 3 — CSR Creates and Corrects Records (Priority: P2)

**Goal**: Create, partially update, and archive customers, with validation refusing implausible entries.

**Independent Test**: Create a valid customer and retrieve it; attempt several invalid entries and confirm each is refused with a clear reason.

**Note**: Write-permission enforcement is applied inline at T038/T044 and audit at T045 — both are properties of these endpoints, not later additions.

### Tests First

- [X] T038 [P] [US3] Write write-permission tests in `apps/customers/tests/test_permissions.py`: only Customer Service and System Administrator may POST/PATCH/DELETE; the five view-only roles are refused (**404** on detail routes, per `HasRole`) and the data is unchanged (FR-024)
- [X] T039 [P] [US3] Write create tests in `apps/customers/tests/test_views.py`: 201 with a generated `client_id`, immediately retrievable, and all three scores `null` (FR-005, FR-006)
- [X] T040 [P] [US3] Write partial-update tests in `apps/customers/tests/test_views.py`: patching only `phone` changes that field and leaves **every** other field byte-identical (FR-016)
- [X] T041 [P] [US3] Write conflict tests in `apps/customers/tests/test_views.py`: PATCHing a `client_id` that belongs to another customer is refused naming the conflict (FR-003)
- [X] T042 [US3] Write archive tests in `apps/customers/tests/test_views.py`: DELETE returns 204 and sets `archived_at`; the row survives in `all_objects`; re-DELETE returns 404 (terminal, not double-archive); the reference stays reserved (FR-020, FR-021)

### Implementation

- [X] T043 [US3] Add `CreateModelMixin`/`UpdateModelMixin`/`DestroyModelMixin` and `get_serializer_class()` to `CustomerViewSet` in `apps/customers/views.py`, returning `CustomerUpdateSerializer` for `update`/`partial_update`
- [X] T044 [US3] Split permissions per action in `apps/customers/views.py` so write actions require Customer Service or System Administrator while reads keep the seven viewing roles (FR-024)
- [X] T045 [US3] Override `create`/`partial_update`/`destroy` in `apps/customers/views.py` to wrap each in `transaction.atomic()` with `record_action()` **inside** the same block (FR-031), following the `apps/accounts/views.py` pattern
- [X] T046 [US3] Implement `destroy()` as a soft delete in `apps/customers/views.py` — set `archived_at = timezone.now()`, never call `.delete()` (FR-020)

**Checkpoint**: Quickstart §7, §8, §9 pass. Full CRUD with validation and archival.

---

## Phase 7: User Story 5 — Roles Enforced on Every Operation (Priority: P1)

**Goal**: Prove the complete FR-024 matrix. Enforcement already exists from T036/T044; this phase makes it *verified* rather than *assumed*.

**Independent Test**: Every customer operation attempted once as each of the nine roles and once unauthenticated; 100% of outcomes match FR-024.

### Tests

- [X] T047 [US5] Write the exhaustive matrix test in `apps/customers/tests/test_permissions.py` — parametrized over all 9 roles × 5 operations plus the anonymous case, asserting the exact status from the FR-024 table (SC-005). This subsumes the targeted checks in T027/T038 and is the authoritative proof
- [X] T048 [P] [US5] Write superuser-non-bypass tests in `apps/customers/tests/test_permissions.py`: a user with `is_superuser=True` whose role is `product_manager` still gets 403 on list and 404 on detail (FR-026)
- [X] T049 [P] [US5] Write role-freshness tests in `apps/customers/tests/test_permissions.py`: changing a user's role in the database changes the next request's outcome, with no stale caching (FR-025). Note the Phase 1 `force_authenticate` staleness gotcha — re-authenticate or refetch rather than reusing the stale user object
- [X] T050 [P] [US5] Write route-shape tests in `apps/customers/tests/test_permissions.py` documenting the deliberate asymmetry: collection refusals are 403, detail refusals are 404 (FR-022)

**Checkpoint**: `pytest apps/customers/tests/test_permissions.py` green across the full matrix. SC-005 satisfied.

---

## Phase 8: User Story 4 — Compliance Officer Traces Changes (Priority: P2)

**Goal**: Prove the audit trail, and add refusal logging — the one genuinely new audit mechanism in this feature.

**Independent Test**: Create, update, and delete a customer, then retrieve its history and confirm three entries with actor, timestamp, and before/after values.

### Tests First

- [X] T051 [P] [US4] Write audit-content tests in `apps/customers/tests/test_audit.py`: create writes `customer.created` with full `after`; update writes `customer.updated` with **only changed fields** in `before`/`after` (FR-028) — patching `phone` must not list `name`; delete writes `customer.deleted` with full `before` at removal (FR-029)
- [X] T052 [P] [US4] Write atomicity tests in `apps/customers/tests/test_audit.py`: force the audit write to fail and assert the customer change rolls back — neither persists (FR-031)
- [X] T053 [P] [US4] Write no-audit-on-read tests in `apps/customers/tests/test_audit.py`: list, search, and retrieve produce zero audit entries (FR-033)
- [X] T054 [US4] Write refusal-audit tests in `apps/customers/tests/test_audit.py`: a permission-denied operation writes `outcome="refused"` with the customer unchanged (FR-030); critically, a **permitted** user's ordinary 404 on a nonexistent id writes **no** refusal entry (research.md §4 — otherwise every mistyped reference pollutes the compliance record)
- [X] T055 [P] [US4] Write append-only tests in `apps/customers/tests/test_audit.py`: no customer operation updates or deletes an existing `AuditLog` row; the Phase 1 DB trigger still holds (FR-032)

### Implementation

- [X] T056 [US4] Create `apps/core/exception_handlers.py` with a DRF handler that writes an `AuditLog` with `outcome="refused"` for `PermissionDenied` and `NotFound` on customer routes, delegating to `rest_framework.views.exception_handler` for the response itself
- [X] T057 [US4] Add role-scoping to the handler in `apps/core/exception_handlers.py`: consult `request.user` so an unauthenticated or non-viewing-role requester's `NotFound` is a refusal, while a permitted user's `NotFound` is an ordinary miss and is not logged
- [X] T058 [US4] Register `EXCEPTION_HANDLER` in `config/settings/base.py` under `REST_FRAMEWORK`
- [X] T059 [US4] Verify the response body is untouched by the handler — non-disclosure must survive refusal logging (FR-022)

**Checkpoint**: Quickstart §11 passes. Full chain of custody over customer data.

---

## Phase 9: Remove the Phase 1 Placeholder

**Purpose**: FR-043 / SC-010. Sequenced here because the real endpoints must exist before the placeholder is withdrawn.

- [X] T060 Delete `PlaceholderView` from `apps/customers/views.py` and its route from `apps/customers/urls.py` (FR-043)
- [X] T061 Delete the Phase 1 placeholder tests from `apps/customers/tests/test_views.py` — the module asserts `{"module": "customers", "status": "placeholder"}` and covers nothing else, so it is replaced rather than amended (FR-043)
- [X] T062 Add a test asserting `GET /api/customers/placeholder/` returns **404** in `apps/customers/tests/test_views.py` (SC-010)

**Checkpoint**: Quickstart §12 passes. No route serves a fixed non-record response.

---

## Phase 10: Polish & Cross-Cutting Concerns

- [X] T063 Run the full suite: `pytest` — every Phase 1 test still passing alongside the new customer tests. This feature adds no new permission or audit mechanism, so any Phase 1 failure is a regression, not an intended change
- [X] T064 Verify coverage: `pytest --cov=apps.customers --cov-report=term-missing` shows **≥95%** (SC-009). Close gaps with real assertions, never with `# pragma: no cover`
- [X] T065 [P] Verify performance against the full 3,000-record dataset: single retrieve <1s (SC-003), search first page <2s (SC-004), per quickstart §5
- [X] T066 [P] Confirm `data/Insurance_Dataset.csv` remains gitignored and unstaged (FR-041) — `git check-ignore -v data/Insurance_Dataset.csv`
- [X] T067 Execute [quickstart.md](./quickstart.md) end to end, all 13 scenarios, against a real running stack — not just the test suite
- [X] T068 [P] Update `README.md` with the `loadcustomers` command and the customer endpoints
- [X] T069 Review the plan's "Known Spec Defect" section — the duplicate FR-013 was corrected in spec.md on 2026-08-06 (the Edge Cases reference now points to FR-020). Update that section in `plan.md` to record it as resolved rather than outstanding

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Model)**: depends on Phase 1 — **blocks everything**
- **Phase 3 (Serializer)**: depends on Phase 2 — **blocks US2 and US3**
- **Phase 4 (US2 loader)**: depends on Phase 3
- **Phase 5 (US1 read)**: depends on Phase 2; *practically* wants Phase 4 for realistic data volume
- **Phase 6 (US3 write)**: depends on Phase 3 and Phase 5 (extends the same viewset)
- **Phase 7 (US5 RBAC proof)**: depends on Phases 5 and 6 — needs endpoints to test
- **Phase 8 (US4 audit)**: depends on Phase 6 — needs write operations to audit
- **Phase 9 (placeholder removal)**: depends on Phase 5 — real endpoints must exist first
- **Phase 10 (polish)**: depends on all above

### Critical Path

```
Setup → Model → Serializer → Loader (US2) → Read (US1) → Write (US3) → RBAC proof (US5)
                                                                      → Audit (US4)
                                                       → Placeholder removal → Polish
```

US5 and US4 verification can proceed in parallel once Phase 6 completes.

### Within Each Phase

- Tests are written and **observed failing** before implementation (Principle V, SC-009)
- Model → serializer → view → integration
- `[P]` tasks touch different files or different test functions with no shared state

---

## Parallel Opportunities

**Phase 2** — three test files/areas at once:

```bash
Task: "T004 model field and constraint tests"
Task: "T005 manager isolation tests"
Task: "T006 reference generation tests"
```

**Phase 4 (US2)** — five independent loader test areas:

```bash
Task: "T017 happy-path load tests"
Task: "T018 idempotency tests"
Task: "T020 failure-mode tests"
Task: "T021 row-validation tests"
Task: "T022 loader audit tests"
```

*(T019, the archived-reconciliation test, is deliberately not parallel — it depends on archival semantics being settled and deserves focused attention.)*

**Phase 5 (US1)** — five independent read test areas: T027, T028, T029, T030, T031.

**Phase 8 (US4)** — T051, T052, T053, T055 in parallel; T054 separately, since the refusal/miss distinction is the subtle one.

---

## Implementation Strategy

### MVP: Phases 1–4 (Setup → Model → Serializer → Loader)

Delivers a populated, reproducible 3,000-record dataset with full validation. Demonstrable on its own, and the precondition for verifying everything else at realistic volume.

**Stop and validate**: quickstart §2, §3, §4, §13.

### Increment 2: Phase 5 (US1 read)

Adds a searchable, filterable directory over that data. Combined with the MVP this is a coherent product demo. **Stop and validate**: quickstart §5, §6.

### Increment 3: Phases 6–8 (write + RBAC proof + audit)

Completes the module. These three ship together by necessity, not preference: write endpoints without RBAC would expose real personal data, and without in-transaction audit would violate FR-031. **Stop and validate**: quickstart §7–§11.

### Increment 4: Phases 9–10

Placeholder removal and polish. **Validate**: full quickstart, coverage ≥95%.

---

## Notes

- `[P]` = different files, no dependencies on incomplete work
- Verify tests fail before implementing — Principle V is non-negotiable and SC-009 makes it measurable
- Commit after each task or logical group
- **Watch for the Phase 1 `force_authenticate` staleness gotcha** in permission tests (T049): reusing a stale user object after a role change silently tests the old role
- The two subtle failures this list guards against, each with a dedicated test: the loader using `objects` instead of `all_objects` (T019), and lexicographic `client_id` ordering breaking past five digits (T006). Both are invisible at 3,000 rows and expensive to find later
