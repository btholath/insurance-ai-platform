# Implementation Plan: Phase 2c — Claims Management

**Branch**: `004-claims-management` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-claims-management/spec.md`

## Summary

Replace Phase 1's placeholder claims endpoint with a real `Claim` model and full
CRUD API, extend the dataset loader to seed claims alongside the customers and
policies it already creates, and retain the source data's 390 self-contradicting
rows as queryable anomalies rather than dropping them.

The approach mirrors Phase 2b wherever the requirement is the same — dual
managers, serializer-as-single-definition-of-validity, audit inside the write
transaction, registry-driven refusal auditing — and diverges where the domain
genuinely differs. Four decisions carry the design:

1. **No uniqueness constraint at all** (FR-007). Policy needed a
   live-scoped-versus-reserved decision because `(customer, policy_type)` is a
   real business constraint. Claims have no natural key: two identical claims
   against one policy are legitimately distinct events, so the correct
   constraint is none, and the live-versus-reserved question is *moot* rather
   than answered either way. This is the question the spec's input asked be
   worked out explicitly; §1 of research.md records the reasoning.
2. **The registry addition is data entry, not code.** Registering claims in
   `audit_routes.register_defaults()` is the whole change to refusal auditing.
   FR-030 and SC-008 make the Phase 2b prediction falsifiable, and this plan
   treats "no handler edit" as a testable outcome, not an aspiration.
3. **A second model, `ClaimLoadAnomaly`, keyed one-per-policy.** The 390
   mismatches must survive as structured signal (FR-041) without fabricating
   claims. It cannot live in `AuditLog` — that table is append-only by design,
   so 390 fresh rows per run would inflate a Phase 4 count by the number of
   loads. A reconciled record satisfies FR-043's idempotency; the audit trail
   carries the immutable history alongside it.
4. **Clearing an anomaly records *why*.** FR-044's two reasons — `corrected`
   versus `absent` — are stored distinctly, because collapsing them would let a
   later phase count unexplained disappearances as verified corrections. The
   anomaly row holds only the latest clearing, so FR-048a's audit entry is where
   the full clearing history survives (§4 of research.md).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15, psycopg 3.2.
**No new dependencies.**

**Storage**: PostgreSQL 16 (`claims_claim`, `claims_claimloadanomaly`; one
migration in `apps/claims/`)

**Testing**: pytest 8 + pytest-django + Factory Boy, `--cov` per Principle V

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose

**Project Type**: Django web service, API-only

**Performance Goals**: single retrieval < 1s; a policy-filtered or
status-filtered claim list < 2s against ~2,246 claims

**Constraints**: Local-first (Principle I). Server-side RBAC on every route
(Principle III). Audit in the same transaction as every write (FR-034). Source
CSV stays out of the repository. No adjudication, no scoring, no state machine —
status is a recorded fact (FR-024).

**Scale/Scope**: ~2,246 claims and 390 anomalies from 3,000 rows; 5 claim API
routes + 1 read-only anomaly route; 1 further-extended management command; the
dataset's claim columns now consumed, completing Phase 2.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this feature satisfies it |
|---|---|---|
| **I. Local-First** | PASS | Django + PostgreSQL only. No new dependency, no network call, no cloud service. |
| **II. Auditability by Default** | PASS | Claim is a core-domain entity, so every create/amend/remove writes an `AuditLog` entry inside the same transaction (FR-029, FR-034), reusing `record_action`. Refusals are recorded via the registry (FR-031). Anomaly clearing writes a system-attributed entry naming the reason (FR-048, FR-048a). No AI output in this phase. |
| **III. RBAC (NON-NEGOTIABLE)** | PASS | Every route uses the existing `HasRole` at the view layer (FR-025). Read = 5 roles, write = 2 (FR-026, FR-027); anomalies inherit the claim read set (FR-047). Non-disclosure on detail routes (FR-028). SC-005 requires a full pass over all nine roles. |
| **IV. Explainable AI Outputs** | N/A | This feature generates no AI output. A `ClaimLoadAnomaly` is an observation copied from the source, never an inference — §5 of research.md records why that distinction is load-bearing for Phase 4. |
| **V. Test-First (NON-NEGOTIABLE)** | PASS | Validation, role enforcement, audit writing, and load reconciliation are business rules, so tests precede implementation (SC-009). The anomaly lifecycle — raise, clear-as-corrected, clear-as-absent, re-raise — is the highest-value test surface here and is specified before code. CRUD boilerplate still requires tests before merge. |
| **VI. Disposable Prototyping** | N/A | No Phase 0 spike code is involved. |

**Result: PASS.** No violations, so Complexity Tracking stays empty.

### Post-Phase-1 re-evaluation

Re-checked after data-model, contracts, and quickstart were written. Still PASS.
The design added one model beyond the spec's headline entity
(`ClaimLoadAnomaly`), which is worth stating plainly against Principle II rather
than passing silently: it does **not** weaken the audit trail or duplicate it.
`AuditLog` remains the immutable history of actions; the anomaly table is
current, reconciled state. The two are complementary and the spec names the
distinction (Key Entities). The anomaly table is also the reason FR-048a exists
— because reconciled state cannot carry its own history, the append-only trail
must.

## Project Structure

### Documentation (this feature)

```text
specs/004-claims-management/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── claims-api.md
│   ├── claim-anomalies-api.md
│   └── loaddataset-command.md
├── checklists/
│   └── requirements.md  # existing, from /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/
├── claims/                          # EXISTS as Phase 1 placeholder; becomes real
│   ├── apps.py                      # unchanged (label "claims" already set)
│   ├── models.py                    # NEW: Claim, ClaimLoadAnomaly, managers
│   ├── serializers.py               # NEW: single definition of claim validity
│   ├── views.py                     # REPLACES PlaceholderView (FR-049)
│   ├── urls.py                      # REPLACES placeholder route (FR-049)
│   ├── factories.py                 # NEW: Factory Boy, per Principle V
│   ├── migrations/0001_initial.py   # NEW
│   └── tests/
│       ├── test_models.py           # NEW
│       ├── test_serializers.py      # NEW
│       ├── test_views.py            # REPLACES placeholder test
│       ├── test_permissions.py      # NEW
│       ├── test_relationships.py    # NEW: policy archival / PROTECT
│       ├── test_anomalies.py        # NEW: raise / clear / re-raise lifecycle
│       └── test_audit.py            # NEW
├── core/
│   └── audit_routes.py              # ONE registry entry added (FR-030)
└── customers/management/commands/
    └── loaddataset.py               # EXTENDED: third record + anomaly handling
```

**Structure Decision**: Existing Django app layout, unchanged. `apps/claims/`
already exists and is already in `INSTALLED_APPS` (`config/settings/base.py:38`)
with its URLs mounted at `/api/claims/` (`config/urls.py:11`), so this feature
fills in an app rather than scaffolding one. The loader stays in
`apps/customers/management/commands/loaddataset.py` rather than moving: it is one
command reading one file, and splitting it per module would need a fourth place
to coordinate row-level atomicity across three records.

**Note on `apps/core/audit_routes.py`**: this is the only shipped, tested file
outside `apps/claims/` that this feature edits, and the edit is a single
`register(...)` call. If implementing claims requires touching
`exception_handlers.py`, that is a **failure of FR-030/SC-008**, not a routine
adjustment — the Phase 2b registry refactor was justified on exactly this
prediction.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
