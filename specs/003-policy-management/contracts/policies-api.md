# Contract: Policy API

**Base path**: `/api/policies/`
**Auth**: session, unchanged from Phase 1.
**Permission**: `HasRole(...)` per FR-026, enforced server-side on every route.

---

## Permission matrix (FR-026)

| Role | `GET` list / detail | `POST` / `PATCH` / `DELETE` |
|---|---|---|
| Underwriter | 200 | **allowed** |
| System Administrator | 200 | **allowed** |
| Customer Service | 200 | refused |
| Claims Adjuster | 200 | refused |
| Fraud Analyst | 200 | refused |
| Risk Manager | 200 | refused |
| Compliance Officer | 200 | refused |
| Product Manager | 200 | refused |
| Executive Leadership | 403 | refused |
| unauthenticated | 403 | refused |

**Note the differences from the Customer API** — these are deliberate, not
drift:

- **Write access is Underwriter + Sys Admin**, not Customer Service. Writing
  policy terms is underwriting work.
- **Product Manager may read policies**, though they may not read customers.
  Policy type and premium mix are product concerns; individual personal data
  is not.

**Refusal status depends on route shape**, inherited from `HasRole`:

- **Collection routes** (`/api/policies/`) → **403**
- **Detail routes** (`/api/policies/{id}/`) → **404**, so a refusal is
  indistinguishable from a nonexistent record (FR-023)

Every refusal writes an `AuditLog` row with `outcome="refused"` (FR-031).
A **permitted** user's 404 on a missing policy writes nothing (FR-032).

---

## `GET /api/policies/`

List live policies, paginated at 50, ordered by `id` (FR-018).
Archived policies never appear (FR-021).

**Query parameters**

| Param | Effect | Requirement |
|---|---|---|
| `customer` | policies belonging to that customer id | FR-019 |
| `policy_type` | exact match (`Life`/`Auto`/`Property`/`Health`) | FR-020 |
| `expired=true` | `end_date` earlier than today | FR-020 |
| `page` | 1-based page number | FR-018 |

Filters combine with AND. A filter matching nothing returns `200` with
`"results": []` and `"count": 0` — never an error.

`expired` is derived per request by comparing `end_date` to today's date. There
is no stored expiry status, so the answer is always current without a
scheduled job.

**200 response**

```json
{
  "count": 3000,
  "next": "http://localhost:8000/api/policies/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "customer": {
        "id": 1,
        "client_id": "CL-00001",
        "name": "Patrick Hart"
      },
      "policy_type": "Auto",
      "start_date": "2023-01-13",
      "end_date": "2027-03-11",
      "premium_usd": "750.23",
      "renewal_probability": "0.06",
      "created_at": "2026-08-09T12:00:00Z",
      "updated_at": "2026-08-09T12:00:00Z"
    }
  ]
}
```

`premium_usd` and `renewal_probability` serialize as **strings** (DRF's
`DecimalField` default), preserving exact decimal precision. An absent renewal
probability is `null`, never `"0.00"` (FR-004).

The embedded customer summary means US1's "review a customer's coverage" needs
no second request per row. `archived_at` is not exposed — archived policies are
simply absent.

**A policy whose customer is archived still appears here**, with its customer
summary intact (FR-008, FR-022). Archiving a customer hides the customer, not
their coverage history.

---

## `POST /api/policies/`

Create a policy. **Underwriter and System Administrator only.**

**Request**

```json
{
  "customer": 1,
  "policy_type": "Health",
  "start_date": "2026-01-01",
  "end_date": "2027-01-01",
  "premium_usd": "1200.00"
}
```

`renewal_probability` is optional and defaults to `null` (FR-004).

**201** → the full record with the embedded customer summary. Writes
`policy.created` to the audit log (FR-028).

**400** — validation failure, naming the offending field (FR-015):

| Condition | Field named | Requirement |
|---|---|---|
| `policy_type` not a recognized value | `policy_type` | FR-009 |
| `end_date` on or before `start_date` | both dates | FR-010 |
| `premium_usd` zero or negative | `premium_usd` | FR-011 |
| `renewal_probability` outside 0–1 | `renewal_probability` | FR-012 |
| `customer` does not exist | `customer` | FR-013 |
| `customer` is archived | `customer` | FR-014 |
| `customer` omitted | `customer` | FR-002 |
| customer already holds a live policy of this type | `policy_type` | §5 research |

**A customer may hold several policies** (FR-003) — a second policy of a
*different* type succeeds. Only a duplicate live policy of the *same* type is
refused, which is the constraint that makes the loader's match key sound.

Creating a policy for an **archived** customer is refused naming `customer`,
with a message distinguishing "removed" from "does not exist" — an underwriter
should not go hunting for a record that was deliberately archived.

Nothing is stored on any 400 (FR-015).

---

## `GET /api/policies/{id}/`

**200** → the same object shape as a list entry.
**404** → nonexistent, archived, or not permitted — indistinguishable (FR-023).

---

## `PATCH /api/policies/{id}/`

Partial update. **Underwriter and System Administrator only.**
Any subset of writable fields; omitted fields untouched (FR-017).

```json
{"premium_usd": "1350.00"}
```

**200** → the full updated record. Writes `policy.updated` with `before` and
`after` containing **only the fields that actually changed** (FR-029).

**400** → same validation table as POST. Changing `end_date` alone still
triggers the date-coherence check against the stored `start_date`.

**404** → nonexistent, archived, or not permitted.

The policy write and its audit entry share one transaction (FR-033).

---

## `DELETE /api/policies/{id}/`

Archive, not destroy (FR-021). **Underwriter and System Administrator only.**

**204** → `archived_at` is set. The record vanishes from lists and detail, the
row is retained so future claims are never orphaned, and the
`(customer, policy_type)` slot is **released** — the customer may hold a new
policy of that type.

Writes `policy.deleted` with `before` holding the full values as at removal
(FR-030).

**404** → nonexistent, already archived, or not permitted.

There is no un-archive route.

---

## Interaction with Customer archival

| Action | Effect on policies |
|---|---|
| Customer archived | **None.** Policies stay live, readable, linked (FR-022) |
| Customer archived, then policy read | 200, customer summary intact (FR-008) |
| New policy for archived customer | 400 naming `customer` (FR-014) |
| Policy archived | Hidden from `customer.policies`; customer unaffected |

---

## Removed: `GET /api/policies/placeholder/`

The Phase 1 placeholder returning `{"module": "policies", "status": "placeholder"}`
is deleted along with its tests (FR-049). The path returns **404** after this
feature, asserted by test (SC-011).

---

## Audit entries produced

| Trigger | `action` | `outcome` | `before` | `after` |
|---|---|---|---|---|
| POST 201 | `policy.created` | `succeeded` | `null` | full record |
| PATCH 200 | `policy.updated` | `succeeded` | changed fields, old | changed fields, new |
| DELETE 204 | `policy.deleted` | `succeeded` | full record at removal | `null` |
| permission refusal | per method | `refused` | `null` | `null` |
| permitted user's 404 | *(nothing written)* | — | — | — |

`target_type` is `"policies.Policy"`. Retrievals produce no audit entries
(FR-035).

History is readable at
`GET /api/audit/history/policies.Policy/{id}/` by Compliance Officer and
System Administrator, through the existing unmodified audit routes.
