# Contract: `loaddataset` Management Command

**Invocation**: `python manage.py loaddataset <csv_path> [--dry-run]`

Loads customers **and their policies** from the source dataset in one pass.
Idempotent on both record types.

**Renamed from `loadcustomers`.** The Phase 2a name becomes misleading once the
command also loads policies (and, next spec, claims). `loadcustomers` is
retained as a thin alias so the Phase 2a quickstart, README, and operator
habits keep working — breaking a documented command to save one subclass would
be a poor trade.

---

## Arguments

| Argument | Required | Notes |
|---|---|---|
| `csv_path` | **yes** | Positional. **No default** (FR-036) — the file is gitignored and must never be assumed committed. |
| `--dry-run` | no | Validates and reports counts for both record types, writes nothing. |

---

## Column mapping

The policy record adds five columns to the eleven the customer record already
uses. The remaining four are still ignored (FR-042), reserved for Claims.

| CSV column | Policy field |
|---|---|
| `Policy_Type` | `policy_type` |
| `Policy_Start_Date` | `start_date` |
| `Policy_End_Date` | `end_date` |
| `Policy_Premium_USD` | `premium_usd` |
| `Renewal_Probability` | `renewal_probability` |

**Still ignored, now reserved for Claims**: `Claim_Status`,
`Claim_Amount_USD`, `Last_Interaction`, `Client_Feedback`.

`Client_ID` continues to identify the customer, and is how each policy finds
its owner (FR-037).

---

## Matching and idempotency

**Customers** match on `client_id` through `Customer.all_objects`, unchanged
from Phase 2a — including archived customers, so an archived customer
reconciles in place (FR-041).

**Policies** match on **`(customer, policy_type)` among live rows only**
(FR-039).

Matching on the customer alone would be wrong: a customer holding auto *and*
home cover would have one policy repeatedly overwritten by the other on every
re-run — silently, and only for customers this export cannot produce. Verified:
`(Client_ID, Policy_Type)` is unique across all 3,000 rows, so the key is sound
today and survives the multi-policy case.

**Archived policies are not resurrected.** Matching filters to live rows, so a
load after an archival creates a *fresh* live policy rather than un-archiving
one. FR-038 requires one **live** policy per source row, and silently undoing a
deliberate removal would be worse than creating a new record.

---

## Row atomicity — both records or neither

Each row runs in **one** `transaction.atomic()` covering the customer *and* its
policy, with **policy validation running before either record is written**.

FR-045 requires that a refused policy not silently discard the customer from the
same row. The stronger guarantee is that a row lands completely or not at all: a
half-landed row (customer present, policy missing) is precisely the state an
operator cannot reason about, and re-running would then create the policy while
reporting the customer as "updated" — making the counts lie.

So a row with a bad policy is reported as refused, with its reason, and leaves
nothing behind. Valid rows around it persist, which is what makes FR-044's
separate counts meaningful.

---

## Output

**First run**

```
Loading dataset from data/Insurance_Dataset.csv
Customers — created: 3000  updated: 0  refused: 0
Policies  — created: 3000  updated: 0  refused: 0
```

**Re-run on unchanged input** (FR-038)

```
Customers — created: 0  updated: 3000  refused: 0
Policies  — created: 0  updated: 3000  refused: 0
```

**With refused rows** (FR-043, FR-044) — each refusal names the row number and
the offending field:

```
Row 42: end_date — End date must be after start date.
Row 87: policy_type — "Motor" is not a valid choice.
Customers — created: 2998  updated: 0  refused: 2
Policies  — created: 2998  updated: 0  refused: 2
```

Both counts increment for a refused row, which is truthful under row-level
atomicity: the row was refused, not half-applied.

Row numbers are 1-based over data rows, excluding the header.

---

## Failure modes

All exit non-zero via `CommandError`, creating **nothing** (FR-046):

| Condition | Message |
|---|---|
| path does not exist | `File not found: <path>` |
| path unreadable | `Cannot read file: <path>` |
| required columns missing | `Missing required columns: Policy_Type, Client_Age` |
| file empty / no header | `File has no header row: <path>` |

The required-column check now covers **both** the customer and policy column
sets, and runs before the row loop, so a file missing policy columns fails
before writing any customer — a change in behavior from Phase 2a, where such a
file would have loaded customers successfully.

---

## Audit

Each created or updated record — customer *and* policy — writes its own entry
with `actor=None` and `context={"source": "loaddataset", "file": <path>}`
(FR-048).

A full load therefore writes ~6,000 entries (3,000 customers + 3,000 policies),
and a re-run writes ~6,000 more as `updated`. Noisy but truthful; no-op
suppression is deliberately not implemented, for the Phase 2a reason —
deciding a row is unchanged requires the same field comparison the audit diff
already needs, and conflating the two would hide real updates.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Completed. May include refused rows — refusals are reported, not fatal. |
| `1` | `CommandError` — file missing, unreadable, or structurally invalid. Nothing written. |

---

## Backward compatibility

`python manage.py loadcustomers <path>` continues to work, producing identical
behavior to `loaddataset` — including now loading policies. An operator running
the Phase 2a command gets the Phase 2b result, which is the intended outcome:
customers without their policies is not a state this platform wants to be in.
