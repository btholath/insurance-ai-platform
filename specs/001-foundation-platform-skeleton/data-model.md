# Data Model: Foundation — Platform Skeleton & Role-Based Access

**Feature**: `001-foundation-platform-skeleton` | **Date**: 2026-07-30

Two persisted entities (`User`, `AuditLog`), one enumeration (`Role`), and one
transient non-persisted structure (`HealthStatus`). Decisions behind these
shapes are recorded in [research.md](./research.md).

---

## Role (enumeration — not a table)

`django.db.models.TextChoices` in `apps/accounts/models.py`. Closed set of nine
values from the BRD's Primary Users list. See research.md §3 for why this is an
enum rather than a table.

| Value (stored) | Label |
|---|---|
| `fraud_analyst` | Fraud Analyst |
| `claims_adjuster` | Claims Adjuster |
| `customer_service` | Customer Service |
| `underwriter` | Underwriter |
| `compliance_officer` | Compliance Officer |
| `risk_manager` | Risk Manager |
| `product_manager` | Product Manager |
| `executive_leadership` | Executive Leadership |
| `system_administrator` | System Administrator |

**Rules**

- The set is closed (spec Assumptions: "Roles are a fixed set"). Adding a value
  requires a spec change, not configuration.
- Stored values are snake_case and stable; labels are display-only and may be
  reworded without a migration.
- Satisfies FR-009 (the nine roles) and, together with `User.role`'s constraint,
  FR-010 (rejection of anything outside the set).

---

## User

App: `apps/accounts`. Custom model set as `AUTH_USER_MODEL` in the **first**
migration (research.md §2 — this cannot be retrofitted).

Base: `AbstractBaseUser` + `PermissionsMixin`.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `email` | EmailField | unique, required, indexed | `USERNAME_FIELD`; normalized to lowercase on save |
| `password` | CharField | required | Inherited; Django-hashed, never stored plaintext |
| `first_name` | CharField(150) | blank allowed | |
| `last_name` | CharField(150) | blank allowed | |
| `role` | CharField(32) | required, `choices=Role.choices`, DB `CheckConstraint` limiting to the nine values | FR-009, FR-010 |
| `is_active` | BooleanField | default `True` | Inactive users cannot authenticate |
| `is_staff` | BooleanField | default `False` | Django admin access only — **not** an RBAC signal |
| `is_superuser` | BooleanField | default `False` | From `PermissionsMixin`; **never** bypasses `HasRole` (spec edge case) |
| `date_joined` | DateTimeField | auto on create | |
| `last_login` | DateTimeField | null | Inherited |

`USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = ["role"]` — so
`createsuperuser` cannot produce an account without a role.

**Validation rules**

- `email` unique, case-insensitively (normalized before save).
- `role` must be one of the nine values. Enforced three ways: field `choices`
  (form/serializer validation), model `full_clean()`, and a database
  `CheckConstraint` named `user_role_valid` that holds even against raw SQL or
  `QuerySet.update()`.
- A user with a null/blank/unrecognised `role` is permitted to perform nothing
  restricted (FR-014). This is a permission-layer behaviour, not a model
  behaviour — the model prevents the state from being created; the permission
  layer refuses to fail open if it somehow exists.

**Relationships**

- Referenced by `AuditLog.actor` (nullable, `SET_NULL`). No other model in this
  phase references `User`.

**State transitions**

- `is_active`: `True ⇄ False` — deactivation blocks authentication but does not
  delete the account or its audit history.
- `role`: any of the nine → any other of the nine, by a System Administrator
  only (FR-017). Every change writes an `AuditLog` entry (FR-020) and takes
  effect on the user's next request without restart (FR-016).

**Manager**

`UserManager.create_user(email, password, role, **extra)` and
`create_superuser(...)` — both require `role`; `create_superuser` sets
`is_staff`/`is_superuser` but still requires an explicit role, since superuser
status confers no RBAC privilege.

---

## AuditLog

App: `apps/audit`. Append-only. Written only through
`apps.audit.services.record_action()`, inside the caller's transaction
(research.md §6).

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | BigAutoField | PK | |
| `timestamp` | DateTimeField | auto on create, indexed, not editable | When the action occurred (FR-018) |
| `actor` | FK → User | null, `on_delete=SET_NULL`, `related_name="audit_entries"` | Who acted |
| `actor_identifier` | CharField(254) | required | Snapshot of actor's email at action time — survives user deletion (FR-021) |
| `actor_role` | CharField(32) | blank allowed | Snapshot of the role held *at action time*, not the current one |
| `action` | CharField(64) | required, indexed | e.g. `user.created`, `user.role_changed` |
| `target_type` | CharField(64) | required, indexed | Model label of the affected record, e.g. `accounts.User` |
| `target_id` | CharField(64) | required, indexed | Affected record's identifier as a string — generic across PK types (FR-023) |
| `outcome` | CharField(16) | required, `choices=("succeeded", "refused")` | Distinguishes refused attempts from successful ones (FR-018, Story 3 scenario 3) |
| `before` | JSONField | null | Changed values prior to the action; null where not applicable |
| `after` | JSONField | null | Changed values after the action; null where not applicable |
| `context` | JSONField | null | Optional non-sensitive supporting detail for later modules |

**Indexes**

- `(target_type, target_id, timestamp)` — serves FR-024's chronological
  retrieval of a specific record's history as a single index scan.
- `timestamp` — recent-activity listing.
- `actor` — actor-scoped queries.

**Immutability rules (FR-019, SC-005)** — enforced at two layers, per
research.md §5:

1. **ORM layer**: `save()` raises when `self.pk` is set (any update attempt);
   `delete()` raises; the custom manager's queryset overrides `update()` and
   `delete()` to raise.
2. **Database layer**: a PostgreSQL trigger `audit_log_immutable`
   (`BEFORE UPDATE OR DELETE ON audit_auditlog`) raises an exception, installed
   by a `migrations.RunSQL` operation with a matching reverse SQL. This is the
   binding guarantee — it holds for raw SQL, `bulk_update`, admin actions, and
   direct psql sessions.

**Atomicity rule (FR-022)**

`record_action()` is called inside the same `transaction.atomic()` block as the
action it records. If the audit insert fails, the whole transaction rolls back
and the action does not commit. No `on_commit`, no signal, no async task.

**Field-content rules**

- `before`/`after` hold only the fields that changed, JSON-serializable.
- Password hashes, raw passwords, and any secret MUST NOT be written into
  `before`/`after`/`context`. For a password change, record the fact of the
  change, never the values.
- `actor_identifier` is required even when `actor` is set, so deletion of the
  user never leaves an unattributable record.

**Actions recorded in this phase (FR-020)**

| Action | Target | `before` / `after` |
|---|---|---|
| `user.created` | `accounts.User` | `before` null; `after` holds email, role, is_active |
| `user.role_changed` | `accounts.User` | `before`/`after` hold `{"role": ...}` |
| `user.updated` | `accounts.User` | Changed non-credential fields only |
| `user.deactivated` | `accounts.User` | `{"is_active": true}` → `{"is_active": false}` |

Later modules (Customer, Policy, Claim, Risk, Fraud, CRM) reuse this structure
unchanged by supplying their own `action`/`target_type` values (FR-023).

**Retention**

No deletion or archival policy in this phase — records are append-only and kept
indefinitely. A retention policy, if ever needed, is a later spec's decision and
would itself have to reconcile with FR-019.

---

## HealthStatus (transient — not persisted)

App: `apps/health`. A plain in-memory structure produced per request by
`apps/health/checks.py` and serialized directly. No table, no migration.

| Field | Type | Values |
|---|---|---|
| `status` | string | `healthy` \| `unhealthy` |
| `checks.database.status` | string | `ok` \| `error` |
| `checks.cache.status` | string | `ok` \| `error` |

**Rules**

- `status` is `healthy` only when every dependency check is `ok`.
- The structure carries **no** host names, ports, connection strings,
  credentials, exception text, or version strings (FR-028). Failure detail is
  logged server-side only.
- Each probe carries its own 2-second timeout so the whole response is bounded
  well inside SC-006's 5 seconds (research.md §8).

See [contracts/health.md](./contracts/health.md) for the wire format and status
codes.

---

## Entity relationship summary

```text
User (1) ──── SET_NULL ────> (0..n) AuditLog
  │                                  │
  │ exactly one Role                 │ snapshots actor_identifier + actor_role
  │ (enum, closed set of 9)          │ so identity survives User deletion
  ▼                                  ▼
Role (enum, no table)          append-only; never updated or deleted

HealthStatus — transient, no persistence, no relationships
```

---

## Requirements coverage

| Requirement | Where satisfied |
|---|---|
| FR-008 | `User` with `AbstractBaseUser` authentication |
| FR-009 | `User.role` required, single value from `Role` |
| FR-010 | `choices` + `full_clean()` + `user_role_valid` CheckConstraint |
| FR-014 | Deny-by-default in `HasRole`; model prevents the invalid state existing |
| FR-016 | Role read per request from the DB; no cached role claim |
| FR-017 | Account/role mutation endpoints restricted to `system_administrator` |
| FR-018 | `AuditLog` fields: actor, action, target_type/id, timestamp, outcome, before/after |
| FR-019 | ORM guard + `audit_log_immutable` DB trigger |
| FR-020 | `user.created`, `user.role_changed` action records |
| FR-021 | `SET_NULL` FK + `actor_identifier` / `actor_role` snapshots |
| FR-022 | `record_action()` inside the action's transaction |
| FR-023 | Generic `target_type` / `target_id` / JSON before-after shape |
| FR-024 | `(target_type, target_id, timestamp)` index + ordered retrieval endpoint |
| FR-026 | `HealthStatus.checks` reports database and cache individually |
| FR-028 | `HealthStatus` field set excludes all sensitive detail |
