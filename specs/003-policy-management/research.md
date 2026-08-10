# Phase 0 Research: Policy Management

**Feature**: `003-policy-management` | **Date**: 2026-08-09

All Technical Context unknowns are resolved below. Every decision is grounded
in code that already exists in this repository (Phases 1 and 2a) or in the
verified shape of the source dataset.

---

## 1. Generalizing the refusal handler — the one genuinely new mechanism

**Decision**: refactor `apps/core/exception_handlers.py` from a
customer-specific handler into a **registry keyed by route prefix**. Each
registered module supplies its route prefix, its audit `target_type`, its
action-name prefix, and its view/write role sets. The handler looks the
request up in the registry rather than hardcoding one module.

**Rationale**: the shipped handler hardcodes customer knowledge in four
distinct places:

| Location | Current value |
|---|---|
| `_is_customer_route()` | `request.path.startswith("/api/customers/")` |
| `_METHOD_ACTIONS` | `"customer.viewed"`, `"customer.created"`, … |
| `_is_refusal()` | `from apps.customers.views import VIEW_ROLES, …` |
| `_record_refusal()` | `target_type="customers.Customer"` |

FR-031 and FR-032 require the same behavior for policy routes. Copy-pasting a
`_is_policy_route()` alongside would mean a third copy when Claims arrives,
with four hardcoded facts each — twelve places for the three modules to drift
apart. The registry makes adding Claims a data entry rather than a code change,
which matters because Claims is already committed as the next spec.

**Shape**:

```python
# apps/core/audit_routes.py
AuditedRoute = namedtuple("AuditedRoute", "prefix target_type action_prefix "
                                          "view_roles write_roles")
REGISTRY = [...]  # populated at app-ready, not import time
```

**Why not a per-view attribute instead**: attaching `audit_target_type` to the
viewset reads more locally, but the handler runs on the `PermissionDenied`
path where `context["view"]` exists — *except* for `NotAuthenticated` raised
before view dispatch resolves, and for 404s on unrouted paths. A path-prefix
registry works uniformly for every case the handler must cover. Recorded
because the view-attribute approach looks cleaner until that gap surfaces.

**Regression risk, and how it is contained**: this refactor touches a shipped,
tested mechanism. The existing 22 customer audit tests in
`apps/customers/tests/test_audit.py` are the regression suite — they must pass
**unchanged**, with no edits to accommodate the refactor. If a customer audit
test needs modifying, the refactor has changed customer behavior and is wrong.

**Alternatives considered**:
- *Second parallel handler for policies*: rejected — three copies by Claims.
- *Middleware instead of a DRF handler*: rejected for the Phase 2a reason —
  cannot distinguish a permission 403 from a validation 400 without
  re-deriving intent from the response.

---

## 2. The refusal-vs-miss distinction, now with a wider permitted set

**Decision**: keep the existing role-consulting logic, driven by the registry's
per-module role sets.

**Rationale**: FR-032 requires that a permitted user requesting a missing
policy produce **no** refusal entry. The existing `_is_refusal()` already
solves this correctly for customers; the only change is that the allowed-role
sets come from the registry rather than a hardcoded import.

**A real asymmetry between the modules, worth stating**: the policy view set is
*eight* roles (everyone except Executive Leadership), while the customer view
set is seven. Product Manager may read policies but not customers. This means
a Product Manager hitting a missing policy is an ordinary miss, while the same
user hitting a missing customer is a refusal — correct in both cases, but only
because the role sets are per-module. A single shared role set would get one of
the two wrong. This is precisely why the registry carries roles per entry
rather than assuming platform-wide sets.

---

## 3. The Customer foreign key and archived-customer reads

**Decision**: `ForeignKey(Customer, on_delete=models.PROTECT, related_name="policies")`,
with all customer lookups in the policy write path going through
`Customer.all_objects`.

**Rationale**:

- **`PROTECT`, not `CASCADE`**: FR-021 and the Claims dependency require that
  removing a policy never destroys downstream history. `CASCADE` would mean a
  hard `Customer.objects.delete()` silently destroying policies. Customer
  removal through the API is archival and never reaches this, but `PROTECT` is
  the backstop for the path that does — as the Phase 2a live verification
  showed, a hard delete on a real database is something that actually happens.
- **`all_objects` for FK resolution**: FR-008 and FR-022 require a policy to
  remain readable, with its link intact, after its customer is archived. If
  the serializer resolved the FK through `Customer.objects` (which hides
  archived rows), reading such a policy would fail validation or 404 — exactly
  the orphaning FR-022 forbids. This is the same reasoning that made
  `all_objects` load-bearing in Phase 2a, applied to a different failure.
- **`related_name="policies"`**: gives `customer.policies` for FR-019, and
  `select_related("customer")` on the list route to avoid N+1 across a
  50-record page.

**The subtlety that needs its own test**: `related_name` traversal uses the
related model's `_default_manager`. `Policy.objects` hides archived
*policies*, so `customer.policies.all()` correctly excludes archived policies
— but the reverse direction (archived customer → live policy) must still work.
Both directions are asserted separately, because they fail independently.

**Create-time refusal (FR-014)**: creating a policy for an *archived* customer
is refused, naming `customer`. Validation resolves through `all_objects` (so
the customer is found) and then explicitly checks `archived_at is None`. If it
resolved through `objects` instead, the refusal would be "customer does not
exist" — technically a refusal, but a misleading one that would send an
underwriter hunting for a missing record rather than a removed one.

---

## 4. Policy identity: no external reference

**Decision**: policies are identified by the platform's own primary key. No
`policy_id` external reference field.

**Rationale**: FR-007 requires a stable identifier for Claims to reference, and
the internal PK satisfies it. Unlike Customer — where FR-002 required storing
the source dataset's `Client_ID` because it is the idempotency key — the
dataset has **no policy identifier column**. Verified: the 20 columns include
`Policy_Type`, `Policy_Start_Date`, `Policy_End_Date`, `Policy_Premium_USD`,
and no policy ID.

Inventing a `POL-#####` reference to mirror Customer's shape would be
symmetry for its own sake: nothing external supplies it, nothing needs to
reconcile against it, and it would need the same generation-under-lock
machinery for no requirement. The loader's idempotency key is
`(customer, policy_type)` per FR-039, which is what the data actually provides.

**Alternatives considered**:
- *`POL-#####` generated reference*: rejected as above. If a future export
  gains a policy number column, adding it then is a migration, not a redesign.

---

## 5. Loader match key: `(customer, policy_type)`

**Decision**: match existing policies on customer **and** coverage type, per
FR-039. Enforced by a `UniqueConstraint(customer, policy_type)` scoped to live
rows.

**Rationale**: verified against the file — every `Client_ID` appears exactly
once, and `(Client_ID, Policy_Type)` is unique across all 3,000 rows, so the
key works today. It also survives the case the dataset does not exercise: a
customer holding auto *and* home cover reconciles as two distinct policies,
whereas matching on customer alone would overwrite one with the other on every
re-run — silently, and only for customers the current export cannot produce.

**The constraint must exclude archived rows**: a plain
`UniqueConstraint(customer, policy_type)` would make archival poisonous —
archive a customer's auto policy, and they can never hold auto cover again,
because the archived row still occupies the constraint. So:

```python
UniqueConstraint(
    fields=["customer", "policy_type"],
    condition=Q(archived_at__isnull=True),
    name="policy_unique_live_type_per_customer",
)
```

This is a **deliberate divergence** from Customer, where `client_id`
uniqueness spans archived rows *because* FR-021 requires the reference to stay
reserved. Here the opposite is required: FR-021's archival must not permanently
consume a coverage slot. Same word, opposite requirement — worth stating
plainly so the inconsistency is not later "fixed" into matching Customer.

**Consequence for the loader**: matching therefore uses
`Policy.all_objects.filter(customer=…, policy_type=…, archived_at__isnull=True)`
— an archived policy is *not* reconciled against; the load creates a fresh
live one. That is correct: FR-038 requires one **live** policy per source row,
and resurrecting an archived policy would silently undo a deliberate removal.

---

## 6. Expiry as a derived filter, not stored state

**Decision**: FR-020's "coverage has already ended" filter is
`end_date__lt=timezone.localdate()`, evaluated per request. No stored status
field, no scheduled job.

**Rationale**: a stored `is_expired` flag is wrong the day after it is written
unless something maintains it, and maintaining it means a periodic job whose
failure mode is silently stale data. Comparing to the request date is always
correct and costs an indexed range scan.

`localdate()` rather than `now().date()` because the fields are calendar dates,
not timestamps; the project runs `USE_TZ=True` with `TIME_ZONE="UTC"`, so these
coincide today, but the intent is "today's date", not "the date part of an
instant".

**Index**: `end_date` gets `db_index=True`. Range predicates use a B-tree
effectively, unlike the trailing-wildcard `icontains` searches in Phase 2a.

---

## 7. Money: `DecimalField`, never float

**Decision**: `premium_usd = DecimalField(max_digits=10, decimal_places=2)`
with a `CheckConstraint` requiring `> 0`.

**Rationale**: floats cannot represent currency exactly, and the dataset's
premiums carry two decimal places (100.68 – 4997.79). `max_digits=10` allows
up to 99,999,999.99 — far above the observed range, but a commercial policy
premium is not bounded by this consumer-oriented sample, and widening a numeric
column later is a table rewrite.

FR-011 refuses zero and negative premiums. The dataset's minimum is 100.68 so
this is not a case the data exercises; it is refused because a zero-premium
policy is a data error, not a free policy, and Claims will compute against
premium values.

**`renewal_probability`**: `DecimalField(max_digits=3, decimal_places=2,
null=True)` — identical to Customer's score fields, for the same reason
(exact two-decimal comparison in tests, and `None` distinguishable from
`0.00`). Verified: the dataset's renewal probabilities span exactly 0.0–1.0,
so a genuine `0.00` exists in the data and the absent-vs-zero distinction is
exercised by real rows, not just synthetic ones.

---

## 8. Date coherence validation

**Decision**: `end_date > start_date` enforced in the serializer (naming both
fields per FR-010) **and** as a `CheckConstraint` backstop.

**Rationale**: this is a cross-field rule, so it lives in the serializer's
`validate()` rather than a field validator — which is what lets the error name
the date pair rather than one field. The DB constraint catches any path that
bypasses the serializer.

Verified: zero rows in the dataset have `end_date <= start_date`, so no
legitimate source row is refused by this rule.

**Deliberately not validated**: backdated or future-dated policies. A policy
may legitimately start in the past or the future — only the ordering is
incoherent, not the absolute position. Adding a "start date must not be in the
past" rule would refuse most of the dataset, whose start dates run from 2022.

---

## 9. Extending the loader rather than adding a second command

**Decision**: extend `loadcustomers` to create policies from the same row,
renaming it **`loaddataset`** with `loadcustomers` retained as a thin alias.

**Rationale**: FR-036 requires one command loading both, and a policy is
meaningless without its customer — they come from the same row of the same
file. A separate `loadpolicies` would need to re-read the file, re-resolve
customers, and would let the two drift out of sync.

The rename is because "loadcustomers" will be actively misleading once it also
loads policies and (next spec) claims. The alias keeps the Phase 2a quickstart,
README, and any operator muscle memory working — the cost is one thin subclass,
and breaking a documented command to save it would be a poor trade.

**Per-row transaction spans both records (FR-045)**: the customer and its
policy are created in **one** `transaction.atomic()` per row. FR-045 requires
that a refused policy not silently discard the customer from the same row —
but the stronger reading is that a row either lands completely or not at all.
A half-landed row (customer present, policy missing) is exactly the state an
operator cannot reason about, and re-running would then create the policy while
reporting the customer as "updated", making the counts misleading.

So: **policy validation runs before either record is written.** Both counts
reported per row are consistent, and FR-045's "must not silently discard the
customer" is satisfied by reporting the row as refused with its reason, rather
than by leaving a partial write behind.

**Counts are reported separately (FR-044)**: `Customers — created/updated/refused`
and `Policies — created/updated/refused` on separate lines. With row-level
atomicity a refused row increments both refused counts, which is truthful: the
row was refused, not half-applied.

---

## 10. Removing the Phase 1 placeholder

**Decision**: delete `PlaceholderView` from `apps/policies/views.py`, remove its
route, and delete `apps/policies/tests/test_views.py` in full, replacing it
with the real policy test modules. Assert `/api/policies/placeholder/` returns
404 (SC-011).

**Rationale**: identical to Phase 2a's FR-043 handling. The existing test file
asserts `{"module": "policies", "status": "placeholder"}` and covers nothing
else.

Note the placeholder's current roles are Underwriter, Product Manager, and
System Administrator — close to but not the same as FR-026's eight-role view
set. The placeholder's roles carry no authority here; FR-026 is the spec.

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Refusal handler scope | Registry keyed by route prefix; existing customer audit tests are the regression suite |
| Refusal vs miss | Existing role logic, roles supplied per-module (policy view set is 8 roles, customer 7) |
| Customer FK | `PROTECT` + `related_name="policies"`; write path resolves via `all_objects` |
| Policy identity | Internal PK only — the dataset has no policy ID column |
| Loader match key | `(customer, policy_type)`, unique **among live rows only** |
| Archived uniqueness | Deliberately opposite to Customer: archival must not consume a coverage slot |
| Expiry | Derived per request from `end_date`, never stored |
| Money | `DecimalField(10,2)`, `> 0` constraint |
| Date coherence | Serializer `validate()` naming both fields + DB constraint |
| Loader shape | Extend to `loaddataset`; `loadcustomers` kept as alias; one transaction per row spanning both records |
