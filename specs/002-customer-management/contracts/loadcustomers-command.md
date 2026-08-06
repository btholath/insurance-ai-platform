# Contract: `loadcustomers` Management Command

**Invocation**: `python manage.py loadcustomers <csv_path> [--dry-run]`

Loads customers from the source dataset. Idempotent on `client_id`.

---

## Arguments

| Argument | Required | Notes |
|---|---|---|
| `csv_path` | **yes** | Positional. **No default** — FR-034 forbids a default that assumes a committed file. |
| `--dry-run` | no | Validates and reports counts, writes nothing. |

The source file is gitignored (`data/Insurance_Dataset.csv`, FR-041 — already
in `.gitignore` as of commit `5584205`). The path is supplied at run time.

---

## Column mapping

Nine of the source's twenty columns are read. The rest are ignored without
error (FR-037), so the same file later serves the Policy and Claims loaders.

| CSV column | Customer field |
|---|---|
| `Client_ID` | `client_id` |
| `Client_Name` | `name` |
| `Client_Email` | `email` |
| `Client_Phone` | `phone` |
| `Client_Age` | `age` |
| `Client_Gender` | `gender` |
| `Client_Location` | `location` |
| `Lead_Source` | `lead_source` |
| `Risk_Score` | `risk_score` |
| `Fraud_Risk_Flag` | `fraud_risk_flag` |
| `Cross_Sell_Score` | `cross_sell_score` |

*(Eleven columns mapped — the nine identity/demographic fields plus the two
score columns and the fraud level.)*

**Deliberately ignored**: `Policy_Type`, `Policy_Start_Date`, `Policy_End_Date`,
`Policy_Premium_USD`, `Claim_Status`, `Claim_Amount_USD`, `Last_Interaction`,
`Renewal_Probability`, `Client_Feedback`.

---

## Behavior

**Matching** is on `client_id` through `Customer.all_objects` — including
archived records, so an archived customer reconciles in place rather than
producing a duplicate (FR-021, FR-035).

**Validation** runs through the same `CustomerSerializer` the API uses
(FR-038). There is one definition of validity, not two.

**Atomicity** is per row. Each row gets its own `transaction.atomic()`, so a
refused row leaves nothing behind while valid rows persist — which is what
makes FR-039's separate created/updated/refused counts meaningful. A
file-wide transaction would make one bad row discard every good one.

**Audit**: each created or updated row writes an entry with `actor=None` and
`context={"source": "loadcustomers", "file": "<path>"}` (FR-042). Migration
`0003` already relaxed the audit immutability trigger to permit a null actor.

A 3,000-row load therefore writes 3,000 audit entries, and a re-run on
unchanged input writes 3,000 `customer.updated` entries. This is noisy but
truthful; no-op suppression is deliberately not implemented.

---

## Output

**Success**

```
Loading customers from data/Insurance_Dataset.csv
Created: 3000  Updated: 0  Refused: 0
```

**Re-run on unchanged input** (FR-035, SC-002)

```
Loading customers from data/Insurance_Dataset.csv
Created: 0  Updated: 3000  Refused: 0
```

**With refused rows** (FR-038, FR-039) — each refusal names the row number and
the offending field:

```
Loading customers from data/bad.csv
Row 42: age — Ensure this value is greater than or equal to 18.
Row 87: gender — "Unknown" is not a valid choice.
Created: 2998  Updated: 0  Refused: 2
```

Row numbers are 1-based over data rows, excluding the header.

---

## Failure modes

All of these exit non-zero via `CommandError` and create **no** customers
(FR-040):

| Condition | Message |
|---|---|
| path does not exist | `File not found: <path>` |
| path unreadable | `Cannot read file: <path>` |
| required columns missing | `Missing required columns: Client_ID, Client_Age` |
| file empty / no header | `File has no header row: <path>` |

The required-column check inspects `DictReader.fieldnames` **before** the row
loop begins, so a structurally wrong file cannot write a partial load.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Completed. May include refused rows — refusals are reported, not fatal. |
| `1` | `CommandError` — file missing, unreadable, or structurally invalid. Nothing written. |

Refused rows are a **reportable outcome, not a failure**: FR-039 requires the
command to report all three counts, which presumes it runs to completion with
a nonzero refused count.
