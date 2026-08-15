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
| **2b — Policy Management** | ✅ Done | 2a (Customer FK) |
| **2c — Claims Management** | ✅ Done | 2b (Policy FK) |

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

### Pre-flight checklist — run at the start of every session, before any `/speckit-*` command

```bash
cd ~/insurance-ai-platform
git status                          # confirm clean tree before starting new work
docker compose build web            # rebuild BEFORE trusting any test run this
                                     # session — see the stale-image rule below;
                                     # this is the single cheapest insurance
                                     # against a repeat of Phase 2b's false 389
docker compose up -d
docker compose ps                   # confirm all three healthy
```
Then inside Claude Code:
```
/status     # confirm Claude Pro account, not an API key
/model      # confirm Opus for specify/plan, Sonnet for tasks/implement
```
Confirm `⏸ manual mode on`, not `⏵⏵ accept edits on` — check the
bottom-of-screen indicator directly, don't assume it carried over from
the last session.

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
  argument (see §3.5) produced a real, alarming-looking discrepancy
  that had nothing to do with the actual implementation — the "verify,
  don't trust" discipline applies to the verifier's own tooling too,
  not only to what's being verified.

**New, established during 2b**:

- **A passing test run proves nothing if the container image itself is
  stale.** `docker compose exec web pytest` can report a clean,
  plausible-looking pass count while running against code that
  predates the current working tree entirely, if the image was never
  rebuilt after source changes (this project has no dev-time volume
  mount by design — see Phase 1's own documented no-dev-volume-mount
  gotcha). The tell isn't the pass/fail line, which can look completely
  normal — it's the **coverage table**: new or changed modules showing
  as absent or unexpectedly low-coverage is the actual signal a stale
  image is being tested instead of the real one. This is now the first
  step of the pre-flight checklist above, not left to memory.

**New, established during 2c's infrastructure incident (§5.3)**:

- **Docker volume survival cannot be inferred from other volumes'
  survival.** Seeing unrelated projects' volumes intact does not mean
  *this* project's volume wasn't independently removed and recreated —
  these are separate facts. Check the specific volume's own
  `CreatedAt` timestamp directly (`docker volume inspect <name>`)
  before offering any reassurance about data survival, every time.
- **The `Server: Splunkd` / unexpected `303` anomaly, first seen in
  Phase 1 and previously documented as "closed" (attributed to
  unfixable host-network interference), was wrong.** The real cause:
  a local `splunkd` process squatting on port 8000 whenever nothing
  else has bound it first — not network-level interception at all.
  If this resurfaces, check `lsof -i :8000` / `ss -tlnp` before
  assuming it's the same "nothing we can do" situation — it was
  always locally diagnosable and fixable via a simple port remap.

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

## 4. Phase 2b — Policy Management (complete)

### 4.1 What it delivers

Real `Policy` model and CRUD API (`apps/policies/`), replacing Phase
1's placeholder endpoint. FK to `apps.customers.Customer`. Fields per
the Phase 0 CSV: `policy_type` (Life/Auto/Property/Health),
`start_date`/`end_date`, `premium_usd`, plus nullable
`renewal_probability` (storage only, same deferred-scoring pattern as
Customer's risk/fraud/cross-sell fields). The CSV loader extends to
seed Policy records alongside Customer's, in the same transaction per
row. RBAC and audit logging reuse the existing mechanisms — and this
sub-phase generalizes the audit-refusal mechanism itself, previously
hardcoded to Customer alone, into a shared registry both modules (and
Claims, next) draw from.

### 4.2 Spec review — every prior-session concern correctly incorporated

Before `/speckit-specify` ran, checking the actual codebase (not
assumption) confirmed the refusal handler was genuinely hardcoded to
`/api/customers/` and `customers.Customer` in four separate places —
extending it to Policy was real work, not a free inherit, and the
spec was written with that explicitly as scope. All dataset claims in
the Assumptions section were independently re-verified against the
real CSV rather than trusted: coverage types (`Auto/Health/Life/
Property`), premium range (`$100.68`-`$4,997.79`), zero `end_date ≤
start_date` violations across all 3,000 rows, zero blanks, 3,000
unique `Client_ID`s matching 3,000 rows — every number checked out
exactly.

**Both interactive Q&A decisions were resolved deliberately, not
defaulted through**:
- **Cardinality** (`FR-003`): a customer may hold multiple policies,
  even though the current dataset happens to be 1:1 — a real insurance
  platform shouldn't have a business rule baked in permanently just
  because one synthetic sample happened to be shaped that way. A note
  was attached flagging that the loader's re-run matching therefore
  needs to key on `(customer, policy_type)`, not customer alone — this
  landed in the spec as `FR-039` essentially verbatim.
- **Archive cascade**: policies stay live and linked when their
  customer is archived (Option 1), *not* cascaded (Option 2) or
  blocking (Option 3). Option 3 was specifically ruled out on real
  evidence, not preference — the hidden preview text confirmed *all
  3,000 seeded customers hold a live policy*, meaning a
  block-until-resolved rule would have made customer archival
  completely non-functional against the actual dataset from day one.
  Cascade (Option 2) was rejected on the grounds that archiving a
  customer record (a CRM action) and archiving a policy (an insurance-
  coverage action) are genuinely different business events that
  shouldn't be automatically coupled.

No FR-numbering defects this time (Customer's spec had the FR-013/
FR-020 duplicate) — checked specifically, Edge Cases correctly
cross-references FR-021 exactly as it should.

### 4.3 Plan review — two genuinely sharp, independently-verified findings

**Live-scoped `(customer, policy_type)` uniqueness — deliberately the
*opposite* of Customer's reference-reservation pattern, and correct to
be so.** Customer's archived `client_id` stays reserved forever
(prevents a CSV re-run from ever creating a duplicate). If Policy's
uniqueness copied that same "archived still counts" logic, a customer
would be permanently blocked from ever getting a new policy of a given
type after their old one was archived — wrong, since canceling and
later re-issuing the same coverage type is normal. The plan correctly
recognized these two entities need *opposite* semantics despite a
superficially similar archival shape, rather than mechanically reusing
Customer's pattern because it worked there.

**The archived-customer FK resolution bug, caught before it could
exist.** *"FK resolved through `Customer.objects` would 404 policies
of archived customers"* — proactively identified, and the plan
specified both traversal directions (Policy→Customer, Customer→Policy)
get **separately** tested, since they fail independently. Confirmed
this reasoning carried through into `T016`, which explains the
concrete human consequence too: resolving through the wrong manager
*"would produce the misleading second message and send an underwriter
hunting for a record that was deliberately removed."*

**The refusal-handler generalization — explicitly flagged as the
highest-risk change in the whole plan**, because it modifies shipped,
Phase 2a-tested code rather than only adding new code: *"It currently
hardcodes customer knowledge in four places... this is the highest-
risk change here: it touches shipped, tested code."* Refactored into a
registry keyed by route prefix (`apps/core/audit_routes.py`) rather
than adding a third hardcoded copy for Policy (with Claims as an
already-known fourth consumer coming next) — turning "add a new
audited module" into a data-entry problem instead of a
code-duplication problem.

### 4.4 Tasks review — real engineering discipline, not just checkbox coverage

85 tasks (vs. Customer's 69) — larger, reflecting the registry
refactor as genuinely new shared infrastructure, not just
Policy-specific CRUD. Several things worth naming specifically:

- **A new pattern**: `T002`/`T003` capture a provable baseline
  *before* touching shipped code — *"record the passing count
  (expected: 389)"* and *"record the current customer audit test
  count... expected: 22... the number must not change"* — so any
  regression from the risky refactor is immediately demonstrable, not
  just suspected.
- **Deliberate sequencing to isolate risk**: the registry refactor
  (`Phase 4`, marked `🔴 HIGHEST RISK`) runs *before* any Policy route
  exists, specifically so it can be verified against the existing
  Customer suite alone — *"Doing it after policy routes emit refusals
  would tangle 'did the refactor break customers?' with 'is the new
  policy behaviour right?'"*
- **A guardrail against a real anti-pattern**: `T071` explicitly
  states that if a Policy audit entry looks wrong, the fix belongs in
  the per-module registry data (`audit_routes.py`), *never* the shared
  handler — protecting the refactor from the exact kind of
  module-specific patch creeping back into shared code that
  generalizing it was meant to prevent.
- **A test defending a deliberate design choice from a plausible
  future mistake**: `T063`'s "cross-module asymmetry" test pins that
  Product Manager and Customer Service have genuinely *different*
  permissions between Customer and Policy — specifically so a future
  engineer noticing the similar-looking matrices doesn't "harmonize"
  them without realizing the difference was intentional.
- **Cross-session memory correctly applied**: `T065` explicitly
  recalls the `force_authenticate` staleness gotcha from **Phase 1's**
  own US2 testing, not just Customer's more recent lessons.

### 4.5 Implementation — three real bugs, one high-risk refactor landing clean, and a resolved cross-session evidence question

**Bug 1 — a falsely-green baseline from a stale container image.**
`docker compose exec web pytest` initially reported a clean `389`
passing while none of the Phase 2b files existed inside the running
container at all — the image had never been rebuilt after source
changes and was still serving code baked on July 31. **The tell
wasn't the pass/fail line, which looked completely normal — it was
the coverage table**, showing the new modules as entirely absent
rather than low-coverage. This is now documented as a new standing
rule (§2) — a passing run alone proves nothing if the image itself is
stale, and this project has no dev-time volume mount by design, so
this exact failure mode is a real, recurring risk, not a one-off.
Resolved by switching to a bind-mounted runner for the fast TDD loop,
then a final `--build` run so the deployable image is what actually
got verified. True baseline, once rebuilt: 453 tests, 4 failures —
genuinely different from the false `389`.

A real cross-session question this raised — **whether the Customer
Management `389`-test confirmation done earlier in this project (and
the separate `228`-vs-`389` pytest-path investigation) were also
against a stale image** — was resolved directly, not left open.
Claude Code correctly stated it had no record of those events and
declined to fabricate a connection ("I'd rather say so than
reconstruct a plausible-sounding history"). Resolved independently
instead, using evidence available at review time: the `228`-item
collection output from that earlier investigation contained live,
genuine `apps/customers/tests/` entries, and the corrected `389` run's
coverage table showed real coverage numbers for Customer's own code —
neither is possible against an image old enough to predate Customer
Management entirely. The two incidents are confirmed unrelated: the
earlier `228` was a real, already-diagnosed pytest redundant-path bug
(§3.5); this session's staleness is a distinct, newly-discovered risk.
Worth recording as its own small lesson: an "I don't know" answered
honestly, then actually resolved with available evidence, is more
valuable than either a guessed answer or an unresolved worry.

**Bug 2 — an FR-015 message-contract violation, from DRF's own
auto-generated validator.** `UniqueTogetherValidator`, synthesized
automatically by DRF from the model's `UniqueConstraint`, ran *before*
`validate()` and reported the duplicate-policy error under
`non_field_errors` — meaning the response never named `policy_type` as
the contract required, despite the explicit validation logic being
written correctly. Fixed by disabling the auto-generated validator so
the explicit check owns the error message. A genuinely subtle DRF
internals interaction, not a logic mistake.

**Bug 3 — an FR-031 gap latent since Phase 2a, only surfaced now.**
An unpermitted user hitting a *nonexistent* record ID recorded no
refusal, in both Customer and Policy. Root cause: Django's
`get_object_or_404` (used inside `get_object()`) raises `Http404`, not
DRF's `NotFound` — and the refusal handler's `isinstance` check only
covered `NotFound`, silently missing every case where the target
didn't exist at all. Phase 2a's own test suite only ever exercised the
*permitted* user's 404 case, never the unpermitted-user-plus-
nonexistent-id combination, so this gap went undetected through the
entirety of Customer's "zero gaps found" review. Fixed in the shared
handler (confirmed directly: `_REFUSAL_EXCEPTIONS` now includes
`Http404` alongside `NotFound`, with a docstring explaining the real
framework distinction) — and the Phase 4 regression gate (22/22
Customer audit tests) was re-run and confirmed passing *after* this
fix, proving it didn't just fix Policy while silently breaking
Customer's existing behavior.

**The high-risk registry refactor landed clean.** `apps/core/
audit_routes.py` now holds an `AuditedRoute` registry (prefix, target
type, action prefix, role sets), populated in `CoreConfig.ready()`
(not at import time — confirmed via `git diff apps/core/apps.py`,
correctly reasoned: the handler is referenced from `settings.py`,
which loads before the app registry can import models). The T002/T003
baseline gate held with a genuinely zero-line diff on the Customer
audit test file itself.

**Two judgment calls disclosed, not hidden**: Phases 1-3 turned out to
already be implemented from a prior session — verified rather than
blindly rewritten, and one broken test helper found and fixed along
the way (`payload(customer=<pk>)` calling `.pk` on an already-integer
value). And six assertions in Customer's own `test_loadcustomers.py`
needed updating for the loader's new two-line count output format — a
real, contract-specified behavior change, but still an edit to
*shipped* tests, called out explicitly rather than silently folded in.

**One task correctly deferred, not skipped silently**: `T083` (the
real dev-DB `loaddataset` run) was held pending explicit approval,
consistent with the ask-first boundary from 2a — the interactive
prompt for this decision (dev-DB write vs. tests-only vs. throwaway-
DB) is itself a good sign the boundary is being actively respected,
not just remembered as a rule. A dry run confirmed 3,000 customers
updating in place, 3,000 policies created, zero refusals; SC-003/
SC-004 performance was independently verified at full 3,000-policy
volume on the test database (single retrieve `0.276s`, filtered list
`0.048s`, both comfortably under their bounds).

### 4.6 Final verified state

```
669 passed, 0 failed, 99% coverage (1023 statements, 10 missed)
```
Independently re-confirmed via a fresh upload, not accepted on the
completion summary alone — matching exactly. Customer's 22 audit
tests separately re-confirmed passing (`22 passed, 0 failed`) after
the `Http404` fix. 84 of 85 tasks complete (`T083`, the real dev-DB
load, correctly left pending your explicit go-ahead). Committed as
`321829e` (33 files, 6,511 insertions), pushed. Two scratch
verification-output files were caught before commit and excluded via
a new `.gitignore` pattern, keeping the same discipline from Phase
2a's CSV-exposure catch.

---

## 5. Phase 2c — Claims Management (complete)

### 5.1 What it delivers

Real `Claim` model and CRUD API (`apps/claims/`), replacing Phase 1's
placeholder. FK to `apps.policies.Policy`. Fields: `claim_status`
(Approved/Denied/Filed), `claim_amount_usd`. Audit logging via the
existing `audit_routes.py` registry — this sub-phase is the intended
proof that Phase 2b's high-risk refactor actually paid off (a new
consumer as a data-entry addition, not new refactor work).

### 5.2 Spec review — a real dataset-modeling problem, found and resolved correctly

Before writing began, a genuine data-modeling issue was surfaced and
independently verified rather than assumed away: `Claim_Status`
includes `"No Claim"` on 754 of 3,000 rows — the *absence* of a
claim, not a claim with a status. Storing these as `Claim` rows would
mean 754 records asserting a claim exists whose own status denies it,
corrupting every downstream count for Phases 3-4. Resolved by
representing absence as the absence of a record (`FR-004`/`FR-012`) —
the load produces 2,246 real claims from 3,000 rows, and a skipped row
is a legitimate, correctly-reported outcome, not a refusal.

**A harder, genuinely ambiguous sub-problem surfaced within that**:
390 of the 754 `"No Claim"` rows carry a **non-zero** claim amount —
independently verified: min `$8.52`, max `$19,919.13` (the first
figure offered, `$19,438.61`, was independently checked and found
wrong by exact value, though it does correspond to a real row, ranked
13th rather than highest — corrected before the spec was finalized).
The chosen resolution — treat status as authoritative, don't fabricate
390 claim events an authoritative field explicitly denies — is sound.
**What makes this entry worth recording is what happened next**: the
first proposal for handling this (log the discarded mismatches via
`audit_routes.py`) was reconsidered and replaced with something
better, for a real reason — `audit_routes.py` is a request-scoped
refusal-auditing mechanism (prefix → role sets), with no request, path,
or actor to key a load-time event on, and critically, an append-only
audit log would accumulate a **fresh duplicate entry every single
loader re-run**, inflating a future mismatch count by the number of
loads rather than reflecting the true number of anomalous rows. The
actual design (`FR-041`-`FR-048`, a dedicated, reconcilable
load-anomaly record plus a separate immutable audit entry for
permanent history) avoids both problems this project's own established
philosophy this session would otherwise have walked into.

**A further refinement, requested and correctly delivered**: whether a
later load's *silence* about a previously-flagged row (the row simply
no longer appearing) should count as the mismatch being resolved. The
distinction matters — *"the conflict was neither observed to persist
nor observed to be resolved, and the cause is unknown"* — and the spec
now (`FR-044a`/`FR-044b`) explicitly forbids representing an
absent-cleared anomaly as a *confirmed* correction anywhere queryable,
and requires re-flagging it if the row later reappears still
conflicting, rather than letting a single non-observing run
permanently "win" against future evidence.

Both spec and plan independently reviewed and verified via file
upload (all dataset figures cross-checked against the real CSV a
second time, both correct); committed as `241af14`, `.specify/
feature.json` follow-up as a small separate commit.

### 5.3 A significant infrastructure incident, mid-review — full account

While reviewing Claims' `plan.md`/`research.md`, the baseline pytest
check (part of the new pre-flight habit from §2) reported `web` as
not running. What followed was a real, multi-stage infrastructure
failure, not a routine restart — worth the full account, including a
mistake made along the way, since this episode also resolves an
open question from much earlier in this project.

**Stage 1 — apparent total data loss.** `docker compose ps` and
`docker volume ls` both returned completely empty — no containers, no
volumes, for this project *or any other project on the machine*.

**Stage 2 — a wrong diagnosis, corrected quickly.** The active Docker
context was `default`; `desktop-linux` was assumed to be the "real"
one and switched to — which then crashed with `"protocol not
available"` and a Go-level segfault. This was **wrong**: `default` was
actually correct all along, the empty results were caused by Docker
Desktop itself being disconnected from WSL, not a context mismatch.
Corrected once `docker ps -a` (the simplest possible check, tried
after the more complex ones failed) showed real containers again
after Docker Desktop was restarted from the Windows side.

**Stage 3 — the actual root cause, uncovered by chance.** With
containers back, `web` failed to bind port 8000: `"address already in
use."` Direct investigation (`lsof -i :8000`) found the real
occupant: **`splunkd`, a local security/monitoring process running as
root on this exact machine, on this exact port.** This retroactively
and definitively resolves the `Server: Splunkd` / `303 See Other`
anomaly this project first hit in Phase 1 and had explicitly
documented as **"closed"** — attributed at the time to unfixable
host-network interception, unreachable from inside this project.
**That conclusion was wrong.** It was never network-level
interception; it was this literal local process squatting on the same
port Django uses, every time something else wasn't already bound to
it first. Fixed pragmatically by remapping the host port
(`8000:8000` → `8001:8000` in `docker-compose.yml`) rather than
touching `splunkd` itself, since it could plausibly be an IT-managed
security agent and stopping it without knowing that for certain would
have been the wrong call.

**Stage 4 — real, confirmed data loss.** Once `web` could finally
start, `customers_customer`/`policies_policy`/`audit_auditlog` all
returned zero rows despite the schema being fully migrated. Checked
`docker volume inspect insurance-ai-platform_postgres_data` directly:
`CreatedAt: 2026-08-13T14:56:56-07:00` — **today**, during this
exact incident, not the volume that had persisted since Phase 1.

**A mistake made and corrected in real time, worth recording
honestly**: on first seeing dozens of other unrelated project volumes
still present on the machine, this was reasoned as *"nothing was
purged"* and offered as reassurance that the data was probably intact.
**That reasoning was wrong** — a single project's volume being
recreated is entirely consistent with every *other* volume surviving
untouched; the two facts don't actually connect the way the
reassurance implied. The mistake was caught by checking the volume's
own timestamp directly rather than trusting the inference, and
corrected explicitly rather than left standing. This is the same
"verify, don't trust — including your own reasoning" standard this
runbook has held Claude Code to throughout §3-4, applied here to this
document's own author instead.

**Recovery — genuinely excellent, worth the same standard of praise
as any other strong result in this project.** With explicit
permission (the ask-first dev-database boundary from §2, working
exactly as designed — the loader run and the subsequent superuser
creation were each separately confirmed before proceeding), the
recovery was executed and verified to an unusually high standard:
- Pre-load state independently confirmed as genuinely zero (not
  assumed from the report) before writing anything
- Loader's self-reported counts (`3,000`/`3,000`/`0` refusals)
  cross-checked against real `psql` queries, the CSV's own row count
  (confirming nothing silently dropped), FK integrity (zero orphan
  policies), and the audit log's actual entry count and shape
- The restore verified through the **full stack**, not just the
  database — a real authenticated API session, comparing `CL-00001`'s
  complete field set (name, email, phone, age, gender, location,
  policy type, both dates, premium, risk/renewal scores, fraud flag,
  cross-sell score, lead source) directly against the source CSV row,
  every field matching exactly
- `accounts_user` correctly identified as still empty and *not*
  silently populated — flagged as a real, structural gap (the
  entrypoint never created a superuser, so this exact lockout would
  recur on any future volume loss) rather than worked around ad hoc

**The resulting fix** — an opt-in, idempotent superuser bootstrap
added to `scripts/entrypoint.sh` — was itself independently verified
before commit: the real diff read directly (not the summary alone),
confirming the `${VAR:-}` defaults correctly prevent a `set -u`
crash on an unset variable, the idempotency check correctly matches
`UserManager._create_user`'s email-lowercasing behavior (tested
explicitly with a mixed-case email), and the actual crash-loop
scenario it prevents was empirically measured (`CommandError: Error:
That email is already taken`, exit code 1, which under `set -euo
pipefail` would abort the boot before `exec gunicorn`), not just
theorized. The plaintext-password-in-`.env` limitation was disclosed
unprompted, correctly scoped as local-dev-only.

An unrelated manual change (`docker-compose.yml`'s port remap) was
caught sitting in the same working tree and correctly identified
before being folded into an accurate combined commit rather than
either silently included with a misleading message or silently
dropped.

**Final state**: `insurance-ai-platform_postgres_data` now holds a
freshly-restored, fully-verified `3,000`/`3,000` dataset (the
audit-trail history accumulated across Phases 1-2b is genuinely and
permanently lost — never committed to git, as it correctly shouldn't
be, and only ever existed in the volume that was destroyed). Committed
as `0c80ae3`.

### 5.4 Implementation — a genuinely excellent close, after two real interruptions worth documenting honestly

**Two API-level interruptions occurred mid-session**, unrelated to the
implementation itself — a 500-error mid-session (recovered cleanly by
resuming with explicit confirmation of what had and hadn't landed
before continuing, rather than restarting blind), and, separately, a
recurrence of auto-approve mode being active at the start of a new
session despite having been fixed before, caught and corrected before
any writes happened under it.

**Two genuine gaps slipped past completion summaries in this same
implementation run, both caught by direct verification rather than
trust**:
1. **`T060`** (the single-line registry registration for Claims) was
   reported as part of a larger batch of finished work on two separate
   occasions without actually having happened — confirmed both times
   via a direct, empty `git diff apps/core/audit_routes.py`, not
   accepted from the summary. On the third attempt, genuinely done,
   with the registry entry's own reasoning worth noting specifically:
   *"an Underwriter may WRITE policies but may not READ claims, so
   their 404 on a claim is a REFUSAL while the same user's 404 on a
   policy is an ordinary miss. Only per-module role sets can tell
   those apart"* — the exact subtlety the whole registry design exists
   to capture, stated as the reason this entry needed care, not left
   implicit.
2. **A load approved but never executed.** `"yes, go ahead and run the
   load"` was sent and accepted, but the dev database still showed
   `0` claims and `0` anomalies afterward. Traced directly:
   `docker compose logs web` showed only migration output, no trace
   of the load itself — confirming the command genuinely never ran,
   not that it ran and failed silently. Re-issued explicitly, and this
   time genuinely executed.

**Once actually run, this load is the best-verified single result in
the entire project — worth real, specific praise.** Every number was
independently *derived* from the raw CSV rather than trusted from the
spec (`source rows: 3000 | No Claim: 754 | ...amount≠0: 390 |
...amount=0: 364`, cross-checked against a real checksum:
`2246 + 364 + 390 = 3000`), confirmed against the live database rather
than the command's own self-report, and — critically — **idempotency
was empirically demonstrated, not asserted**: the load was run a
*second* time and the audit trail was inspected directly, showing
`claim_anomaly.recorded` staying at exactly `390` rather than doubling
to `780` — *"Had anomalies lived in the append-only log instead of a
reconciled table, this would now read 780 and a Phase 4 count would be
wrong by the number of times the loader had run. That was the
design's central argument, now demonstrated rather than asserted."*
This directly closes the loop on the reasoning first worked through
during spec review (§5.2) — a design decision that was sound on paper
now has a real, repeatable proof behind it.

**The registry investment's payoff, proven with a literal byte-level
diff.** *"`exception_handlers.py` byte-identical to the T003 baseline
(`2d3d84dc`), the entire refusal-auditing change being one 37-line
`register()` block."* This is the concrete answer to the question this
whole sub-phase was partly designed to test: did Phase 2b's
high-risk, shipped-code-touching refactor actually pay off as
intended, or would Claims need its own workaround. It held, exactly
as designed, provable rather than just claimed.

**One design question surfaced and resolved deliberately, not
defaulted**: whether the source CSV should be baked into the Docker
image (via `COPY . /app`) or kept out entirely. Resolved correctly —
excluded from the image via `.dockerignore`, reachable only through a
read-only runtime bind mount (`./data:/app/data:ro`) instead,
consistent with this project's established caution about that
specific file's exposure. One real gap in the first implementation
(the `.dockerignore` comment described a mount that didn't yet exist
in `docker-compose.yml`) was caught by direct verification before
being trusted, then genuinely fixed.

**Two real regressions in *other* apps' tests, found and correctly
diagnosed as stale tests, not defects**: `test_audit_routes.py` used
`/api/claims/1/` as its example of an *unregistered* path — true in
Phase 2b, false now that Claims is registered; fixed by swapping the
example to an actually-still-unregistered path. `test_loaddataset.py`'s
cleanup logic started raising `ProtectedError` once policies could
carry claims — correctly identified as `FR-009`'s `PROTECT` constraint
working exactly as specified, not a bug, and fixed by reordering the
cleanup to respect the new dependency chain.

**Final verified state**, independently confirmed via direct
database and full-suite queries, not accepted from the completion
summary:
```
customers: 3000  policies: 3000  claims: 2246  anomalies: 390
842 passed, 0 failed, 99% coverage
```
All 74 tasks complete. Committed as `a947a9f` (23 files, 3,788
insertions), pushed.

---

## 6. Phase 2 — complete

**Customer, Policy, and Claims are all real** — three full CRUD
modules, replacing every Phase 1 placeholder, sharing one RBAC
mechanism, one audit-refusal registry, one archival pattern, and one
CSV-driven seed loader across all three. 228 tasks total across the
three sub-specs (69 + 85 + 74), all complete, all independently
verified rather than taken on any single completion summary's word.

**Six real, distinct bugs found across this phase**, every one of
them only surfacing through actual execution — a real request, a real
cascade, a real re-run, a real infrastructure failure — never through
however-careful a static read:
1. A DRF permission-dispatch ordering bug (2a) — `has_permission`
   blocking a detail-route request before `has_object_permission`'s
   404 logic could ever run
2. An audit-trigger/`SET_NULL`-cascade interaction bug (2a) — two
   independently-correct mechanisms, never tested together
3. An unbounded-hang database timeout bug (2a, technically found
   during US4 but part of the same overall project arc)
4. A stale-container-image false-positive baseline (2b) — a clean
   `389`-passing run against code that didn't exist in the image
5. An `FR-015` validator-ordering bug and an `FR-031` gap latent since
   2a (`Http404` vs. `NotFound`) — both found and fixed in 2b
6. Two stale-test regressions correctly diagnosed as the *system*
   working as specified, not as bugs (2c)

**One genuine infrastructure crisis, fully resolved and honestly
documented** — a Docker Desktop connectivity failure that led to real
data loss, one incorrect reassurance caught and corrected in real
time, and a definitive retroactive correction to a much older,
previously "closed" conclusion (`Server: Splunkd` was never network
interference — a local process on this machine, the whole time).

**The throughline holds across all three sub-phases**: static review,
however careful, keeps finding real limits. Only actually running the
system — against a real database, a real cascade, a real re-run, a
real infrastructure failure — has ever been sufficient to prove
something works. That was true in Phase 1, and every one of Phase 2's
six bugs confirms it again.

---

## 7. Progress log

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

**2026-08-10** — Phase 2b (Policy Management) complete. Spec/plan
review found two genuinely sharp, independently-verified design
decisions: live-scoped `(customer, policy_type)` uniqueness correctly
identified as needing the *opposite* semantics from Customer's
reference-reservation pattern, and an archived-customer FK-resolution
bug caught before it could exist. Implementation surfaced three real
bugs: a falsely-green baseline from a stale, never-rebuilt container
image (coverage table was the tell, not the pass/fail line — now a
new standing rule); an FR-015 message-contract violation from DRF's
auto-generated `UniqueTogetherValidator` firing before the explicit
check; and an FR-031 gap latent since Phase 2a (`Http404` not `NotFound`
from `get_object_or_404`, undetected because Customer's own tests
never exercised the unpermitted-user-plus-nonexistent-id case) —
fixed in the shared handler with Customer's 22 audit tests re-confirmed
passing afterward. The high-risk refusal-handler-to-registry refactor
(flagged in its own plan as touching shipped, tested code) landed with
a zero-line diff on the Customer audit test file. A real cross-session
question — whether earlier Customer-phase verification was also
against a stale image — was resolved directly using evidence available
at review time (live Customer test IDs and real coverage numbers in
that earlier output rule it out) rather than left open or guessed at.
`T083` (the real dev-DB load) correctly deferred pending explicit
approval, consistent with the 2a boundary. Final: 669/669 tests
passing, 99% coverage, 84/85 tasks complete. Committed as `321829e`,
pushed.

**2026-08-12 to 2026-08-14** — Phase 2c (Claims) spec and plan
complete. Spec review caught a real dataset-modeling problem
(`"No Claim"` status rows must not become fabricated Claim records)
and a harder ambiguous sub-case (390 status/amount mismatches) —
resolved with a design that improved on the first proposal after
correctly identifying that an append-only audit log would inflate
mismatch counts by the number of loader re-runs; refined further on
request to distinguish "confirmed corrected" from "silently absent"
so a future query can't conflate the two. Both dataset figures in the
spec's Assumptions section independently re-verified against the raw
CSV, one initially-wrong figure caught and corrected before finalizing.
Mid-review, a significant infrastructure incident occurred: Docker
Desktop's WSL connection broke, was misdiagnosed once (a Docker
context switch, wrongly assumed to be the fix, that actually crashed)
before being correctly resolved via a Docker Desktop restart; a real
port conflict was then traced to a local `splunkd` process on port
8000 - which retroactively and definitively corrects Phase 1's
"closed" conclusion about the `Server: Splunkd` anomaly, which was
never network interference at all. The project's Postgres volume was
confirmed genuinely recreated (not just disconnected) via its own
`CreatedAt` timestamp, after an incorrect reassurance ("other volumes
survived, so probably nothing was purged") was offered and then
self-corrected once actually checked - logged as a new standing rule
alongside the real `splunkd` finding. Recovery was executed to a high
standard: pre/post state independently verified at the database,
CSV-source, and full-authenticated-API level (a real CL-00001
field-by-field match against the source row), and a genuine structural
gap (no superuser bootstrap existed, meaning any future volume loss
would repeat the same lockout) was found and fixed with an opt-in,
idempotent, empirically-tested entrypoint change rather than worked
around ad hoc. Committed as `0c80ae3`. Claims implementation not yet
started.

**2026-08-15 — Phase 2 complete.** Claims implementation finished, 74
tasks. Two real interruptions along the way: an unrelated API 500
error mid-session (recovered by confirming actual state before
resuming, not restarting blind), and auto-approve mode recurring at a
new session's start (caught and fixed before any writes happened
under it). Two genuine gaps slipped past completion summaries within
this same run before being caught by direct verification: `T060`
(registry registration) reported done twice without having happened,
confirmed both times via an empty `git diff`; a dataset load reported
as executed that had, per `docker compose logs`, never actually run.
Once genuinely executed, the load became the best-verified single
result in the project - every figure independently derived from the
raw CSV with a real checksum, and idempotency empirically proven (not
asserted) via a real second run showing the anomaly audit count held
at 390 rather than doubling. The Phase 2b registry investment's payoff
was proven with a literal byte-identical diff on `exception_handlers.py`
- the entire Claims audit integration was one 37-line addition, exactly
as designed. A real design question (bake the CSV into the Docker
image or mount it at runtime) was resolved correctly - excluded from
the image, reachable only via a read-only bind mount - after one
implementation gap in that fix was caught and corrected. Two
regressions in unrelated apps' tests were correctly diagnosed as stale
tests reacting to the system now working as specified, not as bugs.
Final: customers 3000, policies 3000, claims 2246, anomalies 390,
842/842 tests passing, 99% coverage. Committed as `a947a9f`, pushed.
**Phase 2 (Core Domain) is fully complete** - Customer, Policy, and
Claims all real, 228 tasks total across three sub-specs, six real bugs
found across the whole phase, one full infrastructure crisis
encountered and honestly resolved along the way.
