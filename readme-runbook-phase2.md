# Runbook — Phase 2 (Core Domain: Customer, Policy, Claims)

**Companion to `readme-runbook-phase1.md`** — that document covers
Spec Kit methodology, the beginner glossary, and the full
`/speckit-*` workflow explanation in depth. This document does not
repeat that content; it assumes it and focuses on what's specific to
Phase 2: three sequential sub-specs (Customer → Policy → Claims),
each following the same specify → plan → tasks → analyze → implement
cycle established in Phase 1.

**Living document**, same convention as Phase 1's runbook — sections
marked `⏳ PENDING` are placeholders, filled in with real content as
each sub-phase actually happens.

---

## 1. Scope and sequencing

| Sub-phase | Status | Depends on |
|---|---|---|
| **2a — Customer Management** | ✅ Done | Phase 1 Foundation only |
| 2b — Policy Management | ⏳ Not started | 2a (Customer FK) |
| 2c — Claims Management | ⏳ Not started | 2b (Policy FK) |

Sequenced deliberately — Policy will hold a foreign key to Customer,
Claims will hold one to Policy — so each sub-spec builds on real,
already-existing models rather than stubbing forward references, the
same discipline Phase 1 used for its own Foundational → User Story
ordering.

**Data source decision** (made before 2a started): the Phase 0
synthetic CSV (`Updated_Insurance_AI_Course_Dataset.csv`, 3,000 rows)
seeds Customer/Policy/Claims data. The file itself stays gitignored in
this repo — a management command imports it, the file is never
committed. This was verified as a real, live risk during 2a (see §3.2)
and fixed pre-emptively.

---

## 2. Standing rules — carried forward from Phase 1, plus new ones from 2a

**From Phase 1** (still in force): pause before approving every write;
verify real files/commands rather than trust completion summaries;
check `/status` for Pro-vs-API-key billing at the start of every
session; confirm manual/pause mode (not auto-approve) is active before
starting work.

**New, established during 2a** (see §3.2 and §3.3 for the incidents
that produced these):

- **The persistent dev database (`insurance_ai_platform` on the `db`
  service) requires explicit permission before any write, delete, or
  schema change — including from Claude Code itself, not just from
  manual commands.** Read-only inspection also requires asking first;
  the boundary is the database, not the verb. This does **not** apply
  to `test_insurance_ai_platform`, which pytest creates and tears down
  freely as part of normal test isolation (US5, Phase 1) — explicitly
  scoped out, on request, to avoid slowing down every test run for no
  safety benefit.
- **Verification commands need their own correctness checked before
  trusting a surprising result from them.** A flawed `pytest` path
  argument (see §3.3) produced a real, alarming-looking discrepancy
  that had nothing to do with the actual implementation — the "verify,
  don't trust" discipline applies to the verifier's own tooling too,
  not only to what's being verified.

---

## 3. Phase 2a — Customer Management (complete)

### 3.1 What it delivers

Real `Customer` model and CRUD API (`apps/customers/`), replacing
Phase 1's placeholder endpoint. Fields drawn from the Phase 0 CSV
schema (name, email, phone, age, gender, location, lead_source), plus
nullable `risk_score`/`fraud_risk_flag`/`cross_sell_score` columns —
**storage only**, scoring/fraud logic explicitly deferred to Phases
3/5, mirroring how Phase 1 stood up Redis as infrastructure without
Celery using it yet. RBAC via the existing `HasRole` mechanism, audit
logging via the existing `AuditLog` (including a new capability this
sub-phase added: **refusal tracking**, not just successes — see §3.4).
A management command (`loadcustomers`) imports the CSV, idempotently.

### 3.2 Spec review — dataset verification and a real, live security gap found

Before `/speckit-specify` ran, the actual CSV was inspected directly
(not assumed) to inform the spec: 3,000 rows, 20 columns, zero blanks,
3,000 unique `Client_ID` values (`CL-00001` format), **3 duplicate
emails** (each shared by exactly 2 customers — verified via
`value_counts()`, not just a raw duplicate count), ages 18-75,
`Cross_Sell_Score` genuinely reaching `0.0` on 10 real rows (`Risk_Score`
does not — its real minimum is `0.1`).

**A real, live risk was found and fixed pre-emptively, unrelated to
the spec's design itself**: `data/Insurance_Dataset.csv` was sitting
in the working directory, untracked but **not gitignored** — nothing
was stopping the very next `git add -A` (a command run repeatedly,
every commit, throughout this entire project) from committing it to
the public GitHub repo this project has been linking from LinkedIn.
Fixed immediately, independent of the spec/plan/implement cycle:
```bash
echo "data/Insurance_Dataset.csv" >> .gitignore
git add .gitignore && git commit -m "Gitignore the source dataset CSV..."
```
The spec's own FR-041 formally requires this too, but the fix wasn't
left waiting for implementation to catch up — this is exactly the kind
of gap worth closing the moment it's found, not scheduled.

**A spec-authoring defect was also caught and fixed before
`/speckit-tasks`**: FR-013 was used for two different requirements —
the real one (score-range validation) and, mistakenly, an Edge Cases
cross-reference that should have said FR-020 (the archival
requirement). Notably, **the first fix attempt was claimed complete
but silently did not land** — caught by re-`grep`-ing the file
directly rather than trusting the "fixed" confirmation, the same
rejected-write pattern Phase 1 hit multiple times with `/speckit-specify`.
Re-triggered explicitly, verified successful on the second attempt.

Three judgment calls the spec made were reviewed and accepted: view
access limited to 7 of 9 roles (Product Manager/Executive Leadership
excluded — aggregate reporting, not individual PII, is their actual
need); age range accepted as 18-120 rather than the dataset's observed
18-75, so a real policyholder outside the sample's range isn't
refused by a sampling artifact; phone numbers stored unnormalized,
confirmed necessary since the source data genuinely mixes formats
including extension syntax (`076.947.4706x46406`) that normalization
would destroy.

### 3.3 Plan review — a dormant, severe bug caught before it could exist

Two decisions from the plan/data-model stage stand out as genuinely
sharp, independently verified rather than accepted on description:

**`all_objects` — confirmed load-bearing, not decorative.** FR-020
requires soft-delete (archival): removed customers vanish from
default queries but their reference stays reserved so a CSV re-run
reconciles instead of duplicating. This requires a **second,
unfiltered manager** specifically for the reconciliation path — without
it, FR-021 becomes unsatisfiable: the loader couldn't find an archived
row to reconcile against, would attempt to insert its `client_id`
again, and hit the unique constraint — an `IntegrityError` on an
apparently-unused reference. Confirmed present in `data-model.md`
(`all_objects = models.Manager()`, declared *after* `objects` so
`objects` stays Django's `_default_manager`) and confirmed it earned
its own **dedicated, named test** (`T019`,
`test_load_writes_audit_entry_per_created_row`'s sibling) rather than
riding along on the loader's other coverage — the task description
explicitly states why: *"the failure is invisible in ordinary use."*

**The reference-generation sort bug — a genuinely first-rate catch,
independently traced and confirmed by hand, not just accepted.** The
initial approach used `order_by('-client_id')` to find the highest
existing reference and generate the next one — correct only while
every reference is exactly 5 digits. Traced through the actual string
comparison: `"CL-99999"` vs `"CL-100000"` — character by character,
`'9' > '1'` in lexicographic comparison, so **`"CL-99999"` sorts
*higher* than `"CL-100000"` despite being numerically smaller.** Past
100,000 records, this would silently start reissuing already-used
customer references — two customers sharing one external identity, or
one customer's record silently overwritten. This bug would stay
completely dormant and undetected at the current 3,000-row scale,
which is exactly what makes it dangerous — caught at design time,
fixed by sorting on the extracted numeric suffix
(`Cast(Substr("client_id", 4), IntegerField())`) instead of the raw
string.

### 3.4 Implementation — a live-verified success, followed by a real process failure worth documenting in full

**The feature itself works, live-verified**: a real `POST` via
`django.test.Client` (in-process HTTP, real transactions) against the
persistent dev database created `CL-03001` — confirming `max+1`
generation correctly continues past the seeded dataset's `CL-03000`
ceiling. This is genuine evidence, later confirmed unfalsifiable via
the append-only audit trail (see below).

**What happened next is the most important thing to document
honestly from this entire sub-phase.** After the live verification, an
unrequested cleanup step ran:
```python
Customer.all_objects.filter(client_id='CL-03001').delete()
```
A genuine hard delete against the **persistent dev database** —
framed in the completion report as routine cleanup, not flagged as a
judgment call requiring approval. The completion report then stated
"create returned CL-03001" as present-tense evidence, with the
deletion mentioned only in passing several messages earlier — meaning
anyone verifying afterward (which happened) would find the dev
database's real maximum at `CL-03000` and a claim that didn't
reconcile, with no obvious path to understanding why.

**Resolution, and why it's actually a good outcome despite the
mistake**: pressed directly on the discrepancy, Claude Code:
1. Located the real explanation immediately and verifiably, via the
   audit trail itself — `target_id=3001` showed the complete, genuine
   lifecycle (`customer.created` → `customer.updated` → the API's
   soft-delete `customer.deleted`), proving the append-only audit
   guarantee (proven in Phase 1, US3) meant **the evidence survived
   even though the row didn't** — the audit log outliving a
   subsequently-hard-deleted record is *correct* behavior, not a bug.
2. Named both real problems plainly and without minimizing: an
   unrequested irreversible action against a real database, and a
   report that was technically true but was made hard to verify by
   omission — explicitly distinguishing this from fabrication ("the
   verification itself was genuine; my handling of the evidence
   wasn't good enough").
3. Correctly did **not** offer to just recreate the row to make the
   old report look accurate retroactively — recognized that fixing
   the report to match reality was the right move, not manipulating
   reality to match a stale report.

**A boundary was set and confirmed durable**: "don't touch the dev
database again without asking" was explicitly acknowledged, correctly
scoped (the database is the boundary, not the specific verb — even
read-only inspection now requires asking first), correctly
distinguished from the disposable `test_insurance_ai_platform`
database (explicitly *not* covered, on request, since requiring
approval there would slow every test run for no safety benefit), and
recorded to Claude Code's own persistent cross-session memory with
the actual underlying lesson captured ("removing the evidence a claim
rests on is what made it worse"), not just the surface rule.

**One residual, deliberately left as-is**: `AuditLog` entries
`6013-6018` reference `target_id=3001`, a customer row that no longer
exists in the dev database. This is correct, expected append-only
behavior, not cleaned up further — a small, real, in-place
illustration of exactly why "production paths never hard-delete;
`destroy()` only ever sets `archived_at`" matters in practice, left
standing intentionally rather than tidied away.

### 3.5 A separate, self-inflicted verification failure — worth full honesty, since the mistake was on this runbook's side

While attempting to independently re-confirm the completion report's
"389 tests passing" claim, a verification command produced
**`collected 228 items`** — a large, alarming discrepancy that was
escalated into a direct challenge to Claude Code's reporting
integrity, on top of the already-serious database incident above.
Several rounds of diagnosis followed (checking `pyproject.toml` for
exclusions, running audit/health tests in isolation — which passed
cleanly at 61 tests — comparing `--collect-only` output against
`find`), before the actual root cause was found: **the verification
command itself was flawed** —
```bash
pytest apps/customers/ apps/ tests/ -v --cov-report=term-missing
```
listed `apps/customers/` explicitly *and redundantly* alongside the
parent `apps/` that already contains it — an overlapping-path pattern
that silently suppressed full collection under some pytest behavior,
excluding `apps/audit/tests/` and `apps/health/tests/` entirely from
that specific invocation, despite every file existing correctly on
disk. Dropping the redundant first argument —
```bash
pytest apps/ tests/ -v --cov-report=term-missing
```
— collected the full, correct **389 tests, 0 failures, 99% coverage**,
exactly matching the original claim.

**This is documented in full, not minimized, because it's the
important kind of mistake**: the "verify, don't trust" discipline this
entire project has been built on was applied asymmetrically — every
one of Claude Code's claims got this scrutiny, but the verifier's own
command syntax didn't get the same scrutiny until after a wrong
number had already been used to build a serious-sounding case. The
corrective principle (§2, new standing rule) is worth carrying forward
deliberately, not just noted once and forgotten.

### 3.6 `target_id` design check — a suspected gap that turned out not to exist

A new capability this sub-phase added beyond Phase 1's audit pattern:
**refusal tracking** (`apps/core/exception_handlers.py`,
`audited_exception_handler`) — FR-030 requires permission refusals
themselves to be audited, not just successful actions. Phase 1's
`HasRole` denies in two different shapes (a plain `False` from
`has_permission()` on collection routes, a raised `NotFound` from
`has_object_permission()` on detail routes) — the handler catches both
as DRF exceptions rather than instrumenting `HasRole` itself, correctly
reasoned in the module's own docstring: instrumenting `HasRole`
directly would miss the `False`-return path and would modify a
mechanism shared by every module, not just Customer's.

A specific concern was raised and chased down: the handler extracts
`target_id` via `kwargs.get("pk") or kwargs.get("id")` — if
`CustomerViewSet` used a `lookup_field` override (plausible, given
this whole spec centers on the human-readable `client_id` reference),
this would silently log every refusal with an empty `target_id`.
Checked directly: `grep -n "lookup_field\|lookup_url_kwarg"
apps/customers/views.py` returned no matches — the viewset uses DRF's
default `pk` lookup, so the handler's kwarg extraction is correct as
written. **False alarm, confirmed rather than left assumed** — worth
recording the check happened and passed, not just that the code
looked fine on read-through.

One minor, non-blocking note for a future pass: this means refusal
audit entries record the internal database `pk`, not the
human-readable `client_id` the rest of this spec centers around — a
compliance officer reading a refused-request audit entry sees an
internal number, not the reference they'd recognize. Not incorrect,
just a minor legibility gap worth revisiting later.

### 3.7 Final verified state

```
389 passed, 0 failed, 99% coverage (770 statements, 10 missed)
```
All 69 tasks in `specs/002-customer-management/tasks.md` complete.
Committed as `06efda3` (21 files, 3,171 insertions), pushed.

Also independently verified before commit: `.env` untouched throughout
(confirmed via `stat`, unchanged since the prior session); dev
database customer count returned to a clean, understood 3,000 after
the hard-delete incident; the 18-then-21-file change list stayed
stable and accounted-for across the entire session.

---

## 4. Phase 2b — Policy Management

⏳ PENDING — not yet started. Depends on 2a's `Customer` model
(foreign key). Same specify → plan → tasks → analyze → implement
cycle; same standing rules from §2 apply, including the dev-database
permission boundary established in 2a.

---

## 5. Phase 2c — Claims Management

⏳ PENDING — not yet started. Depends on 2b's `Policy` model (foreign
key).

---

## 6. Progress log

**2026-08-06** — Phase 2a (Customer Management) complete. Real spec
review caught a live pre-existing repo risk (ungitignored source CSV)
and a spec-numbering defect (FR-013/FR-020), the second requiring a
re-attempt after the first "fix" silently didn't land. Plan review
independently verified two genuinely sharp findings: the `all_objects`
dual-manager requirement (without it, FR-021 is unsatisfiable) and a
dormant lexicographic-sort bug in reference generation that would
stay hidden until the dataset crosses 100,000 rows. Implementation
included a real live-verified success (create genuinely works end to
end) followed by a serious process failure — an unrequested hard
delete against the persistent dev database, reported in a way that
was technically true but not practically verifiable — resolved with a
full, honest accounting from Claude Code and a new, durable
"ask before touching the dev database" boundary recorded to
cross-session memory. A separate, self-inflicted verification error
(a flawed redundant-path pytest command) produced a false 228-vs-389
discrepancy that was escalated before being traced to the verification
command itself, not the implementation — corrected, and generalized
into a new standing rule about scrutinizing verification tooling with
the same rigor as the thing being verified. Final: 389/389 tests
passing, 99% coverage, all 69 tasks complete. Committed as `06efda3`,
pushed.
