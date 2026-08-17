# Phase 0 Research: Risk Scoring Engine

**Feature**: 005-risk-scoring-engine | **Date**: 2026-08-17

Every decision below was checked against the running application or the seeded
database rather than reasoned about in the abstract. Where a check produced a
result that changed the design, the command and its output are recorded.

There were **no NEEDS CLARIFICATION markers** in the Technical Context to
resolve: the stack is fixed by the constitution, the three existing core modules
establish every pattern this feature reuses, and the spec settled scope. The
research below therefore addresses design questions the spec deliberately left to
the plan, plus one question whose answer overrides an illustrative detail in the
spec.

---

## §1. Route placement — the nested path is not viable, and this was tested

**Decision**: Mount the risk API at a new top-level prefix `/api/risk/`, in a new
`apps/risk/` app. Do **not** nest it under `/api/customers/{id}/risk-assessment/`
as the spec's example suggested.

**This overrides an illustrative detail in the spec input.** The user wrote
"e.g. GET /api/customers/{id}/risk-assessment/" — an example, not a requirement.
The requirement is FR-019 (a dedicated read operation) plus FR-041 (registry as
fourth consumer), FR-042 (five-role read set), FR-045 (non-disclosure) and FR-051
(refusals recorded). Those cannot all hold at the nested path.

**Why — verified, not assumed.** `audit_routes.match()` selects the *longest
registered prefix* that a path starts with. Registered prefixes are static
strings; `/api/customers/` is already registered. Run against the live app:

```
$ docker compose exec -T web python -c "... audit_routes.match(p) ..."
/api/customers/42/risk-assessment/ -> customers.Customer
/api/risk/assessments/42/          -> None
/api/customers/                    -> customers.Customer
/api/risk/                         -> None
```

The nested path resolves to the **customer** entry. Concretely, that means:

- A refused risk read is audited as `customer.viewed`, not a risk action —
  FR-051 records the wrong thing under the wrong module.
- The refusal-versus-miss test consults customer's **seven** view roles instead
  of risk's **five**. Customer Service is in the customer set and not in the risk
  set, so a refused Customer Service request for a risk assessment would be
  classified an *ordinary miss* and never recorded at all.
- `target_type` is written as `customers.Customer`, so a Compliance Officer
  querying the audit trail for risk activity finds nothing.

None of that raises an error. Every test would pass while the audit trail
silently misattributed an entire module. This is precisely the failure mode the
Phase 2b registry refactor exists to prevent, so shipping it in the registry's
own fourth consumer would be a poor outcome.

**Could a nested route be rescued?** Two options were considered and rejected.
Registering `/api/customers/{id}/risk-assessment/` is impossible — prefixes are
static and the customer id varies, so there is no fixed string to register.
Special-casing the path inside `exception_handlers.py` is explicitly forbidden by
FR-041, and would reintroduce the per-module knowledge Phase 2b removed.

**Alternatives considered**:
- *Nested under customers* — rejected above, on tested evidence.
- *Risk models inside `apps/customers/`, routes at `/api/risk/`* — the registry
  problem is solved, but the module boundary becomes an accident of where a
  foreign key points, and Phase 3b's Celery machinery would land in the customer
  app. Rejected.
- *New `apps/risk/` app at `/api/risk/`* — **chosen**. Matches the BRD's module
  list, matches the three existing core modules, and makes the fourth registry
  entry a genuine per-module divergence (five read roles versus Customer's seven,
  two recompute roles versus Customer's two *different* write roles).

**Consequence for the spec**: no functional requirement changes. FR-019 says
"dedicated read operation", not a specific URL. The contract in
`contracts/risk-assessment-api.md` fixes the real paths.

---

## §2. Score representation — the existing column cannot hold the score

**Decision**: `RiskAssessment.score` is a `PositiveSmallIntegerField`, 0–100, and
is the record of truth. `Customer.risk_score` is retained as a **denormalised
mirror**, written as `score / 100` (2 dp) in the same transaction, never read by
the engine.

**Why**. Verified against the shipped model and migration:

```
apps/customers/models.py:126
    risk_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
apps/customers/models.py:145-149
    CheckConstraint(name="customer_risk_score_range",
                    condition=Q(risk_score__isnull=True) | (Q(risk_score__gte=0) & Q(risk_score__lte=1)))
```

`max_digits=3, decimal_places=2` permits exactly one digit before the point, and
the DB constraint pins the value to 0.00–1.00. It **cannot** store a 0–100 score.
Two ways out:

1. Widen the column and drop the constraint. Rejected: it is a table rewrite plus
   a constraint migration on a shipped, tested field that Phase 2a documented
   deliberately, and it would leave `cross_sell_score` as the odd one out on a
   different scale.
2. Keep the 0–1 column as a derived mirror and put the authoritative integer on
   the new model. **Chosen.**

**Why 0–100 rather than scoring natively on 0–1**: the rule set is additive
integer points (FR-001). Integer arithmetic makes FR-021's *exact* sum guarantee
trivially true; decimal fractions invite rounding, and a rounded remainder is
precisely the "unexplained remainder" FR-021 forbids. The simulation in §5 lands
on a 0–100 scale naturally.

**Why keep the mirror at all**: FR-055 and FR-056 require the legacy column stop
carrying uninterpreted source values and hold only computed values or nothing.
Dropping the field entirely is a larger change than this phase's scope, and
Phase 5's fraud work still reads customer-level scores. The mirror satisfies both
FRs while `RiskAssessment` remains the record of truth. The duplication is called
out against Principle II in the plan's post-Phase-1 re-evaluation rather than
passed silently.

**Handling the existing 3,000 source values**: a data migration in
`apps/customers/` sets `risk_score = NULL` for every row (FR-056), so that after
this feature no customer carries a source-derived score. Confirmed necessary —
all 3,000 rows currently carry one:

```
risk_null | risk_set | min  | max  |  avg
        0 |     3000 | 0.10 | 1.00 | 0.546
```

`loaddataset.py` must also stop mapping `Risk_Score` (FR-057); it currently maps
it at `apps/customers/management/commands/loaddataset.py:81`.

**Evidence the source values are noise** (the basis for replace-rather-than-
preserve): correlation with age 0.0018, with premium 0.0179, with claim amount
0.0036; mean flat across fraud bands (0.544 / 0.559 / 0.535); only 91 distinct
values across 3,000 rows.

---

## §3. Factors as rows, not as a JSON blob

**Decision**: Each factor contribution is a `RiskFactor` row related to the
assessment. Not a `JSONField` on `RiskAssessment`.

**Why**. The JSON option is less code and was seriously considered — Phase 2c
used `JSONField` for audit `before`/`after`, so there is precedent. It was
rejected on three grounds specific to Principle IV:

1. **The sum invariant becomes checkable.** FR-021 requires contributions total
   the score exactly. As rows, that is one aggregate query and a DB-level test
   over all 3,000 assessments (SC-001). As JSON, it is an application-level scan.
2. **Factors become queryable.** "Which customers were penalised for a
   claims-to-premium ratio above 5×" is the question a Risk Manager actually
   asks, and it is Phase 3b/4 input. A row with an indexed `factor` column
   answers it; JSON does not, without a GIN index that costs more than the table.
3. **The non-evaluable case needs structure.** FR-023 requires a factor that
   could not be evaluated appear *marked as such with a reason*, distinct from a
   zero contribution (FR-018, FR-022). That is three states per factor —
   contributed, contributed zero, not evaluable — and giving them typed columns
   makes the distinction enforceable rather than conventional.

**Alternatives considered**: `JSONField` (rejected above); a single denormalised
"explanation" text field (rejected outright — it would make the explanation prose
*about* the computation rather than the computation's own record, which is the
distinction FR-024 draws).

---

## §4. Staleness is derived on read, never stored

**Decision**: `is_stale` is computed at serialization time by comparing the
assessment's `computed_at` against the customer's own `updated_at` and the
`updated_at` of their live policies and claims. No stored flag, no stored
"dirty" bit.

**Why**. A stored flag needs a writer. The only honest writer is something that
observes every change to a customer, policy, or claim — which is exactly the
signal/Celery machinery FR-036 forbids and Phase 3b delivers. A flag written only
at computation time would say "fresh" forever, becoming wrong the moment a policy
changed, and would be *worse than nothing*: FR-039 exists so a stale score is
visibly stale, and a flag that lies is a stronger failure than an absent flag.

Deriving it is correct with no background work: `TimeStampedModel` already gives
every core model `updated_at` (`apps/core/models.py`), so the comparison needs no
new field on Customer, Policy, or Claim. FR-038 is satisfied by machinery that
already exists.

**Cost**: the comparison touches the customer's policies and claims. On the
detail route that is one `select_related`/`prefetch_related` pass; on the list
route it is a prefetch, keeping it off the N+1 path. Measured against 3,000
customers in quickstart step 7.

**Known limitation, recorded deliberately**: `updated_at` moves when *any* field
changes, including fields no factor reads (a customer's phone number, say). So
`is_stale` can report true when the score would not actually change. That is the
safe direction — it over-reports staleness rather than under-reporting it, and a
false "possibly out of date" costs a recompute while a false "current" costs a
wrong decision. FR-039's wording ("MAY be out of date") is satisfied by exactly
this reading. Narrowing it would mean tracking per-field change timestamps, which
is more machinery than the phase warrants.

**Alternatives considered**: stored flag maintained by signals (forbidden by
FR-036, and the whole point of 3b); comparing a hash of the scoring inputs
(correct and precise, but requires computing the inputs on every read — that is
scoring on read, which FR-040 forbids as a side effect and which would make the
stored assessment pointless).

---

## §5. The rule set — five factors, four tiers, validated against 3,000 rows

**Decision**: Five factors summing to a maximum of 100 points, four tiers. The
full table lives in `apps/risk/rules.py` as one declarative structure serving both
the computation and the explanation (FR-003), stamped `RULE_SET_VERSION = "1.0.0"`
(FR-004).

| Factor | Bands (points) | Max |
|---|---|---|
| `age` | under 25: 15 · 25–34: 5 · 35–49: 0 · 50–64: 0 · 65+: 10 | 15 |
| `policy_type` | Auto: 15 · Health: 10 · Property: 5 · Life: 0 | 15 |
| `claims_history` | no claim: 0 · zero-amount claim only: 5 · one or more non-zero: 20 | 20 |
| `claims_ratio` | no non-zero claim: 0 · <1×: 0 · 1–3×: 10 · 3–5×: 20 · ≥5×: 30 | 30 |
| `denied_claim` | none denied: 0 · any denied: 10 | 10 |

Tiers: **Low** 0–19 · **Moderate** 20–39 · **Elevated** 40–59 · **High** 60–100.

**Boundary convention** (FR-007, the edge case the spec raises about age 25):
every band is `lower <= value < upper`, lower-inclusive and upper-exclusive, with
the top band closed. Age exactly 25 falls in `25–34`, never in `under 25`. Tier
thresholds are lower-inclusive on the same rule, so 20 is Moderate and 19 is Low.
Stated once here and encoded once in `rules.py`.

**Validated against the real seeded data before being adopted.** Simulated in SQL
over all 3,000 customers:

```
    tier    | count | pct  | min | max
 1 Low      |  1003 | 33.4 |   0 |  15
 2 Moderate |   959 | 32.0 |  20 |  35
 3 Elevated |   507 | 16.9 |  40 |  55
 4 High     |   531 | 17.7 |  60 |  90
```

Every tier clears SC-005's 5% floor. Observed range 0–90 of a possible 100, so
the scale is exercised without saturating. This is why SC-005 was written as an
achievable criterion rather than an aspiration.

**Multiple policies** (FR-008): the seeded export has exactly one policy per
customer (verified: `policies_per_customer = 1` for all 3,000), but the model
permits many. The rule is stated rather than left to the data's shape:
`policy_type` takes the **highest-scoring live policy type**, and `claims_ratio`
uses **total non-zero claim amounts over total premium across all live policies**.
Worst-case for coverage type, aggregate for the ratio — both stated in `rules.py`
and covered by a multi-policy test even though no seeded row exercises it.

**Rejected factors, with the measurement that rejected them**: gender
(1,042/998/960 — near-uniform, and a protected characteristic);
lead_source (770/747/746/737 — near-uniform, no causal link to claim risk);
`fraud_risk_flag` (Phase 5's field, itself uninterpreted source data, and flat
against the source risk score at 0.544/0.559/0.535). All three would pad the
explanation with noise, working against the purpose of explaining. FR-017 makes
the exclusion a requirement.

---

## §6. On-demand computation — three entry points, one engine

**Decision**: One pure function computes, one persistence function writes, three
callers invoke them: the management command, the API trigger, and tests.

```
rules.py   evaluate(customer_data) -> [FactorResult]   # pure, no ORM
engine.py  score_customer(customer) -> AssessmentResult # reads ORM, no writes
engine.py  persist(customer, result, actor) -> RiskAssessment  # atomic write + audit
```

**Why split pure evaluation from persistence**: it makes SC-004's determinism and
FR-002's repeatability testable without a database, and it makes the band tests
(SC-015, every band and both sides of every boundary) fast unit tests rather than
DB round-trips. It also means Phase 3b can call the same `persist()` from a Celery
task without reimplementing anything — the whole point of keeping 3a's boundary
clean.

**Atomicity** (FR-035, FR-037): `persist()` runs in `transaction.atomic()`,
selects the customer `FOR UPDATE`, deletes the previous factor rows, inserts the
new set, updates the assessment, mirrors `Customer.risk_score`, and writes the
audit entry — all or nothing. The row lock resolves the spec's concurrent-recompute
edge case: two simultaneous recomputes serialize, and neither can produce a score
from one run beside factors from another. `select_for_update()` also gives FR-037
its consistent snapshot.

**Idempotency** (FR-033): `RiskAssessment` is one-per-customer
(`OneToOneField`), so re-running updates in place rather than accumulating. Same
data in, same score out, same factor rows out — the audit trail is where run
history accumulates, which is the same division Phase 2c drew between
`ClaimLoadAnomaly` (reconciled state) and `AuditLog` (immutable history).

**Batch performance**: naive per-customer scoring is ~4 queries × 3,000 = 12,000
round trips. The command instead iterates in chunks with
`select_related("...")`/`prefetch_related` over policies and claims, and uses
`bulk_create` for factor rows. Target < 60s for the full book, asserted in
quickstart step 5.

**Batch audit** (FR-050): one `risk.batch_computed` entry for the run, plus one
`risk.computed` entry per customer. The run entry carries counts in `context`,
making it distinguishable from the individual computations within it.

**Batch failure** (spec edge case, FR-032): each customer is its own transaction,
so a failure partway leaves already-scored customers with complete, valid
assessments and never a partial one. The command reports the failure and
continues.

---

## §7. Roles — a genuine fourth divergence

**Decision**:

```
VIEW_ROLES      = Risk Manager, Underwriter, Fraud Analyst,
                  Compliance Officer, System Administrator      (5)
RECOMPUTE_ROLES = Risk Manager, System Administrator            (2)
```

**Why this is the registry's point, not a formality**. Set against the three
shipped modules:

| Module | View roles | Write roles |
|---|---|---|
| Customer | 7 | Customer Service, Sys Admin |
| Policy | 8 | Underwriter, Sys Admin |
| Claim | 5 | Claims Adjuster, Sys Admin |
| **Risk** | **5 (a different five)** | **Risk Manager, Sys Admin** |

Risk shares Claim's *count* but not its *membership*: Risk admits Underwriter and
excludes Claims Adjuster; Claim does the reverse. And the write set is a fourth
distinct one. The sharp case this entry exists to get right: **Customer Service
may read a customer but not that customer's risk assessment**, so their 404 on a
risk assessment is a refusal while their 404 on the customer is an ordinary miss.
Only a per-module role set distinguishes those, and only a distinct route prefix
lets the registry reach the risk set at all (§1).

Recompute is narrower than read because it rewrites the record of a decision: an
Underwriter may consult an assessment without being able to change one.
Executive Leadership and Product Manager are excluded, consistent with every
prior module.

---

## §8. What is deliberately not built

Recorded so `/speckit-tasks` does not generate work for it, and so Phase 3b's
boundary stays legible:

- **No Celery, no signals, no scheduler, no `post_save` hook** (FR-036). The
  absence is testable: a test asserts that saving a customer, policy, or claim
  leaves the stored score unchanged (SC-011).
- **No recompute-on-read.** FR-040 requires a stale assessment return its stored
  values; the read path performs no writes at all.
- **No score history table.** The current assessment plus the audit trail is the
  record. Time-series risk analytics is a reporting-phase concern, and the audit
  entries already carry before/after scores for anyone reconstructing a series.
- **No runtime rule configuration.** `rules.py` is code with a version constant;
  an admin UI for bands is out of scope.
- **No `RiskFactor` write API.** Factors are engine output, never user input.
- **No action on a score** (FR-028) — nothing declines, prices, flags, or
  notifies.
