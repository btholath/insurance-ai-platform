# Contract: `loaddataset` management command (extended for claims)

**Command**: `python manage.py loaddataset <csv_path> [--dry-run]`
**File**: `apps/customers/management/commands/loaddataset.py` (existing, extended)

Phase 2a loaded customers. Phase 2b added policies. This phase adds **claims**
and **anomalies** to the same per-row transaction, completing the dataset.

The signature does not change. The command stays in `apps/customers/` rather
than moving: it is one command reading one file, and splitting it per module
would need a fourth place to coordinate row-level atomicity across three records.

---

## Column additions

```python
CLAIM_COLUMN_MAP = {
    "Claim_Status":     "claim_status",
    "Claim_Amount_USD": "claim_amount_usd",
}
REQUIRED_COLUMNS = set(COLUMN_MAP) | set(POLICY_COLUMN_MAP) | set(CLAIM_COLUMN_MAP)
```

Adding these to `REQUIRED_COLUMNS` satisfies **FR-037**: a file missing the claim
columns fails in `_read_rows()` **before the row loop**, so no customer or policy
is written. This mirrors the deliberate behavior change Phase 2b made for policy
columns.

The comment at `loaddataset.py:75` reserving these columns for Claims is now
discharged and should be updated to name the remaining unconsumed columns
(`Last_Interaction`, `Client_Feedback`).

---

## Per-row outcomes

Each row produces one outcome per entity. The claim outcome has **two values the
other entities do not have**:

| Claim outcome | When | Counts as |
|---|---|---|
| `created` | row records a real claim, none existed for this policy | claim created |
| `updated` | row records a real claim, one already existed | claim updated |
| `refused` | row's claim data is invalid | row refused entirely |
| **`skipped`** | status is `No Claim`, amount is zero | **not an error** (FR-036) |
| **`anomaly`** | status is `No Claim`, amount is **non-zero** | **not an error** (FR-045) |

`skipped` and `anomaly` are legitimate outcomes, not failures. FR-045 is explicit:
an anomaly is **not** a refusal — the row's customer and policy load normally, and
only the claim is withheld.

**Expected on the shipped dataset** (3,000 rows, verified):

```
Customers — created: 3000  updated: 0  refused: 0
Policies  — created: 3000  updated: 0  refused: 0
Claims    — created: 2246  updated: 0  refused: 0  skipped: 364
Anomalies — recorded: 390  cleared: 0  (corrected: 0  absent: 0)
```

`364` is `754 No Claim rows − 390 anomalous`. The counts must sum to 3,000:
`2246 + 364 + 390 = 3000`.

---

## Row-level atomicity, extended to three records

The existing contract holds unchanged: **one transaction per row spanning every
record it produces**, with all audit writes inside it (FR-038). A row whose claim
is invalid leaves **no customer, no policy, and no claim** behind.

The claim is validated through `ClaimSerializer` — the same serializer the API
uses — so FR-015's field-naming and the API's validation rules hold by
construction rather than by two definitions kept in step by hand. This follows
`_validate_policy_fields()` (`loaddataset.py:230`): fields that do not depend on
the FK are validated before any write, and the FK is attached inside the
transaction where a failure rolls the row back.

**One asymmetry to implement carefully.** `No Claim` is a *valid source value*
but is **not** in `ClaimStatus` choices, so feeding it to `ClaimSerializer` would
report a validation error for a row that is not invalid. The loader must branch
on `No Claim` **before** constructing the serializer:

```
if status == "No Claim":
    if amount != 0:  → record anomaly, outcome "anomaly"
    else:            → outcome "skipped"
    # no ClaimSerializer, no Claim row, in both cases
else:
    → validate through ClaimSerializer, create/update
```

Getting this backwards would refuse 754 valid rows.

---

## Claim reconciliation (FR-035)

Match on **`policy`, among live rows only**:

```python
Claim.objects.filter(policy=policy).first()
```

`Claim.objects` excludes archived rows, so a load after an archival creates a
fresh claim rather than resurrecting a deliberately removed one — the same rule
the policy matcher uses (`loaddataset.py:248`), and deliberately the opposite of
the customer matcher, which resolves through `all_objects` because FR-021 there
reserves the reference forever.

**Documented limitation** (research §2): this export carries at most one claim per
policy — verified, all 3,000 `(Client_ID, Policy_Type)` pairs are distinct — which
is what makes matching on `policy` sound. A future export with two claims against
one policy would reconcile both onto the first record, silently. The file provides
no claim identifier, so no better key exists; this belongs in the loader docstring,
not in tribal memory.

---

## Anomaly lifecycle across runs

The loader tracks **two sets** per run:

- `policies_seen` — every policy the file produced a row for
- `policies_conflicting` — policies whose row was `No Claim` with a non-zero amount

### Recording (FR-041, FR-043)

For each conflicting row, `update_or_create` on `policy`:

- **new** → insert with `status="open"`, `first_observed_at=now`,
  `last_observed_at=now`; audit `claim_anomaly.recorded`
- **existing and `open`** → refresh `last_observed_at`, `source_status`,
  `source_amount_usd`, `source_file`. **No new audit entry** — nothing changed
  about the observation, and an entry per run would be noise that grows linearly
- **existing and `cleared`** → **re-raise** (FR-044b): `status="open"`,
  `cleared_reason=None`, `cleared_at=None`; audit `claim_anomaly.reraised`

`update_or_create` on a unique `policy` is what makes SC-012 hold: the count
stays 390 across any number of runs.

### Clearing (FR-044, FR-044a) — after the row loop

Every anomaly still `open` that was **not** in `policies_conflicting` this run
clears, with the reason decided by one question — *did we see the row at all?*

| Condition | `cleared_reason` | Audit action |
|---|---|---|
| policy **in** `policies_seen` | `corrected` | `claim_anomaly.cleared_corrected` |
| policy **not in** `policies_seen` | `absent` | `claim_anomaly.cleared_absent` |

**This is the distinction FR-044 was refined to enforce.** `corrected` means the
load positively observed the resolution. `absent` means it observed *nothing* —
the row may have been fixed, withdrawn, or dropped by an export that no longer
covers it. Collapsing them would let a Phase 4 query count unexplained
disappearances as verified corrections.

Both reasons set `cleared_at=now` and write an entry attributable to the **system
load, not a person** (FR-048): `actor=None`, `context={"source": "loaddataset",
"file": path}`.

**Clearing runs in its own transaction after the loop**, not per row. It is a
whole-file conclusion — "not seen in this run" cannot be known until the run
ends — and a per-row transaction cannot express it.

---

## `--dry-run` (FR-040, FR-046)

Reports every count above, including `anomaly` and the clearing breakdown, and
**writes nothing**: no claim, no anomaly, no clearing, no audit entry.

This requires computing both sets and the clearing decision without persisting
them. Worth stating because it is the easy thing to get wrong: a dry run that
reports `Anomalies — cleared: 12 (absent: 12)` and then, on the real run,
clears a different number would make preview mode useless for the operator
deciding whether to run it for real.

---

## Output format

```
Customers — created: 3000  updated: 0  refused: 0
Policies  — created: 3000  updated: 0  refused: 0
Claims    — created: 2246  updated: 0  refused: 0  skipped: 364
Anomalies — recorded: 390  cleared: 0  (corrected: 0  absent: 0)
```

Claims report on **one line with the other entities** (FR-036) — a fourth count,
`skipped`, alongside the three the other entities report.

Anomalies report on **their own line** (FR-045), because they are not a claim
outcome and folding them in would suggest they are. The clearing breakdown is
always shown split by reason, even at zero: an operator who never sees the two
numbers separated has no reason to learn they differ.

Refusal detail per row is unchanged (`Row {n}: {field} — {message}`).
