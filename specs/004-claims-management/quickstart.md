# Quickstart: Validating Claims Management

**Feature**: `004-claims-management`

Runnable scenarios proving the feature works end to end. Each maps to success
criteria in [spec.md](./spec.md). Field shapes are in
[data-model.md](./data-model.md); request/response detail is in
[contracts/](./contracts/).

**Database note**: the scenarios in §§4–7 write to the dev database. **Confirm
before running them**, and prefer the test suite where it proves the same
property — §§1–3 and §8 do, and cost nothing. The anomaly lifecycle in §6 is
the one place a real load is genuinely more convincing than a fixture, because
its whole point is behavior across multiple runs.

---

## Prerequisites

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web pytest        # baseline green before starting
```

Tests run inside the `web` container. **The image has no source volume mount**,
so `docker compose up --build -d` is required after host-side edits — otherwise
the container runs stale code and a green suite proves nothing about what you
just wrote.

---

## 1. Test suite and coverage (SC-009)

```bash
docker compose exec web pytest apps/claims/ -v
docker compose exec web pytest --cov=apps.claims --cov-report=term-missing
```

**Expect**: all green; `apps/claims` coverage **≥ 95%**.

Per Principle V, tests precede the implementation they cover.

### The regression check that matters most (SC-008)

```bash
git diff --stat apps/core/exception_handlers.py
```

**Expect: empty output.** This is FR-030's actual test. Phase 2b refactored the
refusal handler into a registry on the explicit prediction that Claims would be
its third consumer and would need **no handler change**. If this diff is
non-empty, the prediction failed and the registry design did not pay off — that
is a finding worth recording, not a line to quietly commit.

```bash
docker compose exec web pytest apps/customers/tests/test_audit.py apps/policies/tests/test_audit.py -v
```

**Expect**: all pass, **unmodified**. Adding a third registry consumer must not
change how the first two behave.

---

## 2. The `No Claim` boundary (SC-002, FR-004, FR-012)

The single most consequential behavior in this feature. Verified without
touching the dev database:

```bash
docker compose exec web pytest apps/claims/tests/test_serializers.py -k no_claim -v
docker compose exec web pytest apps/claims/tests/test_models.py -k status -v
```

**Expect**: `No Claim` is rejected as a claim status with an error naming
`claim_status`, and the message explains that the absence of a claim is
represented by the absence of a record — not merely "not a valid choice".

```bash
docker compose exec web python manage.py shell -c "
from apps.claims.models import ClaimStatus
print([c[0] for c in ClaimStatus.choices])
"
```

**Expect**: `['Approved', 'Denied', 'Filed']` — three values, not four.
`No Claim` is unrepresentable by construction.

---

## 3. RBAC across all nine roles (SC-005, SC-006)

```bash
docker compose exec web pytest apps/claims/tests/test_permissions.py -v
```

**Expect**: a full pass over all nine roles, no exceptions. Specifically:

- **Read = 5 roles** (Claims Adjuster, Fraud Analyst, Compliance Officer, Risk
  Manager, Sys Admin) — narrower than Customer's seven and Policy's eight.
- **Write = 2** (Claims Adjuster, Sys Admin).
- **Underwriter is refused reads** though they write policies. Their 404 on a
  claim is a **refusal**; their 404 on a policy is an ordinary miss. This is the
  case the per-module registry exists for.
- Detail routes 404 rather than 403, so refusal is indistinguishable from
  nonexistence (FR-028).

---

## 4. Load the dataset (SC-002, SC-011)

> **Writes to the dev database. Confirm first.**

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv --dry-run
```

**Expect** — and nothing written:

```
Claims    — created: 2246  updated: 0  refused: 0  skipped: 364
Anomalies — recorded: 390  cleared: 0  (corrected: 0  absent: 0)
```

Then the real run:

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv
```

**Expect**: identical counts. `2246 + 364 + 390 = 3000` — every row accounted
for, none silently dropped.

Verify directly in the database rather than trusting the command's own report:

```bash
docker compose exec db psql -U postgres -d insurance -c "
SELECT
  (SELECT count(*) FROM claims_claim)                                  AS claims,
  (SELECT count(*) FROM claims_claimloadanomaly)                       AS anomalies,
  (SELECT count(*) FROM claims_claim WHERE claim_status = 'No Claim')  AS must_be_zero,
  (SELECT max(source_amount_usd) FROM claims_claimloadanomaly)         AS max_anomaly_amount;
"
```

**Expect**: `2246 | 390 | 0 | 19919.13`.

The `must_be_zero` column is the FR-004 assertion: no stored claim may carry a
status denying its own existence. `max_anomaly_amount` is the figure verified
against the source file — the largest amount the dataset attached to a row that
says no claim was made.

---

## 5. Re-run safety (SC-003, SC-012)

> **Writes to the dev database.**

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv
```

**Expect**:

```
Claims    — created: 0  updated: 2246  refused: 0  skipped: 364
Anomalies — recorded: 390  cleared: 0  (corrected: 0  absent: 0)
```

Everything **updated**, nothing created. The anomaly count stays **390** — it
does not become 780. That is FR-043's idempotency, and it is the reason
anomalies are a reconciled record rather than 390 fresh append-only rows per run.

---

## 6. The anomaly clearing distinction (SC-013, FR-044/044a/044b/048a)

> **Writes to the dev database.** The most important scenario here — it proves
> the behavior the spec was revised to require.

Build two modified copies of the source file:

```bash
# (a) one anomalous row CORRECTED — status still No Claim, amount zeroed
docker compose exec web python -c "
import csv
rows = list(csv.DictReader(open('data/Insurance_Dataset.csv')))
for r in rows:
    if r['Claim_Status'] == 'No Claim' and float(r['Claim_Amount_USD']) != 0:
        r['Claim_Amount_USD'] = '0.00'; break
w = csv.DictWriter(open('/tmp/corrected.csv','w',newline=''), fieldnames=rows[0].keys())
w.writeheader(); w.writerows(rows)
"

# (b) one anomalous row REMOVED entirely
docker compose exec web python -c "
import csv
rows = list(csv.DictReader(open('data/Insurance_Dataset.csv')))
out, dropped = [], False
for r in rows:
    if not dropped and r['Claim_Status'] == 'No Claim' and float(r['Claim_Amount_USD']) != 0:
        dropped = True; continue
    out.append(r)
w = csv.DictWriter(open('/tmp/absent.csv','w',newline=''), fieldnames=rows[0].keys())
w.writeheader(); w.writerows(out)
"
```

Run each and inspect the clearing reason:

```bash
docker compose exec web python manage.py loaddataset /tmp/corrected.csv
# Expect: Anomalies — recorded: 389  cleared: 1  (corrected: 1  absent: 0)

docker compose exec web python manage.py loaddataset /tmp/absent.csv
# Expect: Anomalies — recorded: 389  cleared: 1  (corrected: 0  absent: 1)
```

**The two runs clear the same number of anomalies for entirely different
reasons, and the system must never conflate them.** Confirm:

```bash
docker compose exec db psql -U postgres -d insurance -c "
SELECT status, cleared_reason, count(*)
FROM claims_claimloadanomaly GROUP BY 1,2 ORDER BY 1,2;
"
```

**Expect**: no `cleared` row with a null `cleared_reason`. There is no reasonless
clearing.

### Re-raise (FR-044b)

Load the original file again after the `absent` run:

```bash
docker compose exec web python manage.py loaddataset data/Insurance_Dataset.csv
```

**Expect**: the absent-cleared anomaly returns to `open`, with `cleared_reason`
and `cleared_at` reset to null. An anomaly does not stay cleared on the strength
of a run that never observed it.

### The audit trail is where history survives (FR-048a)

```bash
docker compose exec db psql -U postgres -d insurance -c "
SELECT action, timestamp FROM audit_auditlog
WHERE target_type = 'claims.ClaimLoadAnomaly'
ORDER BY timestamp;
" | head -20
```

**Expect** distinct action names — `claim_anomaly.recorded`,
`claim_anomaly.cleared_absent`, `claim_anomaly.reraised`,
`claim_anomaly.cleared_corrected` — never a generic `cleared` with the reason
buried in prose.

This is the point of FR-048a: the anomaly row holds only its latest state, so a
row cleared, re-raised, and cleared again has **overwritten its own history**.
The append-only trail is the only place both clearings survive. A Phase 4 query
for "how many anomalies did we actually verify as fixed" reads
`action = 'claim_anomaly.cleared_corrected'` and gets a truthful answer.

---

## 7. Claim history survives policy archival (SC-007, FR-008, FR-009)

> **Writes to the dev database.**

```bash
curl -s -X DELETE localhost:8000/api/policies/17/ -b cookies.txt -o /dev/null -w '%{http_code}\n'
curl -s "localhost:8000/api/claims/?policy=17" -b cookies.txt | python -m json.tool
```

**Expect**: `204`, then the claims **still listed**, still naming policy 17.
Withdrawing coverage must not erase claim history — this is the reverse of the
instinct to hide them.

Hard deletion is refused outright:

```bash
docker compose exec web python manage.py shell -c "
from apps.policies.models import Policy
try:
    Policy.all_objects.get(pk=17).delete()
    print('FAIL — deletion succeeded')
except Exception as e:
    print('OK —', type(e).__name__)
"
```

**Expect**: `OK — ProtectedError`.

---

## 8. The placeholder is gone (FR-049)

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/claims/placeholder/ -b cookies.txt
```

**Expect**: `404`. Only one claims surface remains.

```bash
grep -rn "PlaceholderView" apps/claims/
```

**Expect**: no matches.

---

## Success criteria coverage

| Criterion | Scenario |
|---|---|
| SC-001 claims per policy, one request | §7, contracts |
| SC-002 load produces claims, none for `No Claim` | §2, §4 |
| SC-003 re-run updates, does not create | §5 |
| SC-004 every change traceable | §1, §6 |
| SC-005 / SC-006 RBAC + non-disclosure | §3 |
| SC-007 nothing destroyed | §7 |
| SC-008 registry needs no handler change | §1 |
| SC-009 tests precede implementation | §1 |
| SC-010 stable paging | §1 |
| SC-011 390 anomalies, each naming a policy | §4 |
| SC-012 anomaly count stable across runs | §5 |
| **SC-013 clearing reason unambiguous** | **§6** |
