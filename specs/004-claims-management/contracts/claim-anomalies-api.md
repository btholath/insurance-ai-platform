# Contract: Claim Load Anomalies API

**Base path**: `/api/claims/anomalies/`
**Auth**: session, unchanged from Phase 1.
**Permission**: `HasRole(...)` per FR-047 — **exactly the claim read set**.

**Read-only.** The dataset loader is the only writer. Nothing creates, amends, or
removes an anomaly through the API, because an anomaly is an observation of what
the source said, not a record anyone authors.

---

## Why this surface exists

FR-041 requires the 390 self-contradicting source rows survive as a **queryable**
signal. "Queryable" is the operative word: the later Fraud and Behavior phases
are the consumers, and a signal they cannot read is not retained in any useful
sense. SC-011 states the question this endpoint must answer — *"which policies
had inconsistent claim data"* — without access to the source file.

---

## Permission matrix (FR-047)

| Role | `GET` list / detail |
|---|---|
| Claims Adjuster | 200 |
| System Administrator | 200 |
| Fraud Analyst | 200 |
| Compliance Officer | 200 |
| Risk Manager | 200 |
| Customer Service | 403 |
| Underwriter | 403 |
| Product Manager | 403 |
| Executive Leadership | 403 |
| unauthenticated | 403 |

Identical to the claim **read** set, and no write set exists. An anomaly
discloses claim-adjacent financial detail — the amount the source carried — so it
cannot be readable by anyone who may not read claims.

**Registry note**: these routes are nested under `/api/claims/`, and
`audit_routes.match()` selects the longest matching prefix. The single
`/api/claims/` registry entry covers them correctly, since the role sets are the
same. No second registration is needed (research §8).

---

## `GET /api/claims/anomalies/`

List anomalies, paginated at 50, ordered by `id`.

**Query parameters**

| Param | Effect | Requirement |
|---|---|---|
| `policy` | restrict to one policy (by id) | FR-042 |
| `status` | `open` \| `cleared` | FR-044 |
| `cleared_reason` | `corrected` \| `absent` | **FR-044a** |
| `page` | 1-based page number | |

**200 response**

```json
{
  "count": 390,
  "next": "http://localhost:8000/api/claims/anomalies/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "policy": {
        "id": 17,
        "policy_type": "Auto",
        "customer": {"id": 4, "client_id": "CL-00004", "name": "…"}
      },
      "source_status": "No Claim",
      "source_amount_usd": "19919.13",
      "status": "open",
      "cleared_reason": null,
      "cleared_at": null,
      "first_observed_at": "2026-08-12T09:00:00Z",
      "last_observed_at": "2026-08-12T09:00:00Z",
      "source_file": "data/Insurance_Dataset.csv"
    }
  ]
}
```

`source_status` reads `"No Claim"` — a value the `Claim` model refuses to
represent at all. That is the point: the anomaly quotes the source, and the
source said something the domain rejects.

---

## The query FR-044a exists to make possible

The `cleared_reason` filter is not a convenience. It is the requirement:

```
GET /api/claims/anomalies/?status=cleared&cleared_reason=corrected
    → anomalies we VERIFIED were fixed

GET /api/claims/anomalies/?status=cleared&cleared_reason=absent
    → anomalies that merely STOPPED APPEARING, cause unknown
```

A consumer counting confirmed corrections **must** filter on `corrected`.
Counting all cleared rows would silently include rows that vanished from an
export for reasons unrelated to the conflict — filtered, truncated, date-scoped,
or withdrawn — and would understate source inconsistency invisibly, in the one
direction an anomaly signal must not err.

`cleared_reason` is **null while `status="open"`**, and is never an empty string.
There is no reasonless clearing.

---

## `GET /api/claims/anomalies/{id}/`

**200** — a single anomaly, same shape as a list element.
**404** — nonexistent or refused. Indistinguishable (FR-047 inherits FR-028).

---

## What this endpoint does NOT show: clearing history

The anomaly row carries only its **latest** state. An anomaly cleared as
`absent`, re-raised when the conflict returned (FR-044b), and later cleared as
`corrected` reports only that last clearing — `cleared_reason` and `cleared_at`
are reset to null on re-raise.

The full history lives in the audit trail (FR-048a), which is append-only and
therefore cannot lose it:

```
GET /api/audit/?target_type=claims.ClaimLoadAnomaly&target_id=1
```

returning, in order:

| action | timestamp |
|---|---|
| `claim_anomaly.recorded` | first load that saw the conflict |
| `claim_anomaly.cleared_absent` | load where the row did not appear |
| `claim_anomaly.reraised` | load where it conflicted again |
| `claim_anomaly.cleared_corrected` | load where it came back fixed |

This split is deliberate and is the reason FR-048a specifies a *distinct recorded
value* rather than prose. Current state answers "what is true now"; the trail
answers "what did we observe, and when". Denormalizing the history onto the
anomaly row would create a second mutable copy that drifts from the immutable
one — see data-model.md, "A deliberate non-field".

---

## Routes that do NOT exist

- **No `POST` / `PATCH` / `DELETE`.** The loader is the only writer.
- **No manual clear/dismiss action.** An anomaly clears only because a later load
  observed something — never because a person decided it was fine. A dismiss
  button would be indistinguishable, one export later, from a verified
  correction, which is exactly the conflation FR-044a forbids.
- **No "convert to claim" action.** Fabricating a claim from an uncorroborated
  amount is what FR-004 and FR-041 exist to prevent.
