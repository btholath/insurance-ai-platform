# Quickstart: Validating the Prompt Library

**Feature**: 007-prompt-library | **Date**: 2026-09-02

A runnable end-to-end validation in the style established by
[005's](../005-risk-scoring-engine/quickstart.md) and
[006's](../006-automatic-risk-recompute/quickstart.md) quickstarts — every step
is something you execute and read the result of, not take on trust. Each maps to
a spec success criterion.

**Note on ports**: web is host **8001**. This feature publishes no new port.

**Note on the web container**: `docker compose restart web` after code changes
if a route 404s unexpectedly — Gunicorn's sync worker does not reload on file
changes. This matters more than usual here: the library is validated at
app-ready, so a validation change only takes effect on restart.

**Note on scope**: this feature makes **no LLM call** (FR-019, SC-008). Ollama
does not need to be running for any step below. If a step here ever requires it,
something has been built that this phase does not authorize.

## Prerequisites

```bash
docker compose up -d
docker compose ps                                    # db, redis, web, celery-worker healthy
docker compose exec web python manage.py migrate     # expect "No migrations to apply" — this feature adds no table
```

Dataset loaded and customers scored — needed only for Step 6's resolver check,
not for the library itself:

```bash
docker compose exec web python manage.py loaddataset /app/data/Insurance_Dataset.csv
docker compose exec web python manage.py computerisk
```

**Auth** — session cookie + CSRF, per 005's corrected pattern (not bearer
tokens). Log in once per role you test and keep the cookie jar:

```bash
curl -s -c /tmp/pl-admin.jar -X POST http://localhost:8001/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"…"}'
```

---

## Step 1 — The library loads, and loads completely (SC-001, SC-002)

Validation runs at app-ready. A healthy container is itself the first
assertion — but confirm it deliberately rather than inferring it from silence:

```bash
docker compose exec web python manage.py shell -c "
from apps.prompts import library, validation
validation.validate_library(library.TEMPLATES)
print(f'{len(library.TEMPLATES)} templates validated, library version {library.PROMPT_LIBRARY_VERSION}')
"
```

**Expect**: `7 templates validated, library version 1.0.0`.

**Expect 7, not 18.** The feature description said 18; the Phase 0 artifacts say
7 (`research.md` §1, verified against `~/insurance-ai-platform-phase0/app.py:43-101`
and `readme-setup-conclusions.md:192`). If this prints 18, someone has authored
11 templates with no Phase 0 validation behind them, which is what FR-016 exists
to prevent.

Now prove the failure is loud and total (FR-008) rather than skipping the bad
template:

```bash
docker compose exec web python manage.py shell -c "
from dataclasses import replace
from apps.prompts import library, validation
broken = replace(library.TEMPLATES[0], body=library.TEMPLATES[0].body + ' {Customer.nonexistent_field}')
try:
    validation.validate_library((broken,) + library.TEMPLATES[1:])
    print('FAIL: invalid library accepted')
except Exception as e:
    print(f'rejected as expected: {e}')
"
```

**Expect**: a rejection naming `nonexistent_field`, and naming the template it
came from. **A pass here is a failure of the feature.**

---

## Step 2 — The whitelist rejects real fields on ineligible types (SC-002a)

This is the step the spec review added, and the one most worth running by hand.
Every declaration below names a field that **genuinely exists** — field-existence
checking alone would admit all of them.

```bash
docker compose exec web python manage.py shell -c "
from apps.prompts import bindings, validation
for rt, fn in [('User','password'), ('User','is_superuser'), ('User','role'),
               ('AuditLog','before'), ('AuditLog','after')]:
    try:
        validation.check_binding(bindings.FieldBinding(rt, fn, '{%s.%s}' % (rt, fn)))
        print(f'  FAIL  {rt}.{fn} was ACCEPTED')
    except Exception as e:
        print(f'  ok    {rt}.{fn} rejected -> {e}')
"
```

**Expect**: all five rejected, each because the *record type* is ineligible —
not because the field is missing. Confirm the error says so; a "no such field"
message here would mean the whitelist is not what rejected it.

Confirm the fields really do exist, so you know the test has teeth:

```bash
docker compose exec web python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.audit.models import AuditLog
print('User.password  ->', get_user_model()._meta.get_field('password'))
print('AuditLog.before ->', AuditLog._meta.get_field('before'))
"
```

**Expect**: both resolve to real fields. That is the whole point —
`AuditLog.before` holds prior-state snapshots of *other* records, so one accepted
declaration against it re-exposes arbitrary fields of arbitrary types through a
single entry that passes every other check.

And the equality pin (FR-024), in both directions:

```bash
docker compose exec web python -m pytest apps/prompts/tests/test_bindings.py -k whitelist -q
```

**Expect**: passing. This test must fail if a sixth type is added *or* if one of
the five is dropped — the same both-directions discipline as
`apps/risk/tests/test_rules.py:270`.

---

## Step 3 — Version cannot drift from content (SC-003)

```bash
docker compose exec web python -m pytest apps/prompts/tests/test_library.py -k version -q
```

Then prove it detects a real edit. Change one character of any template's `body`
in `apps/prompts/library.py` **without** touching its `version`, and re-run:

**Expect**: failure naming the edited template. Revert the edit and confirm it
passes again. A version that silently accepts two different bodies is FR-010's
exact failure mode.

---

## Step 4 — RBAC: all nine read, one writes (SC-004)

Unlike the other four modules, **every role may read** — a template holds no
customer data (`research.md` §4). Verify the universal set rather than assuming
it:

```bash
for role in risk_manager underwriter fraud_analyst compliance_officer \
            claims_adjuster customer_service product_manager \
            executive_leadership system_administrator; do
  # log in as a user in $role into /tmp/pl-$role.jar first
  code=$(curl -s -o /dev/null -w '%{http_code}' -b /tmp/pl-$role.jar \
         http://localhost:8001/api/prompts/templates/)
  echo "$role -> $code"
done
```

**Expect**: `200` for all nine. **Executive Leadership returning 200 is the
signal that matters** — it is excluded from all four existing view sets, so a
403 there would mean a role set was copied from a neighbouring module rather
than chosen for this one.

Unauthenticated:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8001/api/prompts/templates/
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8001/api/prompts/templates/risk_assessment_summary/
```

**Expect**: `403` on the collection route, `404` on the detail route — existence
non-disclosure, unchanged from `apps/core/permissions.py`'s established
behavior on a non-pk lookup field.

---

## Step 5 — The registry has a fifth consumer, and the other four are untouched (SC-005, SC-006)

```bash
docker compose exec web python manage.py shell -c "
from apps.core import audit_routes
for r in audit_routes.all_routes():
    print(f'{r.prefix:20} {r.target_type:28} view={len(r.view_roles)} write={len(r.write_roles)}')
"
```

**Expect** five rows, the prompts row showing `view=9 write=1`:

```
/api/customers/      customers.Customer           view=7 write=2
/api/policies/       policies.Policy              view=8 write=2
/api/claims/         claims.Claim                 view=5 write=2
/api/risk/           risk.RiskAssessment          view=5 write=2
/api/prompts/        prompts.PromptTemplate       view=9 write=1
```

Now a refusal, end to end. Count audit rows, make an unauthenticated request,
count again:

```bash
docker compose exec web python manage.py shell -c "
from apps.audit.models import AuditLog
print('before:', AuditLog.objects.filter(target_type='prompts.PromptTemplate').count())
"
curl -s -o /dev/null http://localhost:8001/api/prompts/templates/
docker compose exec web python manage.py shell -c "
from apps.audit.models import AuditLog
qs = AuditLog.objects.filter(target_type='prompts.PromptTemplate').order_by('-timestamp')
print('after:', qs.count())
row = qs.first()
print(row.action, row.outcome, row.actor_identifier or '(anonymous)', row.context)
"
```

**Expect**: count incremented by 1; `prompt.viewed refused (anonymous)` with the
path in `context`. Note `prompt.*`, not `customer.*` — a prompt refusal recorded
under another module's action name would mean the prefix is being swallowed by
an existing entry, the exact failure `/api/risk/`'s top-level mount exists to
avoid.

Now confirm a **successful** read writes **no** row — the deliberate narrowing of
FR-015 (`research.md` §7, plan.md Complexity Tracking):

```bash
curl -s -o /dev/null -b /tmp/pl-admin.jar http://localhost:8001/api/prompts/templates/
docker compose exec web python manage.py shell -c "
from apps.audit.models import AuditLog
print('after success:', AuditLog.objects.filter(target_type='prompts.PromptTemplate').count())
"
```

**Expect**: unchanged from the previous count. This matches every existing
module — `apps/risk/views.py` has zero `record_action` calls.

Finally, the four existing consumers, unaffected:

```bash
docker compose exec web python -m pytest \
  apps/customers apps/policies apps/claims apps/risk apps/audit apps/core -q
```

**Expect**: all passing, nothing skipped.

---

## Step 6 — Bindings resolve against real data, still with no LLM call (SC-009)

The resolver is 4a's deliverable half; rendering waits for 4b (`research.md` §6).

```bash
docker compose exec web python manage.py shell -c "
from apps.customers.models import Customer
from apps.prompts import library, bindings
c = Customer.objects.filter(risk_assessment__isnull=False).first()
t = next(t for t in library.TEMPLATES if t.identifier == 'risk_assessment_summary')
for b, v in bindings.resolve(t, customer=c).items():
    print(f'  {b.record_type}.{b.field_name} = {v!r}')
"
```

**Expect**: one line per declared binding, each with a real value from that
customer. Nothing outside the declaration appears — that is the grounding
contract doing its job, and it is exactly the field-by-field mapping 4b's
post-generation validator will consume.

Confirm `RiskAssessment.score` resolves to the authoritative 0–90 integer, not
`Customer.risk_score`'s `score / 100` denormalized mirror
(`apps/customers/models.py:122-131`).

---

## Step 7 — No LLM call anywhere (SC-008)

```bash
grep -rniE 'ollama|requests\.post|httpx|openai|langchain|generate\(' apps/prompts/ || echo "clean — no LLM call surface"
docker compose exec web python -m pytest apps/prompts -q --cov=apps.prompts --cov-report=term-missing
```

**Expect**: `clean`, and a passing suite at 100% coverage on `apps/prompts/`
(the Phase 3b bar — `readme-runbook-phase3.md` records 100% on every
`apps/risk/` file).

Stopping Ollama entirely and re-running the suite is the strongest form of this
check, and it should change nothing:

```bash
# with Ollama stopped:
docker compose exec web python -m pytest apps/prompts -q
```

**Expect**: identical result. A failure here would mean something in this phase
reached for a model it is not authorized to call.

---

## What this quickstart does **not** cover

Deliberately out of scope for 4a, and each belongs to 4b:

- Generating text from a template (no model call exists yet).
- Validating generated text against the declared bindings — the post-generation
  validator is 4b's deliverable; 4a delivers the contract it will consume.
- Rendering a finished prompt string. 4a stops at the resolver
  (`research.md` §6).
- Latency. Phase 0 measured 42.0s–119.8s per generation on CPU-only inference
  (`readme-setup-conclusions.md` §9) against the BRD's `<10s` NFR — a real
  problem, and 4b's to solve with the Celery infrastructure Phase 3b built.
