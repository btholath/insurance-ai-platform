# Quickstart: Validating Automatic Risk Recompute

**Feature**: 006-automatic-risk-recompute | **Date**: 2026-08-21

A runnable end-to-end validation, in the style established by
[005's quickstart](../005-risk-scoring-engine/quickstart.md) — each step maps
to a spec success criterion and is something you execute and read the result
of, not take on trust. Carries forward that quickstart's corrected auth
pattern (session cookies + CSRF, not bearer tokens — see that doc's Auth
section) and its `manage.py shell -c` vs. bare `python -c` distinction.

**Note on ports**: web is host **8001**; this feature adds no new published
port (the Celery worker has no HTTP surface).

**Note on the web container**: as in 005's quickstart, `docker compose
restart web` after code changes if a route 404s unexpectedly — Gunicorn's
sync worker does not reload on file changes. The new `celery-worker`
container has the identical issue for task code: `docker compose restart
celery-worker` after a change to `apps/risk/tasks.py` or any signal
receiver, for the same reason.

## Prerequisites

```bash
docker compose up -d          # brings up db, redis, web, and the new celery-worker
docker compose ps             # all four healthy
docker compose exec web python manage.py migrate   # no new migrations expected — confirms none were missed
```

Dataset loaded and every customer already scored (this feature only
recomputes customers who already have an assessment — FR-005):

```bash
docker compose exec web python manage.py loaddataset /app/data/Insurance_Dataset.csv
docker compose exec web python manage.py computerisk
```

Confirm the worker is actually consuming tasks, not just running:

```bash
docker compose logs celery-worker --tail 20
```

**Expect**: a "ready" / "celery@... ready" line with no import errors. If
`apps.risk.tasks` fails to import (e.g. a typo), this is where it surfaces —
the worker process would otherwise sit healthy-looking but silently unable
to run anything.

---

## Step 1 — Tests pass (Principle V)

```bash
docker compose exec web pytest apps/risk/ -v
docker compose exec web pytest --cov=apps --cov-report=term-missing
```

**Expect**: all risk tests green, including the new `test_tasks.py` —
specifically confirm the retry/backoff tests and the exhausted-retry test
are present and passing, not skipped (per the user description's explicit
requirement that these be tested, not just the happy path). Full suite
still green; the number of passing tests should only grow from Phase 3a's
final count.

---

## Step 2 — A policy change recomputes automatically (SC-001, User Story 1)

```bash
docker compose exec web python manage.py shell -c "
from apps.risk.models import RiskAssessment
a = RiskAssessment.objects.order_by('customer_id').first()
print('customer:', a.customer_id, 'score before:', a.score, 'computed_at before:', a.computed_at)
"
```

Note the customer id and `computed_at`, then change a live policy for that
customer through the real API (see 005's quickstart Auth section for the
login/cookie/CSRF flow — reuse an Underwriter jar):

```bash
UNDERWRITER_CSRF=$(grep csrftoken /tmp/underwriter_cookies.txt | awk '{print $NF}')
POLICY_ID=$(docker compose exec web python manage.py shell -c "
from apps.policies.models import Policy
print(Policy.objects.filter(customer_id=<CUSTOMER_ID>).first().id)
")

curl -s -X PATCH -b /tmp/underwriter_cookies.txt \
  -H "Content-Type: application/json" -H "X-CSRFToken: $UNDERWRITER_CSRF" \
  -d '{"premium_usd": "1234.56"}' \
  http://localhost:8001/api/policies/<POLICY_ID>/
```

Wait a few seconds (no polling loop needed for a real check — this is the
"short, bounded time" SC-001 claims), then:

```bash
docker compose exec web python manage.py shell -c "
from apps.risk.models import RiskAssessment
a = RiskAssessment.objects.get(customer_id=<CUSTOMER_ID>)
print('score after:', a.score, 'computed_at after:', a.computed_at, 'computed_by:', a.computed_by)
"
```

**Expect**: `computed_at` has advanced past the PATCH's timestamp with no
manual recompute call in between, and `computed_by` is `None` (nothing
attributes an automatic recompute to a human). Cross-check via the API,
confirming `is_stale` is now `false`:

```bash
curl -s -b /tmp/risk_mgr_cookies.txt \
  http://localhost:8001/api/risk/assessments/by-customer/<CUSTOMER_ID>/ \
  | python -m json.tool | grep -E "is_stale|computed_at"
```

---

## Step 3 — A never-scored customer is NOT auto-scored (FR-005, SC-003)

```bash
docker compose exec web python manage.py shell -c "
from apps.customers.models import Customer
c = Customer.objects.create_with_reference(
    name='Not Yet Scored', email='nys@example.com', phone='555', age=40,
    gender='Other', location='Nowhere', lead_source='Web')
print('created:', c.client_id, c.id)
"
```

Create a policy for this customer (this saves a `Policy` row and therefore
fires the trigger):

```bash
docker compose exec web python manage.py shell -c "
from apps.customers.models import Customer
from apps.policies.models import Policy
from decimal import Decimal
from datetime import date, timedelta
c = Customer.objects.get(client_id='<CLIENT_ID>')
Policy.objects.create(
    customer=c, policy_type='Auto',
    start_date=date.today() - timedelta(days=1),
    end_date=date.today() + timedelta(days=365),
    premium_usd=Decimal('500.00'))
"
```

Wait a few seconds, then confirm no assessment was created:

```bash
docker compose exec web python manage.py shell -c "
from apps.risk.models import RiskAssessment
from apps.customers.models import Customer
c = Customer.objects.get(client_id='<CLIENT_ID>')
print('assessment exists:', RiskAssessment.objects.filter(customer=c).exists())
"
```

**Expect**: `assessment exists: False`. The Policy save enqueued a task, the
task ran (check `docker compose logs celery-worker` for the no-op if you
want to see it), and it correctly did nothing, because this customer has
never been scored — that stays `computerisk`'s job.

Delete this step's scratch customer and policy (the customer has no
`RiskAssessment` to clean up, by this step's own assertion above) —
skipping this leaves scratch rows accumulating in the persistent dev DB
across quickstart runs, silently inflating counts checked in later steps
(e.g. step 5's before/after row count):

```bash
docker compose exec web python manage.py shell -c "
from apps.customers.models import Customer
from apps.policies.models import Policy
c = Customer.objects.get(client_id='<CLIENT_ID>')
Policy.objects.filter(customer=c).delete()
c.delete()
"
```

---

## Step 4 — A permanent failure produces a discoverable record (FR-010, SC-005, User Story 3)

This step deliberately breaks something to prove the failure path, then
restores it — do this only against a disposable state, or run it via
`pytest` instead (the equivalent assertion already lives in
`apps/risk/tests/test_tasks.py`).

```bash
docker compose exec web python manage.py shell -c "
from unittest.mock import patch
from apps.risk.tasks import recompute_customer_risk
from apps.risk.models import RiskAssessment

customer_id = RiskAssessment.objects.first().customer_id

with patch('apps.risk.tasks.engine.persist', side_effect=RuntimeError('forced failure')):
    result = recompute_customer_risk.apply(args=[customer_id], throw=False)
    print('task state:', result.state)
"
```

Then confirm the audit trail recorded it:

```sql
SELECT action, target_type, outcome, context
FROM audit_auditlog
WHERE action = 'risk.recompute_failed'
ORDER BY id DESC LIMIT 1;
```

**Expect**: one row, `outcome = refused`, `context` naming the customer id
and the forced exception, and — critically — the customer's
`RiskAssessment` is unchanged (a failed recompute never partially writes):

```sql
SELECT score, computed_at FROM risk_riskassessment WHERE customer_id = <CUSTOMER_ID>;
```

Then confirm the earlier "give up" did not permanently disable this
customer (FR-011) — patch removed, retrigger, and it recomputes normally:

```bash
docker compose exec web python manage.py shell -c "
from apps.risk.tasks import recompute_customer_risk
recompute_customer_risk.apply(args=[<CUSTOMER_ID>])
"
```

---

## Step 5 — `loaddataset` re-run stays correct under redundant triggering (FR-016, FR-017, SC-006, User Story 4)

```bash
docker compose exec web python manage.py shell -c "
import json, hashlib
from apps.risk.models import RiskAssessment
rows = list(RiskAssessment.objects.order_by('customer_id').values_list('customer_id', 'score', 'tier'))
print(hashlib.sha256(json.dumps(rows).encode()).hexdigest())
print('count:', len(rows))
" > /tmp/risk_before_reload.txt

docker compose exec web python manage.py loaddataset /app/data/Insurance_Dataset.csv
```

Wait for the resulting flood of enqueued tasks to drain — watch the worker
log for volume, then quiesce:

```bash
docker compose logs celery-worker --tail 5 -f   # Ctrl-C once it goes quiet
```

```bash
docker compose exec web python manage.py shell -c "
import json, hashlib
from apps.risk.models import RiskAssessment
rows = list(RiskAssessment.objects.order_by('customer_id').values_list('customer_id', 'score', 'tier'))
print(hashlib.sha256(json.dumps(rows).encode()).hexdigest())
print('count:', len(rows))
" > /tmp/risk_after_reload.txt

diff /tmp/risk_before_reload.txt /tmp/risk_after_reload.txt && echo "IDENTICAL — SC-006 holds"
```

**Expect**: identical hash and identical count (still 3,000, or whatever
the pre-load count was) — the reload's ~3,000 redundant, same-answer
recompute tasks left the book exactly as it was, despite each one running
for real.

---

## Step 6 — Manual recompute is unaffected (FR-012, SC-007, User Story 5)

```bash
RISK_MGR_CSRF=$(grep csrftoken /tmp/risk_mgr_cookies.txt | awk '{print $NF}')
curl -s -X POST -b /tmp/risk_mgr_cookies.txt \
  -H "Content-Type: application/json" -H "X-CSRFToken: $RISK_MGR_CSRF" \
  -d '{"customer": <CUSTOMER_ID>}' \
  http://localhost:8001/api/risk/assessments/recompute/ | python -m json.tool
```

**Expect**: identical response shape to Phase 3a's quickstart step 7 — this
route's behavior, role enforcement, and audit entry are byte-for-byte
unchanged by this feature's existence.

---

## Success criteria coverage

| Step | Criteria verified |
|---|---|
| 1 | Principle V (tests exist, including retry/backoff and loaddataset-redundancy) |
| 2 | SC-001 |
| 3 | SC-003, FR-005 |
| 4 | SC-005, FR-010, FR-011 |
| 5 | SC-006, FR-016, FR-017 |
| 6 | SC-007, FR-012 |
