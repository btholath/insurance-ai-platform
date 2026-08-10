# Quickstart: Validating Policy Management

**Feature**: `003-policy-management`

Runnable scenarios proving the feature works end to end. Each maps to success
criteria in [spec.md](./spec.md). Field shapes are in
[data-model.md](./data-model.md); request/response detail is in
[contracts/](./contracts/).

**Database note**: these scenarios write to the dev database. Confirm before
running the ones that create or archive records, and prefer the test suite
where it proves the same property.

---

## Prerequisites

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web pytest        # baseline green before starting
```

Tests run inside the `web` container. The image has no source volume mount, so
`docker compose up --build -d` is required after host-side edits.

---

## 1. Test suite and coverage (SC-010)

```bash
docker compose exec web pytest apps/policies/ -v
docker compose exec web pytest --cov=apps.policies --cov-report=term-missing
```

**Expect**: all green; `apps/policies` coverage **≥ 95%**.

Per Principle V, tests precede the implementation they cover.

### The regression check that matters most

```bash
docker compose exec web pytest apps/customers/tests/test_audit.py -v
```

**Expect**: all 22 pass, **unmodified**. This feature refactors the shared
refusal handler that Phase 2a shipped. If any customer audit test needed
editing to accommodate the refactor, the refactor changed customer behavior and
is wrong.

---

## 2. Load customers and policies together (SC-001)

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv
```

**Expect**:

```
Customers — created: 3000  updated: 0  refused: 0
Policies  — created: 3000  updated: 0  refused: 0
```

Confirm every policy is attached to a distinct customer:

```bash
docker compose exec web python manage.py shell -c "
from apps.policies.models import Policy
print('policies:', Policy.objects.count())
print('distinct customers:', Policy.objects.values('customer').distinct().count())
print('orphans:', Policy.objects.filter(customer__isnull=True).count())"
```

**Expect**: `3000`, `3000`, `0`.

---

## 3. Idempotency (SC-002)

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv
```

**Expect**: `Policies — created: 0  updated: 3000  refused: 0`, count still 3000.

Confirm no customer holds a duplicate live policy of one type:

```bash
docker compose exec web python manage.py shell -c "
from django.db.models import Count
from apps.policies.models import Policy
dupes = (Policy.objects.values('customer','policy_type')
         .annotate(n=Count('id')).filter(n__gt=1))
print('duplicate (customer, type) pairs:', list(dupes) or 'NONE')"
```

**Expect**: `NONE`.

---

## 4. The backward-compatible alias

```bash
docker compose exec web python manage.py loadcustomers data/Insurance_Dataset.csv
```

**Expect**: identical output to `loaddataset` — including the policy counts.
The Phase 2a command name still works and now loads policies too.

---

## 5. Read performance (SC-003, SC-004)

Sign in as an Underwriter, then:

```bash
# Single policy — expect < 1 second (SC-003)
time curl -s -b cookies.txt http://localhost:8000/api/policies/1/ | jq '.policy_type'

# One customer's policies — expect < 2 seconds (SC-004)
time curl -s -b cookies.txt "http://localhost:8000/api/policies/?customer=1" | jq '.count'

# Filtered list — expect < 2 seconds (SC-004)
time curl -s -b cookies.txt "http://localhost:8000/api/policies/?policy_type=Auto" | jq '.count'
```

Confirm pagination is bounded and the embedded customer costs no extra queries:

```bash
curl -s -b cookies.txt "http://localhost:8000/api/policies/" \
  | jq '{count, returned: (.results|length), first_customer: .results[0].customer.client_id}'
```

**Expect**: `count: 3000`, `returned: 50`, a populated `client_id`.

---

## 6. Filters (FR-019, FR-020)

```bash
for f in "policy_type=Auto" "policy_type=Health" "expired=true"; do
  echo -n "$f -> "
  curl -s -b cookies.txt "http://localhost:8000/api/policies/?$f" | jq '.count'
done
```

**Expect**, verified against the source file: `Auto` 767, `Property` 767,
`Life` 727, `Health` 739 — summing to exactly 3000.

`expired=true` is derived from today's date, so its count **grows over time** —
that is the filter working, not drift. As of 2026-08-09 the dataset holds
**1,171** already-expired policies, against end dates spanning 2025-06-17 to
2028-06-15. Expect a count at or above that figure, never below.

---

## 7. Validation boundaries (SC-007)

Each rule refuses an invalid value and accepts a valid boundary.

```bash
# end_date == start_date -> 400 naming both dates (FR-010)
# end_date one day later  -> 201
# premium_usd "0.00"      -> 400 naming premium_usd (FR-011)
# premium_usd "0.01"      -> 201
# policy_type "Motor"     -> 400 naming policy_type (FR-009)
# renewal_probability "1.01" -> 400; "1.00" and "0.00" -> 201 (FR-012)
# customer 999999         -> 400 naming customer (FR-013)
```

**Absent ≠ zero** (FR-004) — a policy created without a renewal probability:

```bash
curl -s -b cookies.txt http://localhost:8000/api/policies/<new-id>/ \
  | jq '.renewal_probability'
```

**Expect**: `null` — not `"0.00"`. The dataset contains genuine `0.0` renewal
probabilities, so this distinction is exercised by real loaded rows.

---

## 8. Multiple policies per customer (SC-009)

```bash
# Customer 1 already holds an Auto policy from the load.
# POST a Health policy for customer 1 -> 201
# POST a second Auto policy for customer 1 -> 400 naming policy_type
curl -s -b cookies.txt "http://localhost:8000/api/policies/?customer=1" | jq '.count'
```

**Expect**: `2` after adding Health. A different type succeeds (FR-003); a
duplicate live type is refused, which is what keeps the loader's match key
sound.

---

## 9. Archived customer keeps its policies (SC-008) — the cross-entity guarantee

This is the scenario that distinguishes this feature from a stock CRUD module.

```bash
# Archive a customer who holds a live policy
curl -s -b cookies.txt -X DELETE http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n'

# The customer is gone...
curl -s -b cookies.txt http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n'

# ...but their policy is not
curl -s -b cookies.txt "http://localhost:8000/api/policies/?customer=1" \
  | jq '{count, customer: .results[0].customer.client_id}'
```

**Expect**: `204`, then `404` for the customer, then the policy **still
returned** with its customer link intact (FR-008, FR-022).

Creating *new* coverage for that archived customer is refused:

```bash
# POST a policy with customer=1 -> 400 naming customer (FR-014)
```

**Expect**: the message distinguishes "archived" from "does not exist".

---

## 10. Policy archival releases the coverage slot (SC-012)

```bash
# Archive customer 2's Auto policy
curl -s -b cookies.txt -X DELETE http://localhost:8000/api/policies/<id>/ -o /dev/null -w '%{http_code}\n'
# Then create a new Auto policy for customer 2 -> 201
```

**Expect**: `204`, then `201`. Archival must **not** permanently consume a
coverage slot — the opposite of Customer, where an archived `client_id` stays
reserved forever. Same mechanism, opposite requirement.

Confirm the row survives and the load does not resurrect it:

```bash
docker compose exec web python manage.py shell -c "
from apps.policies.models import Policy
print('live:', Policy.objects.count(), 'total:', Policy.all_objects.count())"
```

**Expect**: `all_objects` exceeds `objects` by the number archived.

---

## 11. Role enforcement, all 9 roles + anonymous (SC-005)

```bash
docker compose exec web pytest apps/policies/tests/test_permissions.py -v
```

**Expect**: every role × every operation matches FR-026, 100%.

Spot-check the two differences from the Customer module:

```bash
# Product Manager MAY read policies (but may not read customers)
curl -s -b pm.txt http://localhost:8000/api/policies/ -o /dev/null -w '%{http_code}\n'   # 200
curl -s -b pm.txt http://localhost:8000/api/customers/ -o /dev/null -w '%{http_code}\n'  # 403

# Customer Service may read but NOT write policies (reverse of the customer module)
curl -s -b cs.txt http://localhost:8000/api/policies/ -o /dev/null -w '%{http_code}\n'   # 200
curl -s -b cs.txt -X DELETE http://localhost:8000/api/policies/1/ -o /dev/null -w '%{http_code}\n'  # 404
```

Superuser status must not bypass (FR-027): a superuser whose role is
`executive_leadership` still gets 403 on the list.

---

## 12. Audit trail (SC-006)

Create, update, then delete a policy, and read its history as a Compliance
Officer:

```bash
curl -s -b compliance.txt \
  "http://localhost:8000/api/audit/history/policies.Policy/<id>/" \
  | jq '.results[] | {action, outcome, before, after}'
```

**Expect**: `policy.created`, `policy.updated`, `policy.deleted`.

- The **update** entry lists **only** changed fields (FR-029) — patching
  `premium_usd` must not list `policy_type`.
- The **delete** entry's `before` holds full values at removal (FR-030).
- A **refused** operation appears with `outcome: "refused"` (FR-031).

**The refusal-vs-miss distinction** (FR-032), which keeps the compliance record
usable:

```bash
# As Customer Service (may read, may not write): DELETE -> refusal entry
# As Underwriter (may write): GET a nonexistent id -> NO entry
curl -s -b uw.txt http://localhost:8000/api/policies/999999/ -o /dev/null -w '%{http_code}\n'
```

**Expect**: `404` with **no** refusal entry written — a permitted user's miss
is not a permission refusal.

Atomicity (FR-033) and append-only (FR-034) are covered by test rather than by
hand.

---

## 13. Placeholder is gone (SC-011)

```bash
curl -s -b cookies.txt http://localhost:8000/api/policies/placeholder/ \
  -o /dev/null -w '%{http_code}\n'
```

**Expect**: `404`. The view, route, and Phase 1 test module are deleted.

---

## 14. Loader failure modes (FR-046)

```bash
docker compose exec web python manage.py loaddataset /nonexistent.csv    # exit 1
docker compose exec web python manage.py loaddataset data/no_policy_cols.csv  # exit 1
```

**Expect**: clear message, exit 1, and **no records of either type** created.

The second case is a behavior change from Phase 2a: a file missing policy
columns now fails before writing any customer, where previously it would have
loaded customers successfully.

---

## Full regression

```bash
docker compose exec web pytest
```

**Expect**: every Phase 1 and Phase 2a test still passing alongside the new
policy tests. The refusal-handler refactor is the highest-risk change in this
feature; a failure in `apps/customers/` or `apps/core/` is a regression, not an
intended change.
