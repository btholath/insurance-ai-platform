# Contract: Risk Assessment API

**Feature**: 005-risk-scoring-engine | **Base path**: `/api/risk/`

Mounted at a **top-level prefix**, not nested under `/api/customers/`. The reason
is load-bearing and tested — see §1 of [research.md](../research.md): a nested
path is swallowed by the existing `/api/customers/` registry entry and would
mis-audit every risk refusal under the wrong module and the wrong role set.

Auth: session or token per the platform default. All routes require
authentication (FR-046).

## Roles

| Role | Read assessments | Recompute |
|---|---|---|
| Risk Manager | ✅ | ✅ |
| System Administrator | ✅ | ✅ |
| Underwriter | ✅ | ❌ |
| Fraud Analyst | ✅ | ❌ |
| Compliance Officer | ✅ | ❌ |
| Claims Adjuster | ❌ | ❌ |
| Customer Service | ❌ | ❌ |
| Product Manager | ❌ | ❌ |
| Executive Leadership | ❌ | ❌ |

Five read roles (FR-042), two recompute roles (FR-043). Enforced by `HasRole` at
the view layer (FR-044). Note **Customer Service reads customers but not their
risk assessments** — the divergence that makes the fourth registry entry
meaningful.

---

## `GET /api/risk/assessments/`

List current assessments. Paginated, 50 per page, ordered by `id` (stable).

**Query parameters**

| Param | Effect |
|---|---|
| `tier` | Exact match on tier (`low`, `moderate`, `elevated`, `high`) |
| `customer` | Assessments for one customer id |
| `min_score` / `max_score` | Inclusive score bounds |

**200 response**

```json
{
  "count": 3000,
  "next": "http://localhost:8001/api/risk/assessments/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "customer": 1,
      "client_id": "CL-00001",
      "score": 15,
      "tier": "low",
      "tier_label": "Low",
      "rule_set_version": "1.0.0",
      "computed_at": "2026-08-17T09:14:22.418Z",
      "computed_by": "risk.manager@example.com",
      "is_stale": false,
      "factors": [ ... ]
    }
  ]
}
```

**`factors` is present on the list route, not only on detail.** This is a
deliberate contract decision under Principle IV: there must exist **no route
that returns a score without the reasoning that produced it** (FR-019, FR-024).
Omitting factors from the list for payload economy would create exactly such a
route. Five rows per assessment × 50 per page is a bounded cost, and
`prefetch_related` keeps it off the N+1 path.

**403** for a role outside the read set. **401** unauthenticated.

---

## `GET /api/risk/assessments/{id}/`

Retrieve one assessment with its full explanation.

**200 response**

```json
{
  "id": 42,
  "customer": 42,
  "client_id": "CL-00042",
  "score": 65,
  "tier": "high",
  "tier_label": "High",
  "rule_set_version": "1.0.0",
  "computed_at": "2026-08-17T09:14:22.418Z",
  "computed_by": "risk.manager@example.com",
  "is_stale": true,
  "stale_reason": "Customer or policy data changed after this assessment was computed",
  "factors": [
    {
      "factor": "age",
      "factor_label": "Customer age",
      "status": "evaluated",
      "observed_value": "23",
      "band_label": "under 25",
      "points": 15
    },
    {
      "factor": "policy_type",
      "factor_label": "Policy coverage type",
      "status": "evaluated",
      "observed_value": "Auto",
      "band_label": "Auto",
      "points": 15
    },
    {
      "factor": "claims_history",
      "factor_label": "Claims history",
      "status": "evaluated",
      "observed_value": "1 claim",
      "band_label": "one or more claims with a non-zero amount",
      "points": 20
    },
    {
      "factor": "claims_ratio",
      "factor_label": "Claims-to-premium ratio",
      "status": "evaluated",
      "observed_value": "1.42",
      "band_label": "1–3× premium",
      "points": 10
    },
    {
      "factor": "denied_claim",
      "factor_label": "Denied claim present",
      "status": "evaluated",
      "observed_value": "no",
      "band_label": "no denied claim",
      "points": 5
    }
  ]
}
```

> The `points` above sum to 65, matching `score`. **This is an invariant of every
> response** (FR-021, SC-001), not a property of this example.

**Always exactly five factor entries** — one per factor in the rule set,
including those contributing zero (FR-022) and those that could not be evaluated
(FR-023). A zero contribution serializes as `"points": 0` with
`"status": "evaluated"`; a non-evaluable factor as:

```json
{
  "factor": "claims_ratio",
  "factor_label": "Claims-to-premium ratio",
  "status": "not_evaluable",
  "observed_value": "",
  "band_label": "",
  "points": 0,
  "unevaluable_reason": "Customer has no live policy, so premium is unknown"
}
```

**`stale_reason`** is present only when `is_stale` is true. Note `is_stale`
over-reports rather than under-reports — any change to the customer, a live
policy, or a live claim sets it, including changes to fields no factor reads
(§4 of research). Over-reporting is the safe direction.

**404** — returned both when the assessment does not exist and when the caller
lacks read permission, with an **identical body** in both cases (FR-045, SC-010).
Achieved by normalising DRF's `Http404` to `NotFound()` in `get_object()`, the
same technique as `ClaimViewSet.get_object()`; **not** by editing the shared
exception handler, which FR-041 forbids.

---

## `GET /api/risk/assessments/by-customer/{customer_id}/`

Same payload as detail, addressed by customer rather than assessment id — the
practical lookup, since callers hold a customer.

**404** when the customer has no assessment. The body distinguishes this from a
low score (FR-029):

```json
{"detail": "This customer has not been assessed."}
```

> This message is returned **only** to callers who hold the read role. A caller
> without it receives the generic `{"detail": "Not found."}`, so the
> distinguishing message never becomes an existence oracle (FR-045).

---

## `POST /api/risk/assessments/recompute/`

Recompute one customer's assessment on demand (FR-034). The **only** write route
this feature adds.

**Request**

```json
{"customer": 42}
```

**200 response**: the full assessment payload above, freshly computed. Creates
the assessment if the customer had none (User Story 3, scenario 5).

**Behaviour**

- Recomputes exactly one customer; no other assessment is touched (FR-034).
- Runs in one transaction with `select_for_update()` on the customer, so two
  concurrent recomputes serialize and neither can produce a score beside another
  run's factors (FR-035, FR-037).
- Writes an audit entry with before/after score **inside the same transaction**
  (FR-053), including when the score is unchanged (FR-049).
- Never triggered implicitly — no other endpoint in the platform causes a
  recomputation (FR-036).

**422** when the customer cannot be scored (no live policy):

```json
{"detail": "Customer CL-00042 has no live policy, so a risk score cannot be computed."}
```

Distinct from a validation 400 and from a 404 — the request was well-formed and
the customer exists, but the data does not support a score (FR-018).

**403** for a read-only role such as Underwriter — permitted to read, not to
recompute (FR-043, User Story 6 scenario 3). No score changes.

---

## Routes deliberately absent

- **No `PUT`/`PATCH`/`DELETE` on assessments.** A score is engine output, never
  user input. An editable score would be unexplainable by construction — its
  factors would no longer describe it — which is Principle IV's core failure.
- **No `RiskFactor` write route**, for the same reason.
- **No score field on any customer write route.** `CustomerSerializer.risk_score`
  becomes read-only (see data-model.md).
- **No bulk recompute over the API.** Batch is the management command
  ([computerisk-command.md](./computerisk-command.md)); an HTTP request that
  scores 3,000 customers synchronously is a timeout waiting to happen, and doing
  it asynchronously would need the queue Phase 3b owns.
- **No "explain" route separate from the score.** The explanation is not an
  optional expansion of a score — the two are one response.

---

## Audit registry entry (FR-041)

Registered in `apps/core/audit_routes.register_defaults()` as the **fourth**
entry. Expected to be a single `register(...)` call with **no change to
`exception_handlers.py`**:

```text
prefix        = "/api/risk/"
target_type   = "risk.RiskAssessment"
action_prefix = "risk"
view_roles    = (RISK_MANAGER, UNDERWRITER, FRAUD_ANALYST,
                 COMPLIANCE_OFFICER, SYSTEM_ADMINISTRATOR)
write_roles   = (RISK_MANAGER, SYSTEM_ADMINISTRATOR)
```

Derived action names follow the existing method map: `risk.viewed` (GET),
`risk.created` (POST). The recompute route is a POST, so a refused recompute
records as `risk.created` — accurate in the registry's vocabulary, and the
engine's own success entries use the more specific `risk.computed` /
`risk.batch_computed` (see the command contract).

If implementing this requires editing `exception_handlers.py`, that is a
**failure of FR-041 and SC-009**, not a routine adjustment.
