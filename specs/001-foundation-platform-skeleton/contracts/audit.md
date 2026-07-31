# Contract: Audit History

**Requirements**: FR-018, FR-019, FR-021, FR-023, FR-024 | **Success criteria**:
SC-004, SC-005 | **User story**: 3

The audit log is **append-only**. The HTTP surface is therefore read-only: there
is no create, update, or delete endpoint, and none may be added (FR-019). Audit
records are written only by `apps.audit.services.record_action()`, called from
inside the transaction of the action being recorded.

---

## `GET /api/audit/`

List audit records, most recent first.

**Permitted roles**: Compliance Officer, System Administrator
**Route type**: collection → unauthenticated callers receive `403`

### Query parameters

| Parameter | Type | Purpose |
|---|---|---|
| `target_type` | string | Filter to one model label, e.g. `accounts.User` |
| `target_id` | string | Filter to one affected record — use with `target_type` |
| `actor` | integer | Filter to one acting user's id |
| `action` | string | Filter to one action name, e.g. `user.role_changed` |
| `ordering` | string | `timestamp` (chronological) or `-timestamp` (default, newest first) |

### Response — `200 OK`

```json
{
  "count": 2,
  "results": [
    {
      "id": 42,
      "timestamp": "2026-07-30T10:31:07Z",
      "actor": 1,
      "actor_identifier": "admin@example.com",
      "actor_role": "system_administrator",
      "action": "user.role_changed",
      "target_type": "accounts.User",
      "target_id": "7",
      "outcome": "succeeded",
      "before": { "role": "claims_adjuster" },
      "after": { "role": "underwriter" }
    }
  ]
}
```

**`403 Forbidden`** — unauthenticated, or any role other than Compliance Officer
and System Administrator.

---

## `GET /api/audit/history/{target_type}/{target_id}/`

Retrieve the complete history of one affected record, in **chronological order**
(oldest first) — the direct expression of FR-024 and Story 3, scenario 4.

**Permitted roles**: Compliance Officer, System Administrator
**Route type**: detail → unauthenticated or unpermitted callers receive
**`404 Not Found`**, never `403` (FR-012)

### Response — `200 OK`

```json
{
  "target_type": "accounts.User",
  "target_id": "7",
  "count": 2,
  "results": [
    {
      "id": 38,
      "timestamp": "2026-07-30T10:14:22Z",
      "actor": 1,
      "actor_identifier": "admin@example.com",
      "actor_role": "system_administrator",
      "action": "user.created",
      "outcome": "succeeded",
      "before": null,
      "after": { "email": "adjuster@example.com", "role": "claims_adjuster", "is_active": true }
    },
    {
      "id": 42,
      "timestamp": "2026-07-30T10:31:07Z",
      "actor": 1,
      "actor_identifier": "admin@example.com",
      "actor_role": "system_administrator",
      "action": "user.role_changed",
      "outcome": "succeeded",
      "before": { "role": "claims_adjuster" },
      "after": { "role": "underwriter" }
    }
  ]
}
```

Ordering is `timestamp` ascending, tie-broken by `id` ascending so two records
written in the same transaction still return in the order they were created.

A record with no history returns `200` with `count: 0` — an empty history is not
a `404`, since the query is about the audit log rather than about the target
record's existence.

---

## Deleted-actor behaviour (FR-021)

When the acting user's account is deleted, the FK is set to null but the record
remains fully readable and still identifies who acted:

```json
{
  "id": 42,
  "actor": null,
  "actor_identifier": "admin@example.com",
  "actor_role": "system_administrator",
  "action": "user.role_changed"
}
```

`actor_identifier` and `actor_role` are snapshots taken at write time. `actor_role`
reflects the role held **when the action occurred**, not the actor's current
role — a later role change does not rewrite the meaning of past entries.

---

## Immutability (FR-019, SC-005)

There is deliberately **no** `POST`, `PUT`, `PATCH`, or `DELETE` on any audit
route. Those methods return `405 Method Not Allowed`.

The absence of endpoints is not the guarantee — it is a consequence of one.
Immutability is enforced below the HTTP layer, at two levels
(see [data-model.md](../data-model.md#auditlog) and research.md §5):

1. `AuditLog.save()` raises on any update; `delete()` and queryset
   `update()`/`delete()` raise.
2. A PostgreSQL `BEFORE UPDATE OR DELETE` trigger raises, covering raw SQL,
   `bulk_update`, admin actions, and direct psql sessions.

SC-005 requires 100% of modification and deletion attempts to fail; tests
exercise both layers directly, not only through the API.

---

## Outcome field

`outcome` distinguishes a refused attempt from a successful one (Story 3,
scenario 3):

| Value | Meaning |
|---|---|
| `succeeded` | The action completed and its effects were committed |
| `refused` | The action was attempted and denied — the target was unchanged |

In this phase, `refused` entries are written for denied administrative actions
against user accounts. Ordinary RBAC rejections at the permission layer (a
Product Manager probing `/api/users/`) are **not** audited — they touch no
record, produce no change, and logging every probe would flood the table that
Principle II reserves for actions against business data.

---

## Reuse by later modules (FR-023)

Customer, Policy, Claim, Risk, Fraud, and CRM modules write to this same model
and appear on these same endpoints without schema changes — they supply their
own `action` names (e.g. `claim.status_changed`) and `target_type` values
(e.g. `claims.Claim`). Nothing in this contract is specific to `accounts.User`;
the `accounts.User` examples above are simply the only actions that exist in
this phase.
