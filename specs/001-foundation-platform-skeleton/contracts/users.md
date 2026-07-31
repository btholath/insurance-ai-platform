# Contract: User Accounts & Role Administration

**Requirements**: FR-008 – FR-017, FR-020 | **Success criteria**: SC-002,
SC-003, SC-004 | **User stories**: 2, 3

All endpoints here are restricted to the **System Administrator** role
(FR-017). `is_superuser` confers no access — the role field is the only signal
(spec edge case: "Administrator vs. unrestricted superuser").

---

## `POST /api/users/`

Create a user account with exactly one role.

**Permitted roles**: System Administrator
**Route type**: collection → unauthenticated callers receive `403`

### Request

```json
{
  "email": "adjuster@example.com",
  "password": "<password>",
  "first_name": "Dana",
  "last_name": "Reyes",
  "role": "claims_adjuster"
}
```

| Field | Required | Rules |
|---|---|---|
| `email` | yes | Valid address, unique (case-insensitive) |
| `password` | yes | Validated by Django's configured password validators |
| `first_name` | no | ≤ 150 chars |
| `last_name` | no | ≤ 150 chars |
| `role` | yes | One of the nine values in [data-model.md](../data-model.md#role-enumeration--not-a-table) |

### Responses

**`201 Created`**

```json
{
  "id": 7,
  "email": "adjuster@example.com",
  "first_name": "Dana",
  "last_name": "Reyes",
  "role": "claims_adjuster",
  "is_active": true,
  "date_joined": "2026-07-30T10:14:22Z"
}
```

The password is never echoed back, in this or any other response.

**`400 Bad Request`** — invalid role (FR-010):

```json
{ "role": ["\"auditor\" is not a valid choice."] }
```

Also `400` for a missing `role`, a duplicate email, or a password failing
validation.

**`403 Forbidden`** — caller is unauthenticated, or holds any role other than
System Administrator (FR-013). No account is created.

### Audit (FR-020)

Writes one `AuditLog` record inside the creating transaction:

| Field | Value |
|---|---|
| `action` | `user.created` |
| `target_type` | `accounts.User` |
| `target_id` | new user's id |
| `outcome` | `succeeded` |
| `before` | `null` |
| `after` | `{"email": ..., "role": ..., "is_active": true}` |

The password is **never** written to `after`. If the audit insert fails, the
transaction rolls back and no account is created (FR-022).

---

## `GET /api/users/`

List user accounts.

**Permitted roles**: System Administrator
**Route type**: collection → unauthenticated `403`

**`200 OK`**

```json
{
  "count": 9,
  "results": [
    { "id": 1, "email": "admin@example.com", "role": "system_administrator", "is_active": true }
  ]
}
```

Password hashes are never serialized. No audit record — reads of the account
list are not among the sensitive actions FR-020 enumerates.

---

## `GET /api/users/{id}/`

Retrieve one account.

**Permitted roles**: System Administrator
**Route type**: detail → unauthenticated or unpermitted callers receive
**`404 Not Found`**, never `403` (FR-012 — a `403` here would confirm the
account exists).

**`200 OK`** — same object shape as the `201` response above.

---

## `PATCH /api/users/{id}/`

Change an account's role, or update its non-credential fields.

**Permitted roles**: System Administrator
**Route type**: detail → unauthenticated or unpermitted callers receive `404`

### Request

```json
{ "role": "underwriter" }
```

`email`, `first_name`, `last_name`, and `is_active` may also be patched.
`password` is **not** accepted on this endpoint (password change is out of scope
for this phase).

### Responses

**`200 OK`** — updated account object.

**`400 Bad Request`** — role outside the nine values (FR-010).

**`404 Not Found`** — caller unauthenticated or not a System Administrator; the
target account is unchanged (FR-013).

### Audit (FR-020)

| Field | Value |
|---|---|
| `action` | `user.role_changed` when `role` changed, otherwise `user.updated` |
| `target_type` | `accounts.User` |
| `target_id` | the account's id |
| `outcome` | `succeeded` |
| `before` | changed fields' prior values, e.g. `{"role": "claims_adjuster"}` |
| `after` | changed fields' new values, e.g. `{"role": "underwriter"}` |

Setting `is_active` to `false` records `user.deactivated`.

### Immediate effect (FR-016)

The affected user's **next** request is evaluated against the new role. No
platform restart, no re-login, no cache invalidation step — the role is read from
the database on each request (research.md §4).

---

## Authentication endpoints

Session sign-in and sign-out use Django's built-in views, mounted for the API:

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/api/auth/login/` | `POST` | public | `{"email": ..., "password": ...}` → `200` + session cookie; `400` on bad credentials |
| `/api/auth/logout/` | `POST` | authenticated | `204`; clears the session |

Failed sign-in returns the same generic error whether the email exists or not,
so account existence is not disclosed. Inactive accounts cannot sign in.

Sign-in and sign-out are not audited in this phase — FR-020 names account
creation and role change as the required records, and session events are the
"session management features" the spec places out of scope.

---

## RBAC test matrix (FR-033, SC-002, SC-003)

Every endpoint above is tested against all nine roles plus the unauthenticated
case. Expected results:

| Caller | `POST /api/users/` | `GET /api/users/{id}/` |
|---|---|---|
| Unauthenticated | `403` | `404` |
| System Administrator | `201` | `200` |
| Fraud Analyst | `403` | `404` |
| Claims Adjuster | `403` | `404` |
| Customer Service | `403` | `404` |
| Underwriter | `403` | `404` |
| Compliance Officer | `403` | `404` |
| Risk Manager | `403` | `404` |
| Product Manager | `403` | `404` |
| Executive Leadership | `403` | `404` |

In every refused case the target data is unchanged and no account is created
(SC-003 requires zero exceptions).
