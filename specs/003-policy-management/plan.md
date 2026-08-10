# Implementation Plan: Phase 2b — Policy Management

**Branch**: `003-policy-management` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-policy-management/spec.md`

## Summary

Replace Phase 1's placeholder policy endpoint with a real `Policy` model and
full CRUD API, extend the dataset loader to seed policies alongside customers,
and generalize the refusal-auditing mechanism so it serves more than one module.

The approach mirrors Phase 2a wherever the requirement is the same — dual
managers, serializer-as-single-definition-of-validity, audit inside the write
transaction — and diverges deliberately where it is not. Four decisions carry
the design:

1. **The refusal handler becomes a registry.** It currently hardcodes customer
   knowledge in four places. FR-031 needs the same behavior for policies, and
   Claims will need it again — so it is generalized once rather than copied
   twice. This is the highest-risk change here: it touches shipped, tested code.
2. **Live-scoped uniqueness on `(customer, policy_type)`.** Deliberately the
   *opposite* of Customer, where archived `client_id` values stay reserved
   forever. Archiving a policy must release the coverage slot.
3. **The customer FK resolves through `all_objects`.** Otherwise a policy whose
   customer was archived becomes unreadable — precisely the orphaning FR-022
   forbids.
4. **One transaction per source row, spanning both records.** A half-landed row
   is the state an operator cannot reason about.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15, psycopg 3.2.
**No new dependencies.**

**Storage**: PostgreSQL 16 (`policies_policy`; one migration in `apps/policies/`)

**Testing**: pytest 8 + pytest-django + Factory Boy, `--cov` per Principle V

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose

**Project Type**: Django web service, API-only

**Performance Goals**: single retrieval < 1s (SC-003); customer's policies or a
filtered list < 2s (SC-004), against 3,000 policies

**Constraints**: Local-first (Principle I). Server-side RBAC on every route
(Principle III). Audit in the same transaction as every write (FR-033). Source
CSV stays out of the repository (FR-047).

**Scale/Scope**: 3,000 policies over 3,000 customers; 5 API routes; 1 extended
management command; ~16 of the dataset's 20 columns now consumed.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this feature satisfies it |
|---|---|---|
| **I. Local-First** | PASS | No external calls. Postgres and a local CSV only; no LLM involvement. |
| **II. Auditability** | PASS | Policy is explicitly named in the principle. Every write audits via the existing `record_action()` inside the same transaction (FR-033). Refusals recorded (FR-031), and distinguished from ordinary misses (FR-032). Append-only already enforced by the Phase 1 DB trigger. |
| **III. RBAC (NON-NEGOTIABLE)** | PASS | Every route carries `HasRole(...)` per FR-026, enforced server-side. Superuser does not bypass (FR-027); role re-read per request (FR-025). |
| **IV. Explainable AI** | **N/A** | No AI or LLM output. `renewal_probability` is *stored as supplied* and never computed or interpreted (FR-005) — this feature produces no decision to explain. Principle IV binds Phase 5, which will produce that value. |
| **V. Test-First (NON-NEGOTIABLE)** | PASS | Validation, relationship, permission, and audit behavior are business rules: tests precede implementation. Factory Boy supplies data. Coverage ≥ 95% (SC-010). |
| **VI. Disposable Prototyping** | PASS | No Phase 0 spike code involved. |

**Stack conformance**: within the binding stack; no deviation, no amendment
needed.

**Gate result: PASS.** No violations, so Complexity Tracking stays empty.

**Constitution Exceptions**: none. Principle IV is *not applicable* rather than
excepted.

### Post-Phase-1 re-evaluation

Re-checked after producing `data-model.md`, `contracts/`, and `quickstart.md`:

- The handler registry **strengthens** Principle II — it makes refusal
  recording a platform capability rather than a customer-module accident, and
  Claims inherits it as configuration.
- Live-scoped uniqueness introduces no new permission or AI surface.
- `PROTECT` on the customer FK strengthens the Principle II guarantee that
  history is not silently destroyed.
- The shared serializer between API and loader keeps one definition of validity
  to test, supporting Principle V.

**Gate result after design: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/003-policy-management/
├── plan.md              # This file
├── research.md          # Phase 0 — 10 resolved decisions
├── data-model.md        # Phase 1 — Policy entity, relationship, registry
├── quickstart.md        # Phase 1 — 14 validation scenarios
├── contracts/
│   ├── policies-api.md          # 5 REST routes + permission matrix
│   └── loaddataset-command.md   # CLI contract, column map, atomicity
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/policies/                      # exists as a Phase 1 placeholder shell
├── models.py                       # NEW: Policy, PolicyManager
├── serializers.py                  # NEW: PolicySerializer, PolicyUpdateSerializer
├── views.py                        # REWRITTEN: PolicyViewSet (placeholder deleted)
├── urls.py                         # REWRITTEN: router
├── factories.py                    # NEW: PolicyFactory
├── migrations/
│   ├── __init__.py                 # NEW (app has no migrations dir yet)
│   └── 0001_initial.py             # NEW
└── tests/
    ├── test_views.py               # REPLACED (placeholder tests deleted, FR-049)
    ├── test_models.py              # NEW: constraints, managers, live-scoped uniqueness
    ├── test_serializers.py         # NEW: FR-009..FR-015
    ├── test_permissions.py         # NEW: 9 roles x 5 ops (SC-005)
    ├── test_audit.py               # NEW: FR-028..FR-035
    └── test_relationships.py       # NEW: the cross-entity archival guarantees

apps/core/
├── audit_routes.py                 # NEW: the AuditedRoute registry
└── exception_handlers.py           # REFACTORED: registry-driven, not customer-specific

apps/customers/
└── management/commands/
    ├── loaddataset.py              # NEW: extended loader (customers + policies)
    └── loadcustomers.py            # REDUCED to a thin alias
```

**Structure Decision**: Single Django project, per-domain apps under `apps/` —
the layout Phases 1 and 2a established. `apps.policies` is already in
`INSTALLED_APPS` and `config/urls.py` already routes `/api/policies/`, so this
feature fills an existing shell.

Two files live outside `apps/policies/` for good reason. `apps/core/` holds the
registry and handler because they are registered globally in DRF settings and
serve every module. The loader stays under `apps/customers/management/` because
it is the extension of an existing command; splitting it would mean two
commands reading the same file.

**Note on the loader's location**: the command creates policies but lives in
the customers app. That is slightly awkward, and the alternative — moving it to
a neutral app — would break the `loadcustomers` alias path. Keeping it where it
is, with an accurate module docstring, is the lesser cost. Worth revisiting if
Claims makes it a three-app command.

## Implementation Sequence

| Stage | Delivers | Stories / FRs |
|---|---|---|
| 1 | `Policy` model, managers, constraints, migration, factory | FR-001–FR-008, FR-021 |
| 2 | Serializers with full validation | FR-009–FR-015 |
| 3 | Handler registry refactor; customer tests must pass **unmodified** | FR-031, FR-032 |
| 4 | `loaddataset` + alias | US2 (P1), FR-036–FR-048, SC-001/002 |
| 5 | Read API — list, retrieve, customer filter, type, expiry | US1 (P1), FR-016–FR-020, FR-023 |
| 6 | Write API — create, patch, archive; placeholder deleted | US3 (P2), FR-002–FR-003, FR-017, FR-021, FR-049 |
| 7 | `HasRole` on every route; full matrix | US5 (P1), FR-024–FR-027, SC-005 |
| 8 | Audit on write; refusal recording live | US4 (P2), FR-028–FR-035, SC-006 |
| 9 | Cross-entity archival guarantees | FR-008, FR-022, SC-008 |

**Stage 3 is sequenced early, before any policy route exists.** The refactor is
a pure behavior-preserving change at that point, verified solely by the
existing customer suite. Doing it later — with policy routes already emitting
refusals — would entangle "did the refactor break customers?" with "is the new
policy behavior right?", and make a regression far harder to localize.

Per Principle V, tests precede implementation within each stage.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Handler refactor regresses shipped customer behavior** | Stage 3 runs before any policy route exists. The 22 existing customer audit tests are the regression suite and must pass **unmodified** — if one needs editing, the refactor is wrong. |
| Uniqueness constraint spanning archived rows would permanently consume a coverage slot | Constraint is `condition=Q(archived_at__isnull=True)`, with a dedicated test: archive a policy, create the same type again, expect 201. |
| `renewal_probability` `CheckConstraint` rejecting NULL via SQL three-valued logic | Written as `isnull=True OR (gte AND lte)`; a test creates a policy with no renewal probability. |
| FK resolved through `Customer.objects` would 404 policies of archived customers | Serializer resolves via `all_objects`; both traversal directions tested separately since they fail independently. |
| Loader half-landing a row (customer written, policy refused) | Policy validation runs before either write, inside one per-row transaction. |
| Loader matching on customer alone would overwrite multi-policy customers | Match key is `(customer, policy_type)`; verified unique across all 3,000 rows. |
| Product Manager role asymmetry (reads policies, not customers) recorded wrongly | Registry carries role sets per module rather than platform-wide. |

## Divergences from Phase 2a — deliberate, not drift

Stated explicitly so a later reviewer does not "correct" them into consistency:

| Aspect | Customer | Policy | Why |
|---|---|---|---|
| Uniqueness vs archived rows | `client_id` reserved **forever** | slot **released** on archive | FR-021 there reserves a reference; here it must not block future coverage |
| External reference | `client_id` (`CL-#####`) | none | The dataset has no policy ID column |
| Write roles | Customer Service + Sys Admin | **Underwriter** + Sys Admin | Policy terms are underwriting work |
| Product Manager read | denied | **allowed** | Product mix is a product concern; personal data is not |
| Loader match key | `client_id` | `(customer, policy_type)` | No policy identifier exists in the source |

## Complexity Tracking

> No Constitution Check violations. This section is intentionally empty.
