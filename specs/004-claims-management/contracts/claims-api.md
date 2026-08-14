# Contract: Claims API

**Base path**: `/api/claims/`
**Auth**: session, unchanged from Phase 1.
**Permission**: `HasRole(...)` per FR-025, enforced server-side on every route.

**Replaces** `GET /api/claims/placeholder/` (Phase 1), which is removed (FR-049).

---

## Permission matrix (FR-026, FR-027)

| Role | `GET` list / detail | `POST` / `PATCH` / `DELETE` |
|---|---|---|
| Claims Adjuster | 200 | **allowed** |
| System Administrator | 200 | **allowed** |
| Fraud Analyst | 200 | refused |
| Compliance Officer | 200 | refused |
| Risk Manager | 200 | refused |
| Customer Service | 403 | refused |
| Underwriter | 403 | refused |
| Product Manager | 403 | refused |
| Executive Leadership | 403 | refused |
| unauthenticated | 403 | refused |

**This read set is narrower than either prior module** — five roles, against
Customer's seven and Policy's eight. Claim amounts are financial detail about an
individual, so product- and sales-facing roles are excluded. These are deliberate
differences, not drift:

- **Underwriter may write policies but cannot read claims.** The sharp case for
  the per-module registry: an Underwriter's 404 on a claim is a **refusal**,
  while the same user's 404 on a policy is an ordinary miss.
- **Customer Service may read customers but not claims.** Servicing an account
  does not require the claim ledger.
- **Fraud Analyst reads but does not write.** Investigation is not adjudication.
- **Write is Claims Adjuster + Sys Admin** — a third distinct write set, after
  Customer's (Customer Service) and Policy's (Underwriter).

**The Phase 1 placeholder's role set is NOT inherited.** It permitted
`CLAIMS_ADJUSTER, FRAUD_ANALYST, SYSTEM_ADMINISTRATOR`; the real set adds
Compliance Officer and Risk Manager to reads and drops Fraud Analyst from writes.

**Refusal status depends on route shape**, inherited from `HasRole`:

- **Collection routes** (`/api/claims/`) → **403**
- **Detail routes** (`/api/claims/{id}/`) → **404**, so a refusal is
  indistinguishable from a nonexistent record (FR-028)

Every refusal writes an `AuditLog` row with `outcome="refused"` (FR-031).
A **permitted** user's 404 on a missing claim writes nothing (FR-032).

---

## `GET /api/claims/`

List live claims, paginated at 50, ordered by `id` (FR-017).
Archived claims never appear (FR-021).

**Query parameters**

| Param | Effect | Requirement |
|---|---|---|
| `policy` | restrict to one policy (by id) | FR-018 |
| `claim_status` | restrict to one status: `Approved` \| `Denied` \| `Filed` | FR-019 |
| `page` | 1-based page number | FR-017 |

**200 response**

```json
{
  "count": 2246,
  "next": "http://localhost:8000/api/claims/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "policy": {
        "id": 17,
        "policy_type": "Auto",
        "customer": {"id": 4, "client_id": "CL-00004", "name": "…"}
      },
      "claim_status": "Approved",
      "claim_amount_usd": "1204.55",
      "created_at": "2026-08-12T09:00:00Z",
      "updated_at": "2026-08-12T09:00:00Z"
    }
  ]
}
```

The embedded policy summary carries `policy_type`, so US1 needs no second
request (FR-023). `select_related("policy", "policy__customer")` keeps this from
becoming an N+1 across a 50-record page.

**A claim against an archived policy still appears here** (FR-008). This is
deliberate and is the reverse of the instinct to hide it: withdrawing coverage
must not erase claim history. Only the *claim's* own `archived_at` hides a claim.

---

## `GET /api/claims/{id}/`

Retrieve a single claim by its identifier (FR-016).

**200** — a single claim, same shape as a list element.
**404** — nonexistent, archived (FR-021), or refused (FR-028). Indistinguishable.

---

## `POST /api/claims/`

Record a new claim (FR-020). **Claims Adjuster or System Administrator only.**

**Request**

```json
{"policy": 17, "claim_status": "Filed", "claim_amount_usd": "0.00"}
```

**201** — the created claim, in the read shape above.

**400** — validation failure. Every message names the offending field (FR-015):

| Condition | Field | Requirement |
|---|---|---|
| status not `Approved`/`Denied`/`Filed` | `claim_status` | FR-010 |
| **status is `No Claim`** | `claim_status` | **FR-012** |
| amount negative | `claim_amount_usd` | FR-011 |
| policy does not exist | `policy` | FR-013 |
| policy is archived | `policy` | FR-014 |
| policy omitted | `policy` | FR-002 |

**`No Claim` is refused here by construction.** It is not in the model's
`ClaimStatus` choices at all (see data-model.md), so it fails the `ChoiceField`
rather than a hand-written check. The error message must say more than "not a
valid choice" — it must explain that the absence of a claim is represented by the
absence of a record, or an adjuster will read it as a bug.

**Zero is accepted.** `"0.00"` is valid and distinct from omitting the field,
which is a 400 (FR-011).

**On the archived-policy refusal**: resolved through `Policy.all_objects` so the
message can say the policy is *archived* rather than *nonexistent* — the same
`ArchivedAwarePrimaryKeyRelatedField` pattern Phase 2b used for customers
(`apps/policies/serializers.py:31`). Reporting "does not exist" for a policy that
is right there sends an adjuster hunting.

---

## `PATCH /api/claims/{id}/`

Amend status and/or amount. **Claims Adjuster or System Administrator only.**

All fields optional. **`policy` is read-only after creation** (FR-022) — a claim
cannot be moved to a different policy. Supplying it is ignored rather than
erroring, consistent with DRF's read-only field handling.

**200** — the updated claim.
**400** — same validation table as `POST`.
**404** — nonexistent, archived, or refused.

**Audit records only fields that actually changed** (FR-033). A PATCH setting a
status to the value it already has writes an entry with an empty diff, not a
fabricated one — the same `before_diff`/`after_diff` computation as
`apps/policies/views.py:154`.

**No status transition is enforced** (FR-024). `Approved → Filed` is permitted:
status is a recorded fact, not a state machine. This feature does not adjudicate.

---

## `DELETE /api/claims/{id}/`

**Reversible archival, never a row deletion** (FR-021). Sets `archived_at`.

**204** — archived. The claim vanishes from list and detail, and remains
recoverable in storage.
**404** — nonexistent, already archived, or refused.

Archiving a claim **releases nothing and reserves nothing** — there is no
uniqueness constraint to interact with (FR-007). This is the substantive
difference from both prior modules, where archival had a slot-management
consequence.

---

## Routes that do NOT exist

- **No un-archive route.** FR-021 requires recoverable *in storage*, not through
  the API. Reversal is a DB operation, matching Customer and Policy.
- **No hard-delete route.** Nothing in the API destroys a claim.
- **No adjudication route** — no approve/deny/settle action. FR-024 puts the
  logic that would justify one outside this phase.
- **No `/api/claims/placeholder/`** — removed (FR-049).
