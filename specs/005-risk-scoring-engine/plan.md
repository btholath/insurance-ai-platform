# Implementation Plan: Phase 3a — Risk Scoring Engine

**Branch**: `005-risk-scoring-engine` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-risk-scoring-engine/spec.md`

## Summary

Deliver the platform's first computed business decision: a five-factor,
thresholded rules engine that scores a customer's risk from data the platform
already holds, stores the score together with the per-factor reasoning that
produced it, and exposes both through a dedicated read route. Computation is on
demand only — a management command for the book, an explicit trigger for one
customer — with automatic recomputation deferred whole to Phase 3b.

This is the first phase where constitution Principle IV binds; specs 001, 003 and
004 each recorded it *N/A* because no feature produced a decision. The design
satisfies it structurally rather than by narration: the explanation is the stored
arithmetic, not a description of it.

Six decisions carry the design, each recorded in `research.md`:

1. **A new `apps/risk/` app mounted at its own top-level prefix, `/api/risk/`.**
   This is not a stylistic choice, and the alternative was tested rather than
   assumed. The spec's illustrative path `/api/customers/{id}/risk-assessment/`
   falls under the registry's existing `/api/customers/` prefix, so
   `audit_routes.match()` returns the **customer** entry: customer's seven view
   roles, target type `customers.Customer`, action `customer.viewed`. Verified
   against the running app (§1 of research.md). Every risk refusal would be
   audited as a customer refusal, and the five-role risk read set would never be
   consulted — silently, with all tests passing. A distinct prefix is what makes
   the fourth registry entry meaningful (FR-041).

2. **Score is an integer 0–100 on `RiskAssessment`, not the existing
   `Customer.risk_score`.** That column is `DecimalField(max_digits=3,
   decimal_places=2)` — it cannot hold 100, and its DB constraint pins it to
   0.00–1.00. FR-055/FR-056 still require it stop carrying uninterpreted source
   values, so it is **derived from** the assessment as `score/100` and becomes a
   denormalised mirror, never the record of truth (§2).

3. **Assessment and its factor rows are written as one atomic unit** (FR-035),
   with the factor rows fully replaced per computation. A score beside factors
   from a previous run would be an explanation that does not explain, which is
   the precise failure Principle IV exists to prevent.

4. **Staleness is computed on read from timestamps, never stored** (FR-039). A
   stored `is_stale` flag would need something to maintain it, and the only
   honest maintainer is the automatic recomputation this phase excludes — the
   flag would be wrong the moment a policy changed. Deriving it from
   `computed_at` versus the customer's scoring-data timestamps is correct without
   any background work (§4).

5. **`RULE_SET_VERSION` is a module constant, and the rule table is one
   declarative structure** serving both computation and explanation (FR-003,
   FR-004). One source of truth is what makes FR-021's exact-sum guarantee
   structural rather than a coincidence tests must police.

6. **Customers with no live policy are skipped, not scored zero** (FR-018).
   Two of five factors need a policy. Scoring them as zero would assert their
   coverage carries no additional risk — a claim about data the system does not
   have.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15, psycopg 3.2.
**No new dependencies.** Explicitly no Celery, no signals, no scheduler — the
absence is a requirement (FR-036), not an omission.

**Storage**: PostgreSQL 16 — `risk_riskassessment`, `risk_riskfactor`; one
migration in `apps/risk/`, plus one data migration in `apps/customers/` clearing
source-supplied `risk_score` values (FR-056).

**Testing**: pytest 8 + pytest-django + Factory Boy, `--cov` per Principle V.
The scoring engine is business-rule code, so tests precede implementation.

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose

**Project Type**: Django web service, API-only

**Performance Goals**: single assessment retrieval < 1s; batch recompute of the
full 3,000-customer book < 60s, achieved by bulk-loading factors per customer
rather than per-customer queries (target ≤ 5 queries per batch chunk, not ~4 per
customer)

**Constraints**: Local-first (Principle I) — the engine is arithmetic, with no
model, no inference, and no network call. Server-side RBAC on every route
(Principle III). Audit inside the same transaction as every computation
(FR-053). No automatic recomputation of any kind (FR-036). No action taken on a
score (FR-028).

**Scale/Scope**: 3,000 customers → 3,000 assessments and ~15,000 factor rows
(5 per assessment); 3 API routes (list, retrieve, recompute-one) + 1 management
command; 1 registry entry; 5 scoring factors; 4 tiers.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| Principle | Status | How this feature satisfies it |
|---|---|---|
| **I. Local-First** | PASS | Django + PostgreSQL only. The rules engine is integer arithmetic over local rows — no model file, no inference runtime, no network call, no new dependency. Principle I is satisfied more strongly here than a "no cloud calls" reading requires: there is no ML component at all. |
| **II. Auditability by Default** | PASS | Risk is explicitly named in Principle II's scope. Every computation writes an `AuditLog` entry inside the same transaction (FR-048, FR-053), carrying previous and new score; unchanged scores are still recorded (FR-049); a batch run is its own attributable event (FR-050); refusals go through the registry (FR-051); the rule-set version is recorded on every entry (FR-054), which is the "prompt template / model / inputs" analogue for a rules engine. |
| **III. RBAC (NON-NEGOTIABLE)** | PASS | Existing `HasRole` at the view layer on every route (FR-044). Read = 5 roles, recompute = 2 (FR-042, FR-043) — a **narrower** read set than Customer's seven and a distinct write set, which is exactly the per-module divergence the registry exists to record. Non-disclosure preserved on detail routes (FR-045). |
| **IV. Explainable AI Outputs** | **PASS — first phase where it applies** | Specs 001, 003 and 004 each recorded N/A (verified: `001/plan.md:73`, `003/plan.md:65`, `004/plan.md:79`). A risk score is named in the principle's own list of outputs that bind it. Satisfied structurally: the score's contributing factors are persisted rows (FR-020), the explanation is generated from them rather than reconstructed (FR-024), contributions sum exactly to the score (FR-021), and the result is a recommendation with no automatic action (FR-028). The principle's "raw LLM output MUST NOT be the sole record" clause is satisfied vacuously and then some — there is no generation at all, and the structured score-plus-explanation *is* the record of truth. |
| **V. Test-First (NON-NEGOTIABLE)** | PASS | Risk scoring is the first-named example in Principle V's own text. Every band, both sides of every tier boundary, the sum-equals-score invariant, and the skip path are specified as tests before the engine exists (SC-015). Factory Boy supplies the fixtures. |
| **VI. Disposable Prototyping** | N/A | No Phase 0 spike code is involved. |

**Result: PASS.** No violations, so Complexity Tracking stays empty.

### Post-Phase-1 re-evaluation

Re-checked after research, data-model, contracts, and quickstart were written.
Still **PASS**. Three points are worth stating plainly rather than passing
silently:

- **A second model (`RiskFactor`) beyond the spec's headline entity.** It is not
  redundancy: it *is* the Principle IV compliance surface. Storing factors as
  rows rather than as a JSON blob on the assessment is what makes FR-021's
  exact-sum invariant checkable in SQL and makes "which customers were penalised
  for a high claims ratio" a query rather than an application-level scan. The
  alternative was considered and rejected in §3 of research.md.
- **A denormalised `Customer.risk_score` alongside the authoritative
  `RiskAssessment.score`.** Two places holding one fact is normally a smell. It
  is accepted here only because FR-055/FR-056 require the legacy column stop
  carrying source data, and deleting it outright is out of scope for this phase.
  The mirror is written only by the engine, in the same transaction, and the plan
  records `RiskAssessment` as the sole record of truth (§2). Principle II is
  unaffected — the audit entry references the assessment.
- **Principle IV moves from N/A to PASS.** This is the first such transition in
  the project, so the plan states the test for it: if a reviewer can obtain a
  score without also obtaining the factors that produced it, through any route
  this feature adds, the principle is **violated**, not partially met. The
  contracts are written so that no such route exists.

## Project Structure

### Documentation (this feature)

```text
specs/005-risk-scoring-engine/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── risk-assessment-api.md
│   └── computerisk-command.md
├── checklists/
│   └── requirements.md  # existing, from /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/
├── risk/                            # NEW app — the fourth core module
│   ├── __init__.py
│   ├── apps.py                      # NEW: label "risk"
│   ├── models.py                    # NEW: RiskAssessment, RiskFactor, RiskTier
│   ├── rules.py                     # NEW: THE rule set — bands, points,
│   │                                #      thresholds, RULE_SET_VERSION.
│   │                                #      Single source of truth (FR-003).
│   ├── engine.py                    # NEW: pure scoring + persistence entry point
│   ├── serializers.py               # NEW: assessment + nested factor shapes
│   ├── views.py                     # NEW: read routes + recompute trigger
│   ├── urls.py                      # NEW: mounted at /api/risk/
│   ├── factories.py                 # NEW: Factory Boy, per Principle V
│   ├── management/commands/
│   │   └── computerisk.py           # NEW: batch recompute (FR-030)
│   ├── migrations/0001_initial.py   # NEW
│   └── tests/
│       ├── test_rules.py            # NEW: every band, every boundary (SC-015)
│       ├── test_engine.py           # NEW: sum-equals-score, determinism, skips
│       ├── test_models.py           # NEW
│       ├── test_serializers.py      # NEW
│       ├── test_views.py            # NEW
│       ├── test_permissions.py      # NEW: all nine roles × all routes
│       ├── test_staleness.py        # NEW: FR-038 through FR-040
│       ├── test_audit.py            # NEW: FR-048 through FR-054
│       └── test_computerisk.py      # NEW: batch counts, idempotency, isolation
├── core/
│   ├── audit_routes.py              # ONE registry entry added (FR-041)
│   └── tests/test_audit_routes.py   # EDITED: see note below
├── customers/
│   └── migrations/000X_clear_source_risk_score.py   # NEW data migration (FR-056)
└── config/
    ├── settings/base.py             # "apps.risk" added to INSTALLED_APPS
    └── urls.py                      # path("api/risk/", ...) added
```

**Structure Decision**: A new Django app, `apps/risk/`, following the shape of
the three existing core modules. Risk is a first-class BRD module, not an
extension of Customer: it has its own records, its own role sets, its own
lifecycle, and Phase 3b will add background machinery to it. Placing the models
in `apps/customers/` would put risk migrations behind customer migrations
forever and would make the module boundary an accident of where a foreign key
points.

**The route prefix is load-bearing, not cosmetic.** `/api/risk/` is chosen over
the spec's illustrative `/api/customers/{id}/risk-assessment/` for the reason in
Summary §1 and research.md §1: the nested path is swallowed by the existing
`/api/customers/` registry entry, which would mis-audit every risk refusal under
the wrong module, the wrong target type, and the wrong role set. Behaviour the
spec requires (FR-041, FR-042, FR-045, FR-051) is unachievable at the illustrative
path without either a longest-prefix shim per customer id — impossible, since
prefixes are static — or edits to the shared handler that FR-041 forbids. The
spec wrote that path as an example (“e.g.”); this plan takes the requirement and
declines the example, and records why here so the divergence is visible rather
than quiet.

**Note on `apps/core/audit_routes.py`**: as in Phase 2c, this is expected to be a
single `register(...)` call — the fourth consumer, and the fourth consecutive
test of the Phase 2b bet. If implementing risk requires touching
`exception_handlers.py`, that is a **failure of FR-041**, not a routine
adjustment.

**Note on `apps/core/tests/test_audit_routes.py`**: this file needs one edit, and
it is a *predicted* one rather than a surprise. Its
`test_unregistered_path_matches_nothing` currently asserts `/api/risk/1/` matches
nothing (line 34) — it was written using risk as the example of an unclaimed
path, exactly as Phase 2c inherited `/api/claims/1/` and swapped it. The example
must be swapped again (to an unregistered prefix) and the assertion kept intact.
New assertions are added for the risk entry's role sets. This is the registry
test evolving as designed, not the registry failing.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
