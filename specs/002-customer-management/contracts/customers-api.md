# Contract: Customer API

**Base path**: `/api/customers/`
**Auth**: session (`SessionAuthentication`), unchanged from Phase 1.
**Permission**: `HasRole(...)` per FR-024. Enforced server-side on every route.

---

## Permission matrix (FR-024)

| Role | `GET` list / detail | `POST` / `PATCH` / `DELETE` |
|---|---|---|
| Customer Service | 200 | allowed |
| System Administrator | 200 | allowed |
| Underwriter | 200 | refused |
| Claims Adjuster | 200 | refused |
| Fraud Analyst | 200 | refused |
| Risk Manager | 200 | refused |
| Compliance Officer | 200 | refused |
| Product Manager | 403 | refused |
| Executive Leadership | 403 | refused |
| unauthenticated | 403 | refused |

**Refusal status depends on route shape**, inherited from `HasRole`:

- **Collection routes** (`/api/customers/`) → **403**. `has_permission()`
  returns `False` and DRF short-circuits.
- **Detail routes** (`/api/customers/{id}/`) → **404**. `has_object_permission()`
  raises `NotFound` so a refusal is indistinguishable from a nonexistent
  record (FR-022).

This asymmetry is deliberate Phase 1 behavior, not an inconsistency: a 403 on
a detail route would confirm the record exists.

Every refusal writes an `AuditLog` row with `outcome="refused"` (FR-030).

---

## `GET /api/customers/`

List live customers, paginated, `page_size = 50`, ordered by `id` (FR-017).
Archived customers never appear (FR-020).

**Query parameters**

| Param | Effect | Requirement |
|---|---|---|
| `search` | case-insensitive substring over `name`, `email`, `client_id` | FR-018 |
| `lead_source` | exact match | FR-019 |
| `gender` | exact match | FR-019 |
| `fraud_risk_flag` | exact match | FR-019 |
| `page` | 1-based page number | FR-017 |

Filters combine with AND. A search matching nothing returns `200` with
`"results": []` and `"count": 0` — never an error.

**200 response**

```json
{
  "count": 3000,
  "next": "http://localhost:8000/api/customers/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "client_id": "CL-00001",
      "name": "Patrick Hart",
      "email": "amandamartinez@hayes.com",
      "phone": "588-240-1527",
      "age": 25,
      "gender": "Other",
      "location": "New Steven",
      "lead_source": "Agent",
      "risk_score": "0.16",
      "fraud_risk_flag": "Low",
      "cross_sell_score": "0.75",
      "created_at": "2026-08-06T12:00:00Z",
      "updated_at": "2026-08-06T12:00:00Z"
    }
  ]
}
```

Scores serialize as **strings** (DRF's `DecimalField` default), preserving the
two-decimal precision of the source. An absent score is `null`, never `"0.00"`
(FR-006).

`archived_at` is not exposed — archived records are simply absent.

---

## `POST /api/customers/`

Create a customer. **Customer Service and System Administrator only.**

**Request** — `client_id` optional; generated as `CL-#####` when omitted
(FR-005). The three score fields are optional and default to `null` (FR-006).

```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "phone": "555-0100",
  "age": 36,
  "gender": "Female",
  "location": "London",
  "lead_source": "Referral"
}
```

**201** → the full record, including the assigned `client_id`, with
`risk_score`, `fraud_risk_flag`, and `cross_sell_score` all `null`.
Writes `customer.created` to the audit log (FR-027).

**400** — validation failure. The response names the offending field
(FR-014):

```json
{"age": ["Ensure this value is less than or equal to 120."]}
```

| Condition | Field named | Requirement |
|---|---|---|
| name absent or empty | `name` | FR-009 |
| email malformed | `email` | FR-010 |
| age outside 18–120 | `age` | FR-011 |
| gender / lead_source / fraud_risk_flag unrecognized | that field | FR-012 |
| risk_score or cross_sell_score outside 0–1 | that field | FR-013 |
| `client_id` already in use | `client_id` | FR-003 |

A duplicate `email` is **accepted** — two customers may legitimately share one
(FR-004). The source dataset contains three such pairs.

A `client_id` collision returns 400 with a `client_id` error naming the
conflict. It collides against archived records too, since archival reserves
the reference (FR-021).

Nothing is stored on any 400 (FR-014).

---

## `GET /api/customers/{id}/`

`{id}` is the internal PK (FR-044), not `client_id`.

**200** → the same object shape as a list entry.
**404** → nonexistent, archived, or not permitted — indistinguishable (FR-022).

---

## `PATCH /api/customers/{id}/`

Partial update. **Customer Service and System Administrator only.**
Any subset of writable fields; omitted fields are untouched (FR-016).

```json
{"phone": "555-0199"}
```

**200** → the full updated record. Writes `customer.updated` with `before` and
`after` containing **only the fields that actually changed** (FR-028). A PATCH
that sets a field to its current value contributes nothing to the diff.

**400** → same validation table as POST.
**404** → nonexistent, archived, or not permitted.

The customer write and its audit entry share one transaction — both commit or
neither does (FR-031).

---

## `DELETE /api/customers/{id}/`

Archive, not destroy (FR-020). **Customer Service and System Administrator only.**

**204** → `archived_at` is set. The record vanishes from list, search, and
detail, but the row and its `client_id` remain (FR-021). Writes
`customer.deleted` with `before` holding the customer's full values as at
removal (FR-029).

**404** → nonexistent, already archived, or not permitted.

There is no un-archive route. FR-020 requires retention, not restoration.

---

## Removed: `GET /api/customers/placeholder/`

The Phase 1 placeholder returning `{"module": "customers", "status": "placeholder"}`
is deleted along with its tests (FR-043). The path returns **404** after this
feature, asserted by test (SC-010).

---

## Audit entries produced

| Trigger | `action` | `outcome` | `before` | `after` |
|---|---|---|---|---|
| POST 201 | `customer.created` | `succeeded` | `null` | full record |
| PATCH 200 | `customer.updated` | `succeeded` | changed fields, old | changed fields, new |
| DELETE 204 | `customer.deleted` | `succeeded` | full record at removal | `null` |
| any permission refusal | matching action | `refused` | `null` | `null` |

`target_type` is `"customers.Customer"`; `target_id` is `str(customer.id)`.

Retrievals (GET list/detail) produce **no** audit entries (FR-033).

Existing audit routes expose this history unchanged — Compliance Officer and
System Administrator can read it at
`GET /api/audit/history/customers.Customer/{id}/`.
