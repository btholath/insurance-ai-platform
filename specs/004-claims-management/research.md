# Phase 0 Research: Claims Management

**Feature**: `004-claims-management` | **Date**: 2026-08-12

No Technical Context unknowns remained after the spec: the stack is fixed by the
constitution, and Phases 1, 2a, and 2b already settled the mechanisms this
feature reuses. What follows resolves the genuinely open *design* questions —
the ones where the spec states a requirement and the implementation still has a
real choice to make.

Every decision is grounded in code already in this repository, or in the source
dataset verified directly.

---

## 1. Uniqueness: none, and why that is not an oversight

**Decision**: `Claim` carries **no unique constraint of any kind**. Not on
`(policy, status, amount)`, not live-scoped, not reserved. The primary key is
the only identity a claim has.

**Rationale**: the spec's input asked this be worked out explicitly rather than
assumed, because Policy faced a hard version of the question in Phase 2b. The
answer is that Policy's question does not arise here.

Policy needed a live-scoped-versus-reserved decision because
`(customer, policy_type)` is a **real business constraint** — a customer cannot
hold two live auto policies — so archival had to either release the slot or
reserve it. Phase 2b chose release (`policy_unique_live_type_per_customer`,
`apps/policies/models.py:91`), deliberately opposite to Customer, where an
archived `client_id` stays reserved forever.

Claims have no equivalent. The dataset carries no claim identifier column, and
nothing else identifies a claim naturally:

- `(policy, status, amount)` is not unique **in principle**. A policyholder can
  legitimately file two separate claims for the same amount and have both
  approved. A constraint over those fields would refuse the second one — a
  correctness bug that manifests only in production data, since this export
  cannot produce it.
- There is no date column specific to a claim, so not even
  `(policy, status, amount, date)` is available as a tiebreaker.

Since there is no constraint, **archival cannot release or reserve anything**,
and the live-versus-reserved question is moot rather than answered either way.

**Verified against the dataset**: every `Client_ID` appears exactly once and all
3,000 `(Client_ID, Policy_Type)` pairs are distinct, so this export yields at
most one claim per policy. That is a property of *this file*, not of the
business — which is why FR-003 requires the model permit many claims per policy
even though the seed data never exercises it.

**Alternatives considered**:

- *`unique_together` on `(policy, status, amount)`* — rejected: refuses a valid
  second claim, as above.
- *A synthetic `claim_reference` like Customer's `client_id`* — rejected: it
  would be invented by us, not carried from the source, so it identifies nothing
  the business recognizes and gives the loader no better idempotency key than
  the policy FK already provides (§3).

---

## 2. Loader reconciliation: match a row's claim on its policy

**Decision**: on re-run, the loader matches a row's claim by **`policy`, among
live rows**, via `Claim.objects.filter(policy=policy).first()`.

**Rationale**: the file gives the loader no claim identifier, so it must derive
one. The policy is the only stable handle the row has — and it is sound *for
this export specifically* because the export carries at most one claim per
policy (verified in §1). This mirrors the loader's existing policy matching,
which resolves `(customer, policy_type)` among live rows only
(`loaddataset.py:248`).

**The limitation is real and must be recorded rather than discovered later**: if
a future export carries two claims for one policy, this rule reconciles both
onto the first record and the second silently overwrites it. That is not a
defect in *this* implementation — it is the correct behavior for a file with no
claim identifier — but it is a landmine for whoever extends the loader.
`data-model.md` and the loader docstring both state it, and it belongs in the
contract for the command rather than in tribal memory.

**Matching through `objects`, not `all_objects`**: deliberately the same choice
the policy matcher makes, and for the same reason — a load after an archival
should create a fresh claim rather than resurrect a deliberately removed one.
This is the *opposite* of the customer matcher, which uses `all_objects`
(`loaddataset.py:163`) because FR-021 there reserves the reference forever. Three
managers, three different rules, each justified by its own requirement; a test
pins each so none is later "harmonized" into consistency.

---

## 3. Where anomalies live: a dedicated reconciled model, not `AuditLog`

**Decision**: a new `ClaimLoadAnomaly` model, **one row per policy**, reconciled
in place on each load — *plus* a system-attributed `AuditLog` entry alongside it.

**Rationale**: the user offered two mechanisms and both were evaluated.

**`audit_routes.py` — rejected.** That registry maps URL path prefixes to
per-module role sets so the shared refusal handler can tell a refusal from an
ordinary miss (`AuditedRoute(prefix, target_type, action_prefix, view_roles,
write_roles)`). Every field is request-shaped. A load-time anomaly has no
request, no path, no actor, and no refusal — using it would mean inventing a
fake route prefix for something that is never routed.

**The underlying `AuditLog` — rejected, for a stronger reason.** It is strictly
append-only, enforced in three places: `AuditLogQuerySet.update`/`delete` raise
`NotImplementedError`, `AuditLog.save()` raises if `pk is not None`, and
`AuditLog.delete()` raises (`apps/audit/models.py:5-55`). That is correct for an
audit trail and fatal for this use: 390 fresh rows would accumulate on **every**
load, so a Phase 4 query for "how many policies had inconsistent claim data"
would be wrong by a factor of the number of runs. FR-043 forbids exactly this,
and SC-012 makes it testable.

**A dedicated model satisfies both requirements at once**, because the load is
already idempotent by construction (FR-035) and an anomaly reconciles on the same
key its policy does.

**Why keep an audit entry too**: because the reconciled row holds only *current*
state. FR-048a needs the clearing history, and history is precisely what an
append-only table is for. The two records are complementary, not redundant — the
spec's Key Entities section names the distinction, and §4 explains why it becomes
load-bearing.

**Alternatives considered**:

- *A JSON column on `Policy`* — rejected: makes "find every anomaly" a JSON scan
  instead of an indexed FK lookup, and puts claim-adjacent financial detail on a
  record readable by Product Manager, who may not read claims (FR-047).
- *Console/log output only* — rejected outright by FR-041; unavailable to Phase 4
  and lost when the terminal closes.

---

## 4. Clearing an anomaly: two reasons, stored distinctly

**Decision**: `ClaimLoadAnomaly` carries a `status` of `open` / `cleared`, and
when cleared, a `cleared_reason` of **`corrected`** or **`absent`**. Every
clearing also writes an `AuditLog` entry whose action names the reason —
`claim_anomaly.cleared_corrected` or `claim_anomaly.cleared_absent`.

**Rationale**: FR-044 distinguishes two situations that are *not* the same
evidence:

| Reason | What the load observed | Evidence value |
|---|---|---|
| `corrected` | Row present, status and amount now agree | Positive — the resolution was seen |
| `absent` | Row did not appear at all | **None** — neither persistence nor resolution was seen |

An export can drop a row for reasons unrelated to the conflict: filtered,
truncated, scoped to a date window, or the row withdrawn. Recording both as
"resolved" would let a Phase 4 query count unexplained disappearances as verified
corrections — understating source inconsistency, invisibly, and in the one
direction an anomaly signal must not err.

**Why the audit entry is load-bearing rather than decorative** (FR-048a): the
anomaly row holds only the *latest* clearing reason. A row that is cleared as
`absent`, conflicts again (FR-044b re-raises it to `open`), and is later cleared
as `corrected` overwrites its own history. The append-only trail is then the only
place both clearings survive. This is why FR-048a specifies a *distinct recorded
value* rather than prose: a Phase 4 consumer must be able to filter on it.

**Implementation shape**: clearing is a bulk operation at the end of a load —
every `open` anomaly whose policy was not re-observed as conflicting this run
gets cleared, with the reason chosen by whether that policy appeared in the file
at all. This requires the loader to track two sets per run: policies seen, and
policies observed conflicting. `dry_run` computes both and writes neither
(FR-046).

**Alternative considered**: *a single `cleared_at` timestamp with no reason* —
this is what the spec said before the 2026-08-12 revision, and it is exactly the
conflation FR-044a now forbids.

---

## 5. `No Claim` handling, and why an anomaly is not an inference

**Decision**: a `No Claim` row produces **no `Claim` record**. Where its amount
is non-zero, it additionally produces a `ClaimLoadAnomaly`. Neither outcome is a
refusal — the row's customer and policy load normally (FR-045).

**Rationale**: storing `No Claim` as a claim would mean 754 rows asserting the
existence of a claim whose status denies it exists, and would corrupt every later
count and fraud signal — "how many claims does this policy have" would answer 1
for a policy with none. The absence of a claim is represented by the absence of a
record.

**Verified against the dataset** (`data/Insurance_Dataset.csv`, 3,000 rows):

| Fact | Value |
|---|---|
| Status distribution | Approved 769, No Claim 754, Filed 749, Denied 728 |
| Blank claim cells | 0 |
| Amount range (all rows) | 0.00 – 19,988.98 |
| Rows at exactly 0.00 | 1,507 |
| Negative amounts | 0 |
| `No Claim` rows | 754 — of which **390 carry a non-zero amount** |
| Non-zero `No Claim` amount range | **8.52 – 19,919.13** |
| Distinct policies among the 390 | 390 (one anomaly per policy) |

Expected load outcome: **2,246 claims** (3,000 − 754) and **390 anomalies**.

**On Principle IV (Explainable AI)**: an anomaly is *not* an inference and this
distinction matters for Phase 4. The record asserts only "the source said X and Y,
which contradict." It never asserts a claim occurred, never estimates what the
amount meant, and never scores anything. Principle IV is therefore genuinely N/A
rather than narrowly escaped — but a future phase that turns anomalies into a
fraud *signal* will be generating an inference, and Principle IV binds there. The
anomaly record deliberately stores the raw conflicting values so that phase can
explain itself from source facts.

---

## 6. Amounts: `Decimal`, and zero is not null

**Decision**: `claim_amount_usd` is `DecimalField(max_digits=10,
decimal_places=2)`, **not null**, with a `>= 0` check constraint.

**Rationale**: currency needs exact representation, so never `float` — the same
reasoning as `Policy.premium_usd` (`apps/policies/models.py:53`). Width matches
Policy's at 99,999,999.99, far above the observed 19,988.98, because widening a
numeric column later is a table rewrite.

The `>= 0` bound differs from Policy's `> 0` deliberately: FR-011 requires zero
be **accepted** and stay distinguishable from absent, and 1,507 rows carry
exactly 0.00. Reusing Policy's positive-only constraint would refuse half the
dataset. `null=True` is *not* used, which is the other half of FR-011 — a claim
that exists always has an amount, and nullable would make "0.00" and "unknown"
collapse in every later aggregate.

---

## 7. RBAC: five read roles, two write roles

**Decision**:

```python
VIEW_ROLES  = (CLAIMS_ADJUSTER, FRAUD_ANALYST, COMPLIANCE_OFFICER,
               RISK_MANAGER, SYSTEM_ADMINISTRATOR)
WRITE_ROLES = (CLAIMS_ADJUSTER, SYSTEM_ADMINISTRATOR)
```

**Rationale**: FR-026 names the work that requires claim visibility — claim
handling, fraud investigation, compliance review, risk management, system
administration. That is five roles, and it is **narrower than both prior
modules**: Customer allowed seven readers, Policy eight. Claim amounts are
financial detail about an individual, so Product Manager (product mix, not
individuals), Customer Service, and Underwriter are excluded.

This is a third distinct role set, which is precisely why the Phase 2b registry
stores them **per module** rather than platform-wide. Underwriter is the sharp
case: they *write* policies (`apps/policies/views.py:40`) but cannot even read
claims — so an Underwriter's 404 on a claim is a **refusal**, while the same
user's 404 on a policy is an ordinary miss. A shared role set would necessarily
record one of those wrongly.

Anomalies inherit `VIEW_ROLES` exactly (FR-047), since an anomaly discloses
claim-adjacent financial detail. They are read-only through the API — nothing
creates or edits an anomaly by hand; the loader is the only writer.

---

## 8. FR-030: registering claims must be data entry, not code

**Decision**: the entire refusal-auditing change is one `register(...)` call
appended to `audit_routes.register_defaults()`:

```python
register(AuditedRoute(
    prefix="/api/claims/",
    target_type="claims.Claim",
    action_prefix="claim",
    view_roles=VIEW_ROLES,    # the five above
    write_roles=WRITE_ROLES,  # the two above
))
```

**Rationale**: Phase 2b justified the registry refactor on the explicit
prediction that Claims would be its third consumer and would need no handler
change. FR-030 and SC-008 turn that prediction into a requirement, so it can
*fail*. The verification is concrete and belongs in the task list: after
implementation, `git diff` on `apps/core/exception_handlers.py` must be empty.

**One wrinkle worth flagging before implementation.** `match()` selects the
longest matching prefix (`audit_routes.py:64-73`), so `/api/claims/` and a
future `/api/claims/anomalies/` would both match an anomaly request, with the
more specific entry winning. The anomaly routes are nested under the claims
prefix and share its role sets, so a single `/api/claims/` entry covers both
correctly and **no second registration is needed**. If anomalies later diverge in
roles, a second entry is the mechanism — which is the registry working as
designed, not a workaround.

---

## 9. Removing the placeholder (FR-049)

**Decision**: delete `PlaceholderView` from `apps/claims/views.py`, replace
`apps/claims/urls.py` with the router, and replace the placeholder's test.

**Rationale**: FR-049 requires one claims surface, not two. The placeholder
currently answers `GET /api/claims/placeholder/` with
`{"module": "claims", "status": "placeholder"}` and permits
`CLAIMS_ADJUSTER, FRAUD_ANALYST, SYSTEM_ADMINISTRATOR` — note this is *not* the
final role set (§7 adds Compliance Officer and Risk Manager for reads and drops
Fraud Analyst from writes), so the placeholder's permissions must not be copied
forward by habit.

`apps/claims/tests/test_views.py` currently asserts the placeholder's behavior
and will fail once it is removed. That is correct and expected: the task list
replaces the file rather than deleting the assertions, so claims never has an
untested route.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| 1 | Uniqueness | None. Live-vs-reserved is moot, not answered |
| 2 | Loader match key | `policy`, live rows only; single-claim-per-export limitation documented |
| 3 | Anomaly storage | Dedicated reconciled model + audit entry; not `AuditLog`, not the route registry |
| 4 | Clearing | Two distinct reasons (`corrected` / `absent`), reason recorded in the append-only trail |
| 5 | `No Claim` | No claim record; anomaly when amount non-zero; not a refusal |
| 6 | Amount | `Decimal(10,2)`, not null, `>= 0` — zero is data |
| 7 | RBAC | 5 read / 2 write — narrower than Customer or Policy |
| 8 | Registry | One `register()` call; empty diff on the handler is the test |
| 9 | Placeholder | Removed; role set deliberately not inherited |
