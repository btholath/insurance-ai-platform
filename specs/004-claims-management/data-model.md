# Phase 1 Data Model: Claims Management

**Feature**: `004-claims-management` | **Date**: 2026-08-12

Two new entities, and the existing entities this feature touches.

---

## Claim (new) — `apps/claims/models.py`

Inherits `apps.core.models.TimeStampedModel` for `created_at` / `updated_at`
(FR-005), exactly as Customer and Policy do.

### Fields

| Field | Type | Null | Constraints / notes | Requirement |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | The **only** identity a claim has. No external reference field, no natural key — see "Uniqueness" below | FR-006, FR-007 |
| `policy` | `FK(Policy)` | **no** | `on_delete=PROTECT`, `related_name="claims"`, `db_index` | FR-002, FR-009 |
| `claim_status` | `CharField(16)` | no | choices: `Approved`, `Denied`, `Filed`; `db_index` for the status filter | FR-001, FR-010 |
| `claim_amount_usd` | `DecimalField(10,2)` | **no** | must be `>= 0`; zero is a legitimate value | FR-001, FR-011 |
| `archived_at` | `DateTimeField` | **yes** | null = live; set = removed | FR-021 |
| `created_at` / `updated_at` | `DateTimeField` | no | from `TimeStampedModel` | FR-005 |

### `ClaimStatus` choices — three values, not four

```python
class ClaimStatus(models.TextChoices):
    APPROVED = "Approved", "Approved"
    DENIED   = "Denied",   "Denied"
    FILED    = "Filed",    "Filed"
```

`No Claim` is **deliberately absent from the choices**. The source dataset has
four status values, but the fourth describes the *absence* of a claim, so it can
never be a stored claim's status (FR-004). Making it unrepresentable in the model
is what enforces FR-012 at the deepest layer: a `No Claim` submission fails the
`ChoiceField` before any hand-written validator runs, and the DB check constraint
catches anything bypassing the serializer.

This is the single most consequential modeling decision in the feature. Including
`No Claim` in the choices would make FR-004 a runtime convention that any future
code path could violate silently.

### Uniqueness — none, deliberately

No `UniqueConstraint`, no `unique_together`, and therefore **no live-scoped
versus reserved question**. Research §1 records the full reasoning; the short
form: `(policy, claim_status, claim_amount_usd)` is not unique in principle,
because two identical claims against one policy are legitimately distinct events,
and a constraint over those fields would refuse the valid second one.

Contrast with the two prior modules, all three of which are correct:

| Module | Key | Archival behavior |
|---|---|---|
| Customer | `client_id` | **Reserved** forever (FR-021 there) |
| Policy | `(customer, policy_type)`, live-scoped | **Released** on archive |
| **Claim** | **none** | **Not applicable** — nothing to release or reserve |

### On `PROTECT` — the constraint runs in the opposite direction from Policy's

`Policy.customer` uses `PROTECT` so a customer cannot be hard-deleted out from
under its policies. `Claim.policy` uses it for FR-009, which is the same
mechanism pointed the other way: a policy carrying claims cannot be destroyed.

FR-008 is the complement and is satisfied *without* extra code: archiving a
policy sets `Policy.archived_at` and does not touch its claims, so claims stay
readable and keep their link. The FK is to the row, not to its live-ness.

**One consequence needs care in the view layer.** `Claim.objects` filters on
`archived_at` for the *claim*, not the policy. A live claim against an archived
policy therefore stays visible — which is exactly what FR-008 requires, and is
the opposite of the instinct to hide it. `select_related("policy")` must resolve
the policy through the FK (which ignores the default manager) rather than a
separate `Policy.objects` lookup that would drop archived rows.

### Meta

```python
class Meta:
    ordering = ["id"]                       # FR-017 stable paging
    constraints = [
        models.CheckConstraint(
            name="claim_amount_non_negative",
            condition=models.Q(claim_amount_usd__gte=0),
        ),
        models.CheckConstraint(
            name="claim_status_valid",
            condition=models.Q(claim_status__in=["Approved", "Denied", "Filed"]),
        ),
    ]
    indexes = [
        models.Index(fields=["policy", "claim_status"]),
    ]
```

`gte=0`, not `gt=0` — this is the deliberate divergence from
`policy_premium_positive` (`apps/policies/models.py:74`). 1,507 of 3,000 rows
carry exactly 0.00, so a positive-only constraint would refuse half the dataset.
FR-011 requires zero be accepted and stay distinguishable from absent, which is
also why the column is **not** nullable.

`claim_status_valid` duplicates the `choices` enforcement at the DB level on
purpose: `choices` is a serializer/form-layer convention that raw ORM writes
bypass, and FR-004's integrity is worth a constraint the database itself holds.

### Managers — the established dual pattern

```python
objects = ClaimManager()        # declared FIRST -> stays _default_manager
all_objects = models.Manager()
```

`ClaimManager.get_queryset()` filters `archived_at__isnull=True`, so FR-021's
invisibility and FR-028's non-disclosure both fall out of the manager rather than
needing a branch in every handler — identical to `PolicyManager`
(`apps/policies/models.py:32`).

---

## ClaimLoadAnomaly (new) — `apps/claims/models.py`

A retained observation that a source row contradicted itself. **Not a claim, and
never evidence that one occurred** (FR-041, FR-042).

### Fields

| Field | Type | Null | Constraints / notes | Requirement |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | | |
| `policy` | `FK(Policy)` | **no** | `on_delete=PROTECT`, `related_name="claim_load_anomalies"`, **`unique=True`** | FR-042, FR-043 |
| `source_status` | `CharField(16)` | no | the conflicting status **as supplied** — free text, not `ClaimStatus` choices | FR-042 |
| `source_amount_usd` | `DecimalField(10,2)` | no | the conflicting amount as supplied | FR-042 |
| `status` | `CharField(8)` | no | `open` \| `cleared`; default `open`; `db_index` | FR-044 |
| `cleared_reason` | `CharField(16)` | **yes** | null while `open`; `corrected` \| `absent` when cleared | FR-044, FR-044a |
| `cleared_at` | `DateTimeField` | **yes** | null while `open` | FR-044 |
| `first_observed_at` | `DateTimeField` | no | when this conflict was first seen | FR-042 |
| `last_observed_at` | `DateTimeField` | no | most recent load that saw it conflicting | FR-042 |
| `source_file` | `CharField(512)` | no | the load run that observed it | FR-042 |

### `source_status` is deliberately NOT constrained to `ClaimStatus`

It records what the file said, and what the file said is `No Claim` — a value the
`Claim` model refuses to represent at all. Constraining this column to
`ClaimStatus` would make it impossible to store the very thing the anomaly exists
to record. It is free text because it is a **quotation of the source**, not a
domain value.

### `policy` is unique — the idempotency key

FR-043 requires re-running the load leave the anomaly count unchanged. The
loader reconciles on `policy` with `update_or_create`, so a second run over an
unchanged file updates 390 rows rather than inserting 390 more.

**Verified against the dataset**: the 390 anomalous rows map to 390 *distinct*
policies, so one-per-policy is sound for this export. This inherits the same
limitation as claim matching (research §2): a future export with two anomalous
claims against one policy would reconcile both onto one row. Documented rather
than defended — it is the correct behavior for a file with no claim identifier.

### State transitions

```
                    load observes conflict
        (none) ─────────────────────────────────►  open
                                                    │
                    ┌───────────────────────────────┤
                    │                               │
        row present, no longer         row absent from load
        conflicting                             │
                    │                               │
                    ▼                               ▼
        cleared/corrected                  cleared/absent
                    │                               │
                    └───────────┬───────────────────┘
                                │
                    load observes conflict again (FR-044b)
                                │
                                ▼
                              open        (cleared_reason/cleared_at reset to null)
```

**`open → cleared` requires a reason. There is no reasonless clearing.** This is
FR-044a's teeth: a consumer counting confirmed corrections filters
`cleared_reason="corrected"`, and an `absent` row can never be mistaken for one.

**Re-raising resets `cleared_reason` and `cleared_at` to null** (FR-044b), which
is precisely why the audit trail is load-bearing rather than decorative: this row
now has no memory of having been cleared before. A policy cleared as `absent`,
re-raised, and later cleared as `corrected` shows only the last state here. The
append-only `AuditLog` is the only place both clearings survive — FR-048a.

### A deliberate non-field: no `cleared_count` or history JSON

Tempting, and rejected. A denormalized counter or embedded history array on this
row would be a *second*, mutable copy of what `AuditLog` already holds
immutably — and the two would drift, with the mutable one winning by being
closer to hand. The anomaly table is current state; history belongs in the
append-only table built for it.

### Meta

```python
class Meta:
    ordering = ["id"]
    indexes = [
        models.Index(fields=["status", "cleared_reason"]),
    ]
```

The composite index serves the query FR-044a exists for: "every confirmed
correction" and "every current anomaly" are both single-index lookups.

---

## Audit actions written by this feature

| Action | Actor | When | Requirement |
|---|---|---|---|
| `claim.created` | user | API create | FR-029 |
| `claim.updated` | user | API amend (changed fields only) | FR-029, FR-033 |
| `claim.deleted` | user | API remove (archival) | FR-029 |
| `claim.viewed` / `claim.created` / … with `outcome="refused"` | user or null | refusal, via the registry | FR-031 |
| `claim.created` / `claim.updated` | **null** (system) | dataset load | FR-039 |
| `claim_anomaly.recorded` | **null** (system) | load observes a new conflict | FR-048 |
| `claim_anomaly.cleared_corrected` | **null** (system) | row returned, no longer conflicting | FR-048a |
| `claim_anomaly.cleared_absent` | **null** (system) | row absent from load | FR-048a |
| `claim_anomaly.reraised` | **null** (system) | cleared anomaly conflicts again | FR-044b, FR-048a |

The two clearing actions are **separate action names** rather than one action
with a reason in `context`. FR-048a requires a "distinct recorded value" a
consumer can filter on, and `action` is already indexed (`apps/audit/models.py:31`)
whereas a JSON `context` key is not. `target_type` is `claims.ClaimLoadAnomaly`
and `target_id` is the anomaly's id, so the whole clearing history of one anomaly
is a single indexed lookup on `(target_type, target_id, timestamp)` — an index
that already exists (`apps/audit/models.py:43`).

---

## Existing entities touched

### Policy — `apps/policies/models.py`

**No schema change.** Two new reverse relations arrive by FK declaration:

- `policy.claims` — `related_name` on `Claim.policy`
- `policy.claim_load_anomalies` — `related_name` on `ClaimLoadAnomaly.policy`

`PROTECT` on both means a policy carrying either cannot be hard-deleted (FR-009).
Worth stating: this makes the **anomaly** table protective too. A policy whose
only claim-side record is an anomaly still cannot be destroyed — correct, since
destroying it would orphan the anomaly's only reference to what the source said.

### Customer — `apps/customers/models.py`

**Untouched.** No claim references a customer directly; the path is
`Claim → Policy → Customer` (FR-002). A claim inherits its business context from
the contract it was filed under rather than restating it.

### AuditLog — `apps/audit/models.py`

**No schema change.** New `action` values and one new `target_type`
(`claims.ClaimLoadAnomaly`), both plain `CharField` values needing no migration.

---

## Load outcome, verified against `data/Insurance_Dataset.csv`

| Quantity | Expected | Derivation |
|---|---|---|
| Rows read | 3,000 | file |
| Claims created | **2,246** | 3,000 − 754 `No Claim` rows |
| Anomalies recorded | **390** | `No Claim` rows with non-zero amount |
| Claims refused | 0 | no blank claim cells, no negative amounts |
| Anomaly amount range | 8.52 – 19,919.13 | the 390 non-zero `No Claim` amounts |

Re-running over the unchanged file must leave both **2,246** and **390** exactly
where they are, reporting claims as updated (SC-003) and anomalies as unchanged
(SC-012).
