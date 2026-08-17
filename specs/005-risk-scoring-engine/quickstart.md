# Quickstart: Validating the Risk Scoring Engine

**Feature**: 005-risk-scoring-engine | **Date**: 2026-08-17

A runnable end-to-end validation. Each step maps to a spec success criterion, and
each is something you can execute and read the result of rather than take on
trust. Written for the verification style this project uses: the assertions are
re-checkable with `psql` and `curl` independently of the test suite.

**Note on ports**: the web service is mapped to host **8001** (`splunkd` occupies
8000 on this machine). Adjust if your compose file differs.

## Prerequisites

```bash
docker compose ps          # db, redis, web all healthy
docker compose exec web python manage.py migrate
```

Dataset loaded (3,000 customers / 3,000 policies / 2,246 claims). If not:

```bash
docker compose exec web python manage.py loaddataset /data/Insurance_Dataset.csv
```

---

## Step 1 — Tests pass, coverage holds (Principle V, SC-015)

```bash
docker compose exec web pytest apps/risk/ -v
docker compose exec web pytest --cov=apps --cov-report=term-missing
```

**Expect**: all risk tests green, full suite still green (842 tests passing
before this feature — the number should only grow), coverage on
`apps/risk/rules.py` and `apps/risk/engine.py` at **100%**. These two files are
the business-rule core Principle V names explicitly; an uncovered branch there is
a gate failure, not a nit.

Specifically confirm `test_rules.py` covers **both sides of every boundary** —
age 24/25 and 34/35 and 64/65, ratio 0.99/1.0 and 2.99/3.0 and 4.99/5.0, and
score 19/20, 39/40, 59/60 for tiers (FR-007).

---

## Step 2 — The rule set is one source of truth (FR-003, FR-004)

```bash
docker compose exec web python -c "
from apps.risk import rules
print('version:', rules.RULE_SET_VERSION)
print('factors:', [f for f in rules.FACTORS])
print('max possible:', rules.max_score())
"
```

**Expect**: version `1.0.0`, five factors, max score `100`. The same structure
drives both computation and the explanation's band labels — there is no second
table to drift.

---

## Step 3 — Roles are enforced on every route (Principle III, SC-009, SC-010)

Get tokens for a Risk Manager, an Underwriter, and a Customer Service user, then:

```bash
# Risk Manager reads — 200
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Token $RISK_MGR" \
  http://localhost:8001/api/risk/assessments/1/

# Customer Service reads — 404 (not 403: non-disclosure on a detail route)
curl -s -H "Authorization: Token $CUST_SVC" \
  http://localhost:8001/api/risk/assessments/1/

# ...and for an id that does not exist — byte-identical body (SC-010)
curl -s -H "Authorization: Token $CUST_SVC" \
  http://localhost:8001/api/risk/assessments/99999999/

# Underwriter may read but NOT recompute — 403, and no score change
curl -s -X POST -H "Authorization: Token $UNDERWRITER" \
  -H "Content-Type: application/json" -d '{"customer": 1}' \
  http://localhost:8001/api/risk/assessments/recompute/

# Unauthenticated — 401
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/risk/assessments/
```

**Expect**: the two Customer Service responses are **identical**, body included —
`{"detail":"Not found."}` both times. Diff them to be sure:

```bash
diff <(curl -s -H "Authorization: Token $CUST_SVC" http://localhost:8001/api/risk/assessments/1/) \
     <(curl -s -H "Authorization: Token $CUST_SVC" http://localhost:8001/api/risk/assessments/99999999/) \
  && echo "IDENTICAL — SC-010 holds"
```

---

## Step 4 — The registry absorbed risk as configuration (FR-041, the fourth-consumer test)

```bash
git diff --stat apps/core/
```

**Expect**: `audit_routes.py` changed (one `register(...)` call) and
`tests/test_audit_routes.py` changed (swapped example + new assertions).
**`exception_handlers.py` MUST be untouched.** If it appears in that diff, FR-041
has failed and the Phase 2b registry bet did not pay off — that is a finding to
report, not a detail to absorb.

Confirm the entry resolves to *risk*, not *customers*:

```bash
docker compose exec web python -c "
from apps.core import audit_routes
for p in ['/api/risk/assessments/1/', '/api/customers/1/']:
    m = audit_routes.match(p)
    print(p, '->', m.target_type, m.action_prefix, len(m.view_roles), 'view roles')
"
```

**Expect**: `/api/risk/...` → `risk.RiskAssessment`, `risk`, **5** view roles;
`/api/customers/1/` → `customers.Customer`, `customer`, **7**. Different modules,
different role sets — that is the registry doing the job it exists for.

Then confirm the refusal was actually recorded under the right module:

```sql
SELECT action, target_type, actor_role, outcome
FROM audit_auditlog WHERE action LIKE 'risk%' ORDER BY id DESC LIMIT 5;
```

**Expect**: `risk.viewed | risk.RiskAssessment | customer_service | refused` —
**not** `customer.viewed`. This is the concrete payoff of the top-level prefix
decision (§1 of research.md).

---

## Step 5 — Score the whole book (FR-030, FR-031, SC-006)

```bash
time docker compose exec web python manage.py computerisk
```

**Expect**: `scored: 3000`, `skipped: 0`, `failed: 0`, a tier distribution near
33/32/17/18%, and completion **under 60s**. Counts must sum to 3,000 (SC-006).

Verify independently:

```sql
SELECT tier, count(*), round(100.0*count(*)/sum(count(*)) OVER (),1) AS pct
FROM risk_riskassessment GROUP BY 1 ORDER BY min(score);
```

**Expect**: four tiers, **each at or above 5%** (SC-005). If any tier is empty or
below the floor, the rules are not discriminating and SC-005 has failed.

---

## Step 6 — The explanation actually explains (Principle IV, SC-001, SC-002)

The central check of this feature. Every assessment's factors must sum to its
score, across the whole population:

```sql
SELECT count(*) AS mismatched
FROM risk_riskassessment a
JOIN (SELECT assessment_id, sum(points) AS total
      FROM risk_riskfactor GROUP BY 1) f ON f.assessment_id = a.id
WHERE f.total <> a.score;
```

**Expect: `0`.** Any non-zero result is a Principle IV violation — a score
carrying an explanation that does not account for it.

Every assessment carries all five factors (SC-002):

```sql
SELECT factor_count, count(*) FROM (
  SELECT assessment_id, count(*) AS factor_count FROM risk_riskfactor GROUP BY 1
) t GROUP BY 1;
```

**Expect**: a single row — `5 | 3000`. Any assessment with fewer means a factor
was silently omitted rather than reported as zero or non-evaluable.

Then read one end to end:

```bash
curl -s -H "Authorization: Token $RISK_MGR" \
  http://localhost:8001/api/risk/assessments/by-customer/1/ | python -m json.tool
```

**Expect**: score, tier, `rule_set_version`, `computed_at`, and five factor
entries each naming the factor, the observed value, the band, and the points —
readable without consulting the code (FR-025). Add the points yourself; they
must equal the score.

**Idempotency** (FR-033, SC-004) — run it twice for real rather than asserting it:

```bash
docker compose exec web python -c "
import json,hashlib
from apps.risk.models import RiskAssessment
rows=list(RiskAssessment.objects.order_by('customer_id').values_list('customer_id','score','tier'))
print(hashlib.sha256(json.dumps(rows).encode()).hexdigest())
" > /tmp/risk_before.txt

docker compose exec web python manage.py computerisk
# ...same command again, then re-hash
diff /tmp/risk_before.txt /tmp/risk_after.txt && echo "IDENTICAL — SC-004 holds"
```

Also confirm no duplicates accumulated:

```sql
SELECT count(*) FROM risk_riskassessment;              -- still 3000
SELECT count(*) FROM risk_riskfactor;                  -- still 15000
```

---

## Step 7 — Nothing recomputes automatically (FR-036, SC-011)

The boundary between 3a and 3b, verified rather than assumed.

```bash
# note the current score
docker compose exec web python -c "
from apps.risk.models import RiskAssessment
a=RiskAssessment.objects.get(customer_id=1); print(a.score, a.computed_at)"

# change data that feeds the score — via the API, as a real user would
curl -s -X PATCH -H "Authorization: Token $UNDERWRITER" \
  -H "Content-Type: application/json" -d '{"premium_usd": "100.00"}' \
  http://localhost:8001/api/policies/1/

# score MUST be unchanged
docker compose exec web python -c "
from apps.risk.models import RiskAssessment
a=RiskAssessment.objects.get(customer_id=1); print(a.score, a.computed_at)"
```

**Expect**: identical score and identical `computed_at`. A changed score here
means something is recomputing automatically, which FR-036 forbids and Phase 3b
owns.

**But it must now report as stale** (FR-039, SC-012):

```bash
curl -s -H "Authorization: Token $RISK_MGR" \
  http://localhost:8001/api/risk/assessments/by-customer/1/ | python -m json.tool | grep -E "is_stale|stale_reason"
```

**Expect**: `"is_stale": true` with a reason — and the **stored score and factors
still returned as computed** (FR-040), not suppressed and not silently
recalculated.

Then recompute explicitly and watch it clear:

```bash
curl -s -X POST -H "Authorization: Token $RISK_MGR" \
  -H "Content-Type: application/json" -d '{"customer": 1}' \
  http://localhost:8001/api/risk/assessments/recompute/ | python -m json.tool
```

**Expect**: new score reflecting the changed premium, `is_stale` back to `false`.

---

## Step 8 — Every computation is audited (Principle II, SC-008)

```sql
SELECT action, count(*) FROM audit_auditlog
WHERE action LIKE 'risk%' GROUP BY 1 ORDER BY 2 DESC;
```

**Expect**: `risk.computed` at 3,000+ and `risk.batch_computed` at one per batch
run (FR-050).

Before/after and rule version are recorded (FR-048, FR-054):

```sql
SELECT actor_identifier, actor_role, action, before, after, context
FROM audit_auditlog WHERE action = 'risk.computed'
ORDER BY id DESC LIMIT 3;
```

**Expect**: `before` carrying the previous score (null on first computation),
`after` carrying the new score, tier, and `rule_set_version`. For the API-triggered
recompute from step 7, `actor_identifier` is the Risk Manager's email; for command
runs it is empty, which is honest — no user triggered those.

**An unchanged recompute is still recorded** (FR-049): recompute the same
customer twice with no data change and confirm the entry count rises by two.

Append-only still holds:

```bash
docker compose exec web python -c "
from apps.audit.models import AuditLog
try:
    AuditLog.objects.filter(action='risk.computed').update(action='tampered')
except NotImplementedError as e:
    print('append-only holds:', e)"
```

---

## Step 9 — The legacy field no longer carries source data (FR-055 – FR-057, SC-013)

```sql
SELECT count(*) FILTER (WHERE risk_score IS NULL)     AS unscored,
       count(*) FILTER (WHERE risk_score IS NOT NULL) AS scored,
       min(risk_score), max(risk_score)
FROM customers_customer;
```

**Expect**: `scored` = 3,000 with values that are **exactly** the assessment
score ÷ 100. Cross-check the mirror against the record of truth:

```sql
SELECT count(*) AS mismatched
FROM customers_customer c
JOIN risk_riskassessment a ON a.customer_id = c.id
WHERE c.risk_score <> round(a.score / 100.0, 2);
```

**Expect: `0`.**

Confirm the loader can no longer reintroduce source scores (FR-057) — re-run the
load and check the mirror is untouched:

```bash
docker compose exec web python manage.py loaddataset /data/Insurance_Dataset.csv
```

Then re-run the mismatch query above. **Expect `0` still** — the load must not
overwrite computed scores with the CSV's `Risk_Score` column.

---

## Step 10 — A customer who cannot be scored (FR-018, SC-007)

Not present in the seeded data (every customer has a policy), so construct it:

```bash
docker compose exec web python manage.py shell -c "
from apps.customers.models import Customer
c = Customer.objects.create_with_reference(
    name='No Policy', email='np@example.com', phone='555', age=40,
    gender='Other', location='Nowhere', lead_source='Web')
print(c.client_id)"

docker compose exec web python manage.py computerisk --customer <CLIENT_ID>
```

> This writes to the persistent dev database. Ask before running step 10 against
> dev, or run it against the test database instead — the equivalent assertion is
> already covered in `test_computerisk.py`.

**Expect**: `scored: 0`, `skipped: 1`, with the reason stated — **no assessment
row created**, and no score of 0. Then:

```bash
curl -s -H "Authorization: Token $RISK_MGR" \
  http://localhost:8001/api/risk/assessments/by-customer/<ID>/
```

**Expect**: 404 with `"This customer has not been assessed."` — distinguishable
from a genuine low score (FR-029).

---

## Success criteria coverage

| Step | Criteria verified |
|---|---|
| 1 | SC-015 |
| 2 | FR-003, FR-004 |
| 3 | SC-009, SC-010 |
| 4 | FR-041 (fourth-consumer test) |
| 5 | SC-005, SC-006 |
| 6 | SC-001, SC-002, SC-003, SC-004, SC-014 |
| 7 | SC-011, SC-012 |
| 8 | SC-008 |
| 9 | SC-013 |
| 10 | SC-007 |
