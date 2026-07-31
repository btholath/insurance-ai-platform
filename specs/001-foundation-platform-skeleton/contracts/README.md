# Interface Contracts: Foundation — Platform Skeleton & Role-Based Access

**Feature**: `001-foundation-platform-skeleton` | **Date**: 2026-07-30

The platform exposes an HTTP interface (Django + Django REST Framework). These
documents define the endpoints this phase introduces, and — critically — the
role required for each one, since Principle III makes that part of the contract
rather than an implementation detail.

| Contract | Endpoints | Auth |
|---|---|---|
| [health.md](./health.md) | `GET /health/` | **Public** — the only unauthenticated endpoint |
| [users.md](./users.md) | User creation, retrieval, role change | System Administrator |
| [audit.md](./audit.md) | Audit history retrieval | Compliance Officer, System Administrator |

Placeholder role-restricted endpoints in `customers`, `policies`, and `claims`
are described at the end of this file.

---

## Conventions applying to every endpoint

**Base path**: all authenticated endpoints are mounted under `/api/`. The health
endpoint is at the root (`/health/`) so container and monitoring tooling can
reach it without knowing the API prefix.

**Content type**: `application/json` for requests and responses.

**Authentication**: Django session authentication. No token, JWT, or API-key
scheme in this phase (out of scope — "session management features beyond basic
authenticated sign-in").

**Authorization**: every non-public endpoint declares its permitted roles below.
Enforcement is server-side via the single `HasRole` permission class
(FR-011, FR-015). A role change takes effect on the very next request (FR-016).
`is_superuser` grants no additional API access (spec edge case).

### Standard status codes

| Code | Meaning in this API |
|---|---|
| `200 OK` | Request succeeded |
| `201 Created` | Resource created |
| `400 Bad Request` | Validation failure; body lists offending fields |
| `403 Forbidden` | Authenticated, but role not permitted — **or** unauthenticated on a collection route |
| `404 Not Found` | Resource does not exist — **or** unauthenticated/unpermitted on a detail route (see below) |
| `503 Service Unavailable` | Health endpoint only: a dependency is unreachable |

### Existence non-disclosure rule (FR-012)

On **detail** routes (any route addressing a specific record), an
unauthenticated caller receives **`404 Not Found`**, never `403`. A `403` on a
detail route would confirm the record exists, which FR-012 forbids: the system
"MUST refuse a restricted action requested by an unauthenticated caller,
without disclosing whether the target record exists."

On **collection** routes there is no record whose existence could leak, so
unauthenticated callers receive `403 Forbidden`.

An authenticated caller whose role is not permitted receives `403` on
collection routes and `404` on detail routes, for the same reason.

### Error response shape

```json
{ "detail": "Not found." }
```

Validation errors use DRF's field-keyed form:

```json
{ "role": ["\"auditor\" is not a valid choice."] }
```

Error bodies never contain stack traces, SQL, connection details, or
configuration values.

### Audit side effects

Endpoints that create or modify a `User` write an `AuditLog` record inside the
same transaction (FR-020, FR-022). If the audit write fails, the request fails
and the change is not committed. Each contract notes its audit action name.

---

## Placeholder role-restricted endpoints

The `customers`, `policies`, and `claims` apps carry no business models in this
phase (spec Out of Scope). Each exposes exactly one endpoint whose sole purpose
is to exercise the RBAC mechanism in the modules where later phases will use it
(spec Assumptions: "Demonstration surface for access control").

| Endpoint | Method | Permitted roles | Response |
|---|---|---|---|
| `/api/customers/placeholder/` | `GET` | Customer Service, Underwriter, System Administrator | `200 {"module": "customers", "status": "placeholder"}` |
| `/api/policies/placeholder/` | `GET` | Underwriter, Product Manager, System Administrator | `200 {"module": "policies", "status": "placeholder"}` |
| `/api/claims/placeholder/` | `GET` | Claims Adjuster, Fraud Analyst, System Administrator | `200 {"module": "claims", "status": "placeholder"}` |

These are collection routes, so unauthenticated callers receive `403`. Callers
in any other role receive `403`. They return no data and have no audit side
effect. They exist to be tested (FR-033) and are replaced by real endpoints when
the corresponding module is specified.
