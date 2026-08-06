# Quickstart: Validating Customer Management

**Feature**: `002-customer-management`

Runnable scenarios proving the feature works end to end. Each maps to success
criteria in [spec.md](./spec.md). Field shapes are in
[data-model.md](./data-model.md); request/response detail is in
[contracts/](./contracts/).

---

## Prerequisites

```bash
docker compose up -d          # Postgres + Redis
python manage.py migrate
pytest                        # baseline: all green before starting
```

The source dataset must exist at a path you supply. It is gitignored
(FR-041) — if `data/Insurance_Dataset.csv` is absent, obtain it separately.

---

## 1. Test suite and coverage (SC-009)

```bash
pytest apps/customers/ -v
pytest --cov=apps.customers --cov-report=term-missing
```

**Expect**: all green; `apps/customers` coverage **≥ 95%**, matching the level
Phase 1 established.

Per Principle V, the customer tests are written **before** the implementation
they cover. The commit history should show tests failing first.

---

## 2. Load the dataset (SC-001)

```bash
python manage.py loadcustomers data/Insurance_Dataset.csv
```

**Expect**: `Created: 3000  Updated: 0  Refused: 0`

```bash
python manage.py shell -c \
  "from apps.customers.models import Customer; print(Customer.objects.count())"
```

**Expect**: `3000`

---

## 3. Idempotency (SC-002)

Re-run the identical command:

```bash
python manage.py loadcustomers data/Insurance_Dataset.csv
```

**Expect**: `Created: 0  Updated: 3000  Refused: 0`, count still `3000`.

Confirm zero duplicate references directly in the database:

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT client_id, COUNT(*) FROM customers_customer
   GROUP BY client_id HAVING COUNT(*) > 1;"
```

**Expect**: `(0 rows)`

---

## 4. Shared email addresses (SC-008)

The source contains three email addresses held by two customers each — email
is deliberately not unique (FR-004).

```bash
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT email, COUNT(*) FROM customers_customer
   GROUP BY email HAVING COUNT(*) > 1 ORDER BY email;"
```

**Expect**: exactly 3 rows, each with count 2 — 6 customers across 3 addresses.

Then search by one of them and confirm both holders return:

```bash
curl -s -b cookies.txt \
  "http://localhost:8000/api/customers/?search=<one-of-those-emails>" | jq '.count'
```

**Expect**: `2`

---

## 5. Retrieval and search performance (SC-003, SC-004)

Sign in as Customer Service first:

```bash
curl -s -c cookies.txt -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"cs@example.com","password":"<password>"}'
```

Single record — **expect < 1 second** (SC-003):

```bash
time curl -s -b cookies.txt http://localhost:8000/api/customers/1/ | jq '.client_id'
```

Search first page — **expect < 2 seconds** (SC-004):

```bash
time curl -s -b cookies.txt \
  "http://localhost:8000/api/customers/?search=patrick" | jq '.count'
```

Also confirm pagination is bounded and ordering stable:

```bash
curl -s -b cookies.txt "http://localhost:8000/api/customers/" \
  | jq '{count, returned: (.results | length)}'
```

**Expect**: `count: 3000`, `returned: 50`. Requesting `?page=2` twice returns
identical ids.

---

## 6. Filters (FR-019)

```bash
for f in "lead_source=Agent" "gender=Female" "fraud_risk_flag=High"; do
  echo -n "$f -> "
  curl -s -b cookies.txt "http://localhost:8000/api/customers/?$f" | jq '.count'
done
```

**Expect**: each returns a nonzero count below 3000; combining two filters
narrows further.

---

## 7. Validation boundaries (SC-007)

Every rule refuses an invalid value **and** accepts a valid boundary value.

```bash
# age 17 -> 400 naming "age"
curl -s -b cookies.txt -X POST http://localhost:8000/api/customers/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"T","email":"t@e.com","phone":"1","age":17,"gender":"Other","location":"X","lead_source":"Web"}' \
  | jq 'keys'

# age 18 -> 201  (lower boundary accepted)
# age 120 -> 201 (upper boundary accepted)
# age 121 -> 400
```

**Expect**: `["age"]` on refusals; 201 at 18 and 120.

Repeat for: empty `name` (FR-009), malformed `email` (FR-010), unrecognized
`gender` / `lead_source` / `fraud_risk_flag` (FR-012), and `risk_score` /
`cross_sell_score` outside 0–1 (FR-013). Each refusal names exactly that field
and stores nothing.

**Absent ≠ zero** (FR-006) — a customer created without scores:

```bash
curl -s -b cookies.txt http://localhost:8000/api/customers/<new-id>/ \
  | jq '.risk_score, .cross_sell_score, .fraud_risk_flag'
```

**Expect**: `null`, `null`, `null` — not `"0.00"`.

---

## 8. Duplicate email accepted, duplicate reference refused

```bash
# Two customers, same email -> both 201 (FR-004)
# Second customer with an existing client_id -> 400 naming client_id (FR-003)
```

**Expect**: shared email succeeds; duplicate `client_id` is refused with a
`client_id` error.

---

## 9. Soft delete and reference reservation (SC-011)

```bash
curl -s -b cookies.txt -X DELETE http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n'
curl -s -b cookies.txt http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n'
curl -s -b cookies.txt "http://localhost:8000/api/customers/?search=CL-00001" | jq '.count'
```

**Expect**: `204`, then `404`, then `0` — gone from detail and search.

The row itself survives:

```bash
python manage.py shell -c \
  "from apps.customers.models import Customer; \
   print(Customer.objects.count(), Customer.all_objects.count())"
```

**Expect**: `2999 3000` — the archived row is still there.

**The critical reconciliation check** — re-run the load and confirm the
archived reference matches rather than duplicating (FR-021):

```bash
python manage.py loadcustomers data/Insurance_Dataset.csv
python manage.py shell -c \
  "from apps.customers.models import Customer; \
   print(Customer.all_objects.filter(client_id='CL-00001').count())"
```

**Expect**: `1`, and total `all_objects` count still `3000`. This is the
scenario that fails if the loader looks up through `objects` instead of
`all_objects` — it would raise `IntegrityError` on a reference it cannot see.

---

## 10. Role enforcement, all 9 roles + anonymous (SC-005)

```bash
pytest apps/customers/tests/test_permissions.py -v
```

**Expect**: every role × every operation matches the FR-024 matrix, 100%.

Note the asymmetry, which is intended Phase 1 `HasRole` behavior:
collection-route refusals are **403**; detail-route refusals are **404**, so a
refusal is indistinguishable from a nonexistent record (FR-022).

Spot-check by hand — Product Manager may not view:

```bash
# sign in as product_manager, then:
curl -s -b pm.txt http://localhost:8000/api/customers/ -o /dev/null -w '%{http_code}\n'   # 403
curl -s -b pm.txt http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n' # 404
```

Underwriter may view but not write:

```bash
curl -s -b uw.txt http://localhost:8000/api/customers/ -o /dev/null -w '%{http_code}\n'   # 200
curl -s -b uw.txt -X DELETE http://localhost:8000/api/customers/1/ -o /dev/null -w '%{http_code}\n' # 404
```

Superuser status must **not** bypass the role check (FR-026): a superuser
whose role is `product_manager` still gets 403 on the list.

---

## 11. Audit trail (SC-006)

Create, update, then delete a customer, and read its history as a Compliance
Officer:

```bash
curl -s -b compliance.txt \
  "http://localhost:8000/api/audit/history/customers.Customer/<id>/" \
  | jq '.results[] | {action, outcome, before, after}'
```

**Expect**: three entries — `customer.created`, `customer.updated`,
`customer.deleted`.

- The **update** entry's `before`/`after` contain **only** the fields that
  changed (FR-028). Patching just `phone` must not list `name` or `email`.
- The **delete** entry's `before` holds the full values as at removal (FR-029).
- A **refused** operation appears with `outcome: "refused"` and the customer
  unchanged (FR-030).

**Atomicity** (FR-031) is covered by test rather than by hand — a forced audit
failure must roll the customer write back, leaving neither.

**Append-only** (FR-032) is already guaranteed by the Phase 1 database trigger;
`apps/audit/tests/test_immutability_db.py` still passes.

---

## 12. Placeholder is gone (SC-010)

```bash
curl -s -b cookies.txt http://localhost:8000/api/customers/placeholder/ \
  -o /dev/null -w '%{http_code}\n'
```

**Expect**: `404`. The view, its route, and its Phase 1 test module are all
deleted (FR-043).

---

## 13. Loader failure modes (FR-040)

```bash
python manage.py loadcustomers /nonexistent.csv          # File not found, exit 1
python manage.py loadcustomers data/missing_columns.csv  # Missing required columns, exit 1
```

**Expect**: clear message, exit 1, and `Customer.all_objects.count()` unchanged
in both cases — the column check runs before any row is written.

Extra columns cause no error (FR-037): the real dataset carries nine unused
policy/claim columns and loads cleanly, which scenario 2 already proves.

---

## Full regression

```bash
pytest
```

**Expect**: every Phase 1 test still passing alongside the new customer tests.
This feature adds no new permission or audit mechanism, so any Phase 1 failure
indicates a regression rather than an intended change.
