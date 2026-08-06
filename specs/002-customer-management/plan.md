# Implementation Plan: Phase 2a — Customer Management

**Branch**: `002-customer-management` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-customer-management/spec.md`

## Summary

Replace Phase 1's placeholder customer endpoint with a real `Customer` model
and full CRUD API, plus an idempotent management command that loads the
3,000-row source dataset. The customer record carries identity, contact,
demographic, and acquisition fields, and stores — without computing — three
analytical values that Phases 3 and 5 will later produce.

The technical approach is deliberately conservative: reuse the Phase 1
`HasRole` permission factory and the `record_action()` audit write path
unchanged, add no new dependencies, and follow the idioms already established
in `apps/accounts/views.py` and `apps/audit/views.py`. Three decisions carry
the design:

1. **A two-manager soft delete.** `Customer.objects` hides archived records;
   `Customer.all_objects` sees them. The second manager is what makes FR-021
   satisfiable — the loader must find archived records by reference to
   reconcile against them.
2. **A shared serializer between API and loader.** FR-038 requires identical
   validation on both paths, so the loader constructs the same
   `CustomerSerializer` rather than writing models directly.
3. **Refusal auditing via a DRF exception handler.** FR-030 is new work;
   `HasRole` denies in two different shapes and the handler is the one seam
   that catches both.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15, psycopg 3.2.
**No new dependencies.** Search and filtering are implemented with explicit
`query_params` handling rather than adding `django-filter`, matching the
existing idiom in `apps/audit/views.py`.

**Storage**: PostgreSQL 16 (`customers_customer` table; one migration)

**Testing**: pytest 8 + pytest-django + Factory Boy, `--cov` per Principle V

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose for services

**Project Type**: Django web service, API-only (no UI in this feature)

**Performance Goals**: single-record retrieval < 1s (SC-003); search first page
< 2s (SC-004), both against the full 3,000-record dataset

**Constraints**: Local-first, no cloud calls (Principle I). Server-side RBAC on
every route (Principle III). Audit entry in the same transaction as every write
(FR-031). Source CSV must stay out of the repository (FR-041).

**Scale/Scope**: 3,000 customers; one new Django app module; ~11 mapped CSV
columns of 20; 5 API routes plus 1 management command.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this feature satisfies it |
|---|---|---|
| **I. Local-First** | PASS | No external calls. Postgres and the CSV file are local; no LLM involvement in this feature at all. |
| **II. Auditability by Default** | PASS | Customer is explicitly named in the principle. Every create/update/delete writes via the existing `record_action()`, in the same transaction (FR-031). Refusals logged (FR-030). Append-only already enforced by the Phase 1 DB trigger (FR-032). |
| **III. RBAC (NON-NEGOTIABLE)** | PASS | Every route carries `HasRole(...)` per the FR-024 matrix, enforced server-side. `HasRole` already refuses superuser bypass (FR-026) and re-reads the role per request (FR-025). No new mechanism. |
| **IV. Explainable AI Outputs** | **N/A** | No AI or LLM output in this feature. `risk_score`, `fraud_risk_flag`, and `cross_sell_score` are *stored as supplied* and never computed or interpreted (FR-007) — this feature produces no decision to explain. Principle IV binds Phase 3 (Risk) and Phase 5 (Fraud), which will produce these values. Storing an un-computed value is not a business decision. |
| **V. Test-First (NON-NEGOTIABLE)** | PASS | Validation, identity, permission, and audit behavior are business rules, so tests are written **before** implementation. Factory Boy `CustomerFactory` supplies test data. Coverage target ≥ 95% (SC-009). CRUD boilerplate is TDD-exempt per the principle but still tested before merge. |
| **VI. Disposable Prototyping** | PASS | No Phase 0 spike code is imported or refactored. This module starts fresh under the full Spec Kit lifecycle. |

**Stack conformance**: Python 3.13, Django 5.x + DRF, PostgreSQL, pytest +
Factory Boy — all within the binding stack. No deviation, so no amendment
needed. `pgvector`, Redis, Celery, and Ollama are simply unused here.

**Gate result: PASS.** No violations, so Complexity Tracking stays empty.

**Constitution Exceptions**: none. Principle IV is *not applicable* rather than
excepted — the feature produces no AI output to explain, by explicit design
(FR-007).

### Post-Phase-1 re-evaluation

Re-checked after producing `data-model.md`, `contracts/`, and `quickstart.md`.
No design decision introduced a violation:

- The two-manager soft delete adds no cloud dependency, no new permission path,
  and no AI surface.
- The shared serializer *strengthens* Principle V by giving one validation
  definition to test rather than two that can drift.
- The exception handler *strengthens* Principle II by capturing refusals that
  Phase 1 did not record.
- Reference generation under `select_for_update()` is a correctness measure, not
  added architecture.

**Gate result after design: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/002-customer-management/
├── plan.md              # This file
├── research.md          # Phase 0 output — 9 resolved decisions
├── data-model.md        # Phase 1 output — Customer entity, managers, factory
├── quickstart.md        # Phase 1 output — 13 validation scenarios
├── contracts/
│   ├── customers-api.md         # 5 REST routes + permission matrix
│   └── loadcustomers-command.md # CLI contract, column map, exit codes
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/customers/                     # exists as a Phase 1 placeholder shell
├── __init__.py
├── apps.py
├── models.py                       # NEW: Customer, CustomerManager
├── serializers.py                  # NEW: CustomerSerializer, CustomerUpdateSerializer
├── views.py                        # REWRITTEN: CustomerViewSet (placeholder deleted)
├── urls.py                         # REWRITTEN: router (placeholder route deleted)
├── factories.py                    # NEW: CustomerFactory
├── migrations/
│   ├── __init__.py                 # NEW (app has no migrations dir yet)
│   └── 0001_initial.py             # NEW
├── management/
│   └── commands/
│       └── loadcustomers.py        # NEW
└── tests/
    ├── __init__.py
    ├── test_views.py               # REPLACED (placeholder tests deleted, FR-043)
    ├── test_models.py              # NEW: constraints, managers, ref generation
    ├── test_serializers.py         # NEW: FR-009..FR-014 validation
    ├── test_permissions.py         # NEW: 9 roles x 5 ops (SC-005)
    ├── test_audit.py               # NEW: FR-027..FR-032
    └── test_loadcustomers.py       # NEW: FR-034..FR-042

apps/core/
└── exception_handlers.py           # NEW: refusal auditing (FR-030)

config/settings/base.py             # EDIT: REST_FRAMEWORK["EXCEPTION_HANDLER"]
```

**Structure Decision**: Single Django project, per-domain apps under `apps/` —
the layout Phase 1 established and which `config/settings/base.py` already
registers (`apps.customers` is in `INSTALLED_APPS`, and `config/urls.py`
already routes `/api/customers/`). This feature fills in an app shell that
already exists rather than introducing any new structure. The only file outside
`apps/customers/` is the exception handler, which lives in `apps/core/` because
it is registered globally in DRF settings and will serve Policy and Claims
identically.

## Implementation Sequence

Ordered by the spec's story priorities, each stage independently verifiable.

| Stage | Delivers | Stories / FRs |
|---|---|---|
| 1 | `Customer` model, managers, constraints, migration, factory | FR-001–FR-008, FR-020, FR-044 |
| 2 | Serializers with full validation | FR-009–FR-014 |
| 3 | `loadcustomers` command | US2 (P1), FR-034–FR-042, SC-001/002/008 |
| 4 | Read API — list, retrieve, search, filter, pagination | US1 (P1), FR-015–FR-019, FR-022 |
| 5 | Write API — create, patch, archive; placeholder deleted | US3 (P2), FR-003, FR-005, FR-016, FR-020, FR-021, FR-043 |
| 6 | `HasRole` on every route; full matrix test | US5 (P1), FR-023–FR-026, SC-005 |
| 7 | Audit on write; refusal handler | US4 (P2), FR-027–FR-033, SC-006 |

Stages 1–3 deliver a demonstrable product on their own: a populated,
reproducible 3,000-record dataset. Stage 6 is sequenced immediately after the
write API rather than last, because that is the first point where a permission
gap would expose real personal data — the spec's own rationale for making US5
a P1.

Per Principle V, tests precede implementation within each stage.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Loader looking up through `objects` instead of `all_objects` → `IntegrityError` on an invisible archived row | Explicit test: archive, re-load, assert reconciliation (quickstart §9). The failure is silent in ordinary use, so it gets its own named test rather than relying on the loader's other tests. |
| `order_by("-client_id")` lexicographic sort breaking past 5 digits | Order on the extracted numeric suffix (`Cast(Substr(...))`), correct at any width. Would not surface in any 3,000-row test. |
| Score `CheckConstraint` rejecting nulls via SQL three-valued logic | Constraints written as `isnull=True OR (gte AND lte)`; a test creates a customer with no scores. |
| Refusal handler logging ordinary 404s as permission refusals | Handler consults `request.user`'s role; a permitted user's 404 is a miss, not a refusal (research.md §4). |
| Validation drifting between API and loader | Loader uses the same serializer — one definition, exercised by both. |

## Known Spec Defect

The spec numbers two requirements **FR-013**: the score-range rule under
*Validation*, and a reference in *Edge Cases* to "the removal behavior defined
in FR-013" — where the actual archival requirement is **FR-020**.

This plan reads FR-013 as the score-range rule and FR-020 as the archival rule,
consistent with the Requirements section itself. No requirement is dropped
under this reading and the design is unaffected. Worth correcting in the spec
before `/speckit-tasks` so task numbering does not inherit the ambiguity.

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
