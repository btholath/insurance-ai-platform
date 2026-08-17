# Phase 1 Data Model: Risk Scoring Engine

**Feature**: 005-risk-scoring-engine | **Date**: 2026-08-17

Two new models in a new app `apps/risk/`, plus one derived change to an existing
field. Decisions are grounded in [research.md](./research.md); this document
records the shape and the invariants, not the code.

---

## Enumerations

### `RiskTier` (TextChoices)

| Value | Label | Score range |
|---|---|---|
| `low` | Low | 0–19 |
| `moderate` | Moderate | 20–39 |
| `elevated` | Elevated | 40–59 |
| `high` | High | 60–100 |

Thresholds are lower-inclusive, upper-exclusive, with the top band closed — so
every score in 0–100 maps to exactly one tier, with no gap and no overlap
(FR-006, FR-007). The tier is **derived from the score**, never independently
assigned; it is stored so that a tier query is an indexed lookup rather than a
computed filter, and a test asserts stored tier always equals
`tier_for(score)` (FR-006).

### `RiskFactorName` (TextChoices)

| Value | Label |
|---|---|
| `age` | Customer age |
| `policy_type` | Policy coverage type |
| `claims_history` | Claims history |
| `claims_ratio` | Claims-to-premium ratio |
| `denied_claim` | Denied claim present |

Five values, fixed by `rules.py`. The business-facing labels are what FR-025
requires the explanation to read in.

### `FactorStatus` (TextChoices)

| Value | Label | Meaning |
|---|---|---|
| `evaluated` | Evaluated | The factor was assessed; `points` is its real contribution, possibly 0 |
| `not_evaluable` | Not evaluable | Required data absent; `points` is 0 and `unevaluable_reason` states why |

This enum is the whole of FR-018/FR-022/FR-023. A factor that contributed zero is
`evaluated` with `points=0`; a factor that could not be assessed is
`not_evaluable`. Collapsing them would make "this characteristic adds no risk"
indistinguishable from "we do not know", which is the distinction the spec's
edge cases turn on.

---

## `RiskAssessment`

One per customer — the current computed risk and the record of truth (FR-024).

| Field | Type | Notes |
|---|---|---|
| `customer` | `OneToOneField(customers.Customer, on_delete=PROTECT, related_name="risk_assessment")` | One current assessment per customer; `PROTECT` so a customer carrying an assessment cannot be hard-deleted, matching Policy→Customer |
| `score` | `PositiveSmallIntegerField` | 0–100 integer, the authoritative score (§2 of research) |
| `tier` | `CharField(choices=RiskTier)`, `db_index=True` | Derived from `score`; stored for query |
| `rule_set_version` | `CharField(max_length=16)`, `db_index=True` | FR-004, FR-026 — the version in force at computation |
| `computed_at` | `DateTimeField` | FR-027; set explicitly by the engine, **not** `auto_now`, so it means "when this score was computed" rather than "when this row was last touched" |
| `computed_by` | `FK(AUTH_USER_MODEL, null=True, on_delete=SET_NULL, related_name="risk_assessments_computed")` | Null when the batch command runs unattended; `SET_NULL` so removing a user never destroys the assessment |
| `created_at` / `updated_at` | from `TimeStampedModel` | Row lifecycle, distinct from `computed_at` |

**Constraints**

- `CheckConstraint risk_score_range`: `0 <= score <= 100`. Not nullable — an
  assessment without a score is not an assessment, so absence is represented by
  the absence of the row (FR-029), never by a null score.
- `CheckConstraint risk_tier_valid`: `tier IN (...)`. Duplicates `choices` at the
  DB level deliberately, following `claim_status_valid` — `choices` is a
  serializer-layer convention that raw ORM writes bypass.

**Indexes**: `(tier, score)` — serves "show me the high-risk book, worst first",
the primary read query after single retrieval.

**Meta**: `ordering = ["id"]` for stable paging, consistent with all three core
modules.

**Deliberate non-fields**

- **No `is_stale` column.** Derived on read from `computed_at` versus the
  customer's and their policies'/claims' `updated_at` (§4 of research). A stored
  flag has no honest writer in a phase that forbids automatic recomputation, and
  a flag that says "fresh" forever is worse than no flag.
- **No `previous_score`.** The audit entry carries before/after (FR-048); a
  second mutable copy would drift from the append-only record. Same division
  Phase 2c drew between `ClaimLoadAnomaly` and `AuditLog`.
- **No `explanation` text.** The explanation is the `RiskFactor` rows. A prose
  field would be *about* the computation rather than its record (FR-024).

---

## `RiskFactor`

One row per factor per assessment — collectively, the explanation (FR-020).

| Field | Type | Notes |
|---|---|---|
| `assessment` | `FK(RiskAssessment, on_delete=CASCADE, related_name="factors")` | **CASCADE, deliberately** — see below |
| `factor` | `CharField(choices=RiskFactorName)`, `db_index=True` | Which factor |
| `status` | `CharField(choices=FactorStatus)` | `evaluated` or `not_evaluable` |
| `observed_value` | `CharField(max_length=64)` | The customer's actual value, as displayed — e.g. `"23"`, `"Auto"`, `"4.06"`. Text, not typed: the five factors have incompatible types and this field exists to be *shown* (FR-020, FR-025), not computed on |
| `band_label` | `CharField(max_length=64)` | The band that value fell into — e.g. `"under 25"`, `"3–5×"`. The human-readable half of FR-020 |
| `points` | `SmallIntegerField` | The contribution. `0` when the band contributes nothing; `0` when `not_evaluable` |
| `unevaluable_reason` | `CharField(max_length=128, blank=True)` | FR-023. Non-empty **iff** `status="not_evaluable"` |

**`on_delete=CASCADE` is the one place this feature cascades**, against the
platform's `PROTECT` habit, and it is correct here: a factor row has no meaning
apart from its assessment. Orphaned factors would be an explanation of nothing,
and a `PROTECT` here would make recomputation impossible without manual cleanup.
Note this is *not* a data-loss path — assessments are updated in place, never
deleted, in normal operation.

**Constraints**

- `UniqueConstraint(assessment, factor)` — one row per factor per assessment. A
  duplicated factor would double-count in FR-021's sum while looking correct in
  the response.
- `CheckConstraint factor_reason_matches_status`:
  `(status='not_evaluable' AND unevaluable_reason != '') OR (status='evaluated' AND unevaluable_reason = '')`.
  Makes FR-023 a database guarantee — a not-evaluable factor cannot exist without
  its reason, and an evaluated factor cannot carry a spurious one.
- `CheckConstraint factor_points_non_negative`: `points >= 0`. All bands in rule
  set 1.0.0 are non-negative; the field is `SmallIntegerField` rather than
  positive so a future version can express a risk-*reducing* band without a
  migration, while the constraint keeps 1.0.0 honest.

**Indexes**: `(factor, points)` — serves §3's motivating query, "which customers
were penalised for a high claims ratio".

**Meta**: `ordering = ["id"]`.

### The sum invariant (FR-021, SC-001)

> For every assessment: `sum(factors.points) == assessment.score`

This is **not** enforceable as a DB constraint (it spans rows), so it is
guaranteed three ways instead:

1. **Structurally** — `persist()` computes `score` as the sum of the very
   `FactorResult`s it writes, in one transaction. There is no code path that
   derives the score independently of the factors.
2. **By test** — asserted per-assessment in `test_engine.py`, across every
   fixture combination.
3. **By population check** — one aggregate query over all 3,000 assessments in
   quickstart step 6, which is SC-001's verification.

Every assessment always has exactly five factor rows (one per
`RiskFactorName`), including zero-contribution and not-evaluable ones — that is
FR-022 and FR-023, and it makes the sum well-defined.

---

## Changes to existing models

### `customers.Customer.risk_score` — meaning changes, shape does not

**No migration to the field itself.** It stays
`DecimalField(max_digits=3, decimal_places=2, null=True)` with its 0–1 check
constraint. What changes is what writes it and what it means:

| | Before (Phase 2a) | After (this feature) |
|---|---|---|
| Written by | CSV loader, from `Risk_Score` | Risk engine only, as `score / 100` |
| Meaning | Uninterpreted source value | Denormalised mirror of `RiskAssessment.score` |
| Record of truth | — (nothing read it) | **No** — `RiskAssessment.score` is |

Two changes make FR-055 through FR-057 true:

1. **Data migration** in `apps/customers/migrations/` setting `risk_score = NULL`
   for all rows, so no customer carries a source-derived score afterwards
   (FR-056, SC-013). All 3,000 currently do. Reversible as a no-op — the reverse
   cannot restore source values, and should not pretend to.
2. **`loaddataset.py` stops mapping `Risk_Score`** — remove the entry at
   `apps/customers/management/commands/loaddataset.py:81` (FR-057), so a later
   load cannot reintroduce source scores. The CSV column stays in the file and is
   simply ignored, which is the documented behaviour for unmapped columns.

`CustomerSerializer` keeps `risk_score` as a readable field but it becomes
**read-only**: with the engine as sole writer, an API client setting it directly
would create a score with no assessment and no explanation — a black-box score,
which is the one thing Principle IV forbids.

---

## Relationships

```text
Customer ──1:1── RiskAssessment ──1:N── RiskFactor
   │                                      (exactly 5 per assessment)
   ├──1:N── Policy ──1:N── Claim
   │           └─ premium_usd, policy_type      → factors
   │                        └─ claim_amount_usd, claim_status → factors
   └─ age                                        → factor

RiskAssessment.computed_by ──N:1── User   (nullable)
AuditLog ── references assessments by target_type/target_id (no FK, by design)
```

**Live records only** (FR-016): the engine reads `customer.policies` and
`policy.claims` through the **default managers**, which already exclude archived
rows — so archival exclusion falls out of Phase 2b/2c's dual-manager design
rather than needing a filter in the engine. Archived *customers* are excluded by
`Customer.objects` in the batch command's queryset for the same reason.

---

## Lifecycle

An assessment has no state machine — it exists or it does not, and when it exists
it is current-as-of `computed_at`.

```text
(no assessment)
      │  computerisk / POST recompute
      ▼
  assessment v1  ──── customer/policy/claim data changes ────▶ same row, now derived-stale
      │  recompute                                                    │  recompute
      ▼                                                               ▼
  assessment v1' (same row, updated in place; factors fully replaced)
```

- **Never deleted** in normal operation; recomputation updates in place, which is
  what makes FR-033 idempotent.
- **Factors fully replaced** per computation, never merged — a merge could leave
  a factor row from an earlier rule version beside newer ones, breaking the sum.
- **A skipped customer gets no row** (FR-018): a customer with no live policy has
  no assessment at all, which FR-029 makes distinguishable from a low score.

---

## Volumes

| Table | Rows after full load |
|---|---|
| `risk_riskassessment` | 3,000 (every seeded customer has exactly one live policy) |
| `risk_riskfactor` | 15,000 (5 × 3,000) |
| `audit_auditlog` | +3,001 per batch run (3,000 computations + 1 run entry) |

Expected tier distribution, simulated against the seeded data before the rules
were fixed (§5 of research): Low 33.4% · Moderate 32.0% · Elevated 16.9% ·
High 17.7%.
