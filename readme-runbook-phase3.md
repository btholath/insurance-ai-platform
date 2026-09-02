# Runbook — Phase 3 (Risk Engine)

**Companion to `readme-runbook-phase1.md`** (Spec Kit methodology, the
beginner glossary, the full `/speckit-*` workflow explanation) and
`readme-runbook-phase2.md` (the Core Domain phase — Customer, Policy,
Claims — including six real bugs and a full infrastructure-loss
incident). This document assumes both and focuses on what's specific
to Phase 3.

**Living document**, same convention as Phases 1-2 — sections marked
`⏳ PENDING` are placeholders, filled in with real content as each
sub-phase actually happens.

---

## 1. Scope and sequencing

| Sub-phase | Status | Depends on |
|---|---|---|
| **3a — Risk Scoring Engine** | ✅ Complete | Phase 2 (Customer/Policy/Claims all real) |
| **3b — Automatic Recompute (Celery)** | ✅ Complete | 3a |

Split deliberately, mirroring Phase 2's Customer→Policy→Claims
sequencing logic: get the scoring domain logic solid and fully tested
**on-demand only** first, then layer the harder infrastructure
question (introducing Celery for the first time — Redis has sat
provisioned-but-unused since Phase 1's Foundational plan explicitly
deferred it) on top of something already proven, rather than
debugging both at once.

**Scope decided before writing began**, via explicit questions rather
than defaulted: the score is a **tiered/thresholded rules engine**,
not a black-box calculation; it's exposed via a **dedicated
explainability endpoint** (`GET /api/customers/{id}/risk-assessment/`),
not just an updated field; and recompute is **on-demand only** in 3a
(a management command / explicit API trigger) — no signals, no Celery,
no automatic triggering on data changes until 3b.

---

## 2. Standing rules — carried forward from Phases 1-2, plus new ones from 3a

### Pre-flight checklist — run at the start of every session, before any `/speckit-*` command

```bash
cd ~/insurance-ai-platform
git status
docker compose build web
docker compose up -d
docker compose ps
docker compose exec web pytest apps/ tests/ -v --cov-report=term-missing 2>&1 | tail -10
```
Then inside Claude Code:
```
/status
/model
```
Confirm `⏸ manual mode on`. **New for 3a**: also check `/config` for
`"Use auto mode during plan"` — see below, this is a real, separate
risk from the manual/auto toggle already checked.

**From Phase 1** (still in force): pause before approving every
write; verify real files/commands rather than trust completion
summaries; confirm manual/pause mode before starting work.

**From Phase 2**: a passing test run proves nothing if the container
image is stale — verify via the coverage table, not the pass line. A
Docker volume's survival can't be inferred from other volumes'
survival — check its own `CreatedAt` timestamp directly. The
`Server: Splunkd` anomaly was a local process on port 8000, not
network interference — if it recurs, check `lsof -i :8000` first.

**New, established during 3a**:

- **A Claude Code settings entry — `"Use auto mode during plan"`
  (visible via `/config`) — auto-approves writes during
  plan-classified operations regardless of the overall manual/auto
  mode toggle shown in the status bar.** This is a real, separate risk
  from the `⏸ manual mode on` / `⏵⏵ accept edits on` toggle already
  tracked — the status bar can correctly show manual mode active for
  the *session*, while this setting silently lets *plan-classified*
  writes (which `/speckit-specify`/`/speckit-plan` writes plausibly
  fall under) through without an actual pause. Check `/config` and
  turn this off, or at minimum know it's on, before trusting that a
  spec/plan write was actually reviewed rather than auto-approved.
- **A brand-new "Set up auto mode" onboarding prompt can appear
  mid-session** (distinct from the setting above) and, if accepted or
  even just navigated past carelessly, can flip the status bar
  straight to `⏵⏵ auto mode on`. If this prompt appears, select
  **"Not now"** — not "Don't show again" — so the option to
  reconsider later stays available without silencing something worth
  revisiting once the project is in a calmer state. Then immediately
  `shift+tab` to confirm manual mode is genuinely restored.
- **Verify a claimed instruction or premise before acting on it — a
  discipline that applies to instructions from either side of the
  conversation, not only to completion summaries.** During 3a, an
  instruction stating "FR-005 confirms the scale is 0-100" was
  **wrong** — the actual spec text only requires a fixed, stated,
  bounded scale, no specific number. Claude Code correctly asked to
  re-read the spec before editing anything on that premise, catching
  the error before a costly, unnecessary fix (raising a point value,
  invalidating the entire 3,000-row validation) was applied to satisfy
  a mistaken instruction. Worth remembering symmetrically: the "verify
  before trusting" standard protects against bad instructions, not
  only bad summaries.
- **A live source bind-mount (`.:/app`) was added to `docker-compose.yml`
  in 3a**, likely closing the Phase 2b stale-image failure class
  permanently — code edits are now visible to the running container
  immediately, without a rebuild. This changes what `docker compose
  build web` actually verifies going forward: no longer primarily "is
  the container seeing current code" (the mount already guarantees
  that), but "does the deployable image itself match" — relevant for
  dependency changes (`pyproject.toml`) or confirming what would ship
  if deployed standalone. The image still `COPY`s the source
  independently, so a deploy from the image alone remains
  self-contained; the mount only shadows it in dev.

**New, established during 3b**:

- **Claude Code's own recap/summary mechanism (shown in the status bar
  or as a scheduled "wakeup" message) can surface stale or duplicate
  content and should never be trusted over direct verification.**
  During 3b this happened repeatedly — a stale recap claiming Phase 2b
  was still in progress; a scheduled `/loop wakeup` firing after work
  was already done and committed; the same terminal transcript
  re-uploaded multiple times across real minutes/hours apart. Every
  instance was resolved the same way: check `git log`/`git status`
  directly rather than trust the recap's framing of "what's currently
  true."
- **A single terminal window can genuinely hang (three consecutive
  git commands returning zero output, not even an error) without any
  actual repository damage.** Confirmed during 3b's final wrap-up:
  the correct response is to close that window and open a completely
  fresh one, `cd` back into the project, and re-run the check there —
  not to keep re-querying a frozen shell or assume the worst about
  repository state based on a display problem. A `git push`'s own
  real-time confirmation from GitHub (the `remote:`/`... -> main`
  lines) is independent, external proof work is safe, regardless of
  what a later, unrelated terminal glitch might suggest.
- **If a completion summary in an already-pushed commit message turns
  out to be wrong or incomplete, correct it with a new, honest commit
  — don't rewrite history to hide it.** `2ffc0d1`'s own commit message
  credited the `3001`-vs-`3000` count discrepancy entirely to a
  3-week-old `CustomerFactory`-sequence artifact — true but
  incomplete, and on its own insufficient to explain the discrepancy.
  Once the real, fuller cause was found (see §5's Phase 3b entry),
  rather than `commit --amend` (which would have silently altered
  already-shared history) or leave the inaccurate explanation
  standing, commit `ca2f72d` stated plainly what the original message
  got wrong and why, preserving an honest, if imperfect, record —
  consistent with this entire runbook's own standard for its authors,
  now demonstrated by Claude Code applying it to its own git history
  too.

---

## 3. Phase 3a — Risk Scoring Engine (complete)

### 3.1 What it delivers

A rules-based risk scoring system for `Customer`, replacing the
currently-unused, storage-only `risk_score` field established in
Phase 2a. The first phase where **constitution Principle IV
(Explainable AI Outputs)** actually applies — Phase 1's plan
explicitly marked it N/A, since no AI/scoring surface existed until
now. Every score is a tiered result from a declarative, pure-function
rule table (`apps/risk/rules.py`), explainable via a dedicated
read endpoint, computed on-demand only in this sub-phase.

### 3.2 Spec review — real evidentiary rigor, including two ethically-aware decisions

Before writing began, every candidate scoring factor was checked
against the real 3,000-customer seeded database, not assumed usable:

- **`gender` excluded on both statistical and ethical grounds** —
  near-uniform distribution (no discriminatory power) **and**
  explicitly disqualified as a protected characteristic regardless of
  what the statistics showed. The ordering matters: this wasn't
  "we measured it and it happened to be useless," it was "this must
  never be used, independent of measurement." Independently verified
  against the raw CSV: `1,042/998/960` — genuinely near-uniform.
- **The existing `risk_score` field (from the Phase 0 CSV / Phase 2a
  storage) was proven to be noise before being replaced, not just
  asserted useless.** Independently verified: only 91 distinct values
  across 3,000 rows, near-zero correlation with age (`0.0018`) and
  premium (`0.0179`), and a flat mean across all three fraud-flag
  bands (`~0.54` regardless of Low/Medium/High). `FR-055` cites this
  evidence directly rather than a bare assertion.
- **Zero-amount claims (1,143 of 2,246 real claims) correctly
  identified as needing their own distinct treatment** — not "no
  claim," not "a claim of substance." Independently verified count
  matches exactly.
- **A tier-distribution simulation was run in SQL against all 3,000
  real customers before committing to SC-005's "every tier holds
  ≥5%" claim** — `33.4%/32.0%/16.9%/17.7%`, proving the success
  criterion achievable before it became a testable commitment, not
  after.
- **A deliberate explainability design choice**: `FR-021` requires
  factor contributions to sum exactly to the total score (a testable
  mathematical invariant), and `FR-024` requires explanations to come
  from a *persisted* factor record at computation time, never
  reconstructed later from possibly-since-changed data. This mirrors
  the same "don't let history be reconstructed from present-day data"
  principle behind Phase 1's `actor_role` audit snapshot and Claims'
  corrected-vs-absent anomaly distinction.
- **A staleness-disclosure judgment call, flagged explicitly rather
  than silently decided**: since scoring is on-demand-only in 3a, a
  stored score can go stale as underlying Policy/Claims data changes.
  Rather than sweep this under the rug, User Story 5 and `FR-038`-
  `FR-040` were built to *disclose* staleness rather than let it
  become an undisclosed defect — offered as a trimmable option, not
  forced. **Kept, deliberately** — trimming it would have left a real
  gap in the same explainability guarantee `FR-021`/`FR-024` were
  built to provide from the other side.

### 3.3 Analyze findings — one constitutional-weight bug caught before any code existed

Three findings reviewed in full before approving any remediation,
same discipline as every prior `/speckit-analyze` pass this project:

**D1 (HIGH, constitutional)** — the sole write path for scores
(`engine.persist()`) was scheduled for `T033` (Phase 3, User Story 1),
but the `record_action` audit call for that same write was scheduled
eight phases later, at `T078` (Phase 8, User Story 4). Between those
two points, every real score computation would have written risk data
with **no audit entry** — a direct violation of constitution
Principle II. The finding's own sharpest observation: `tasks.md`'s own
Phase 4 checkpoint claimed *"US1 + US6 together are the minimum
defensible increment"* — a claim the gap itself made false. **Fixed**:
`record_action` moved into `T033`'s existing `transaction.atomic()`
block (which `FR-053` already required it to share); `T078` retargeted
from *introducing* the audit write to *verifying* it; the checkpoint
claim corrected to state plainly that all three principles hold at
that point, not overstated.

**C1 (MEDIUM)** — `SC-005`'s tier-distribution claim ("every tier
holds ≥5%") had no automated assertion, reachable only via a manual
quickstart step. *"A rule change that collapsed 90% of customers into
one tier would pass every automated test in the suite."* **Fixed**: a
dedicated distribution assertion added to `T058`.

**C2 (MEDIUM, treated as higher-stakes than its label)** — `FR-017`
(forbidding gender/location as scoring factors) had zero task
coverage — a `grep` for the excluded fields across all 99 tasks
returned nothing. *"Nothing prevents a later contributor adding a
gender band... the real reason [gender is excluded] is that it
shouldn't be there at all."* **Fixed**, per explicit instruction to
use hard equality rather than a mere absence check: `T011a`, a
standalone task asserting `set(rules.FACTORS) ==` the exact five
approved factors — catching both an unapproved addition *and* a
silent removal (explicitly protecting `claims_ratio`, named as "the
most discriminating factor," from being silently dropped later).

All three remediations verified directly in the real `tasks.md` file
after being applied, not accepted from the completion summary.
Task count: 99 → 100. Committed as `8f1f8b4` (spec, plan, research,
data-model, tasks, contracts, checklists — no application code).

### 3.4 Implementation — a real interruption, a real bug found and correctly resolved, and a real infrastructure fix

**The implementation session was interrupted mid-flight** by an
unrelated API 500 error, and separately hit real turbulence: a
"Set up auto mode" onboarding prompt appeared and was correctly
declined ("Not now," not "Don't show again"); the session's own recap
mechanism twice surfaced a stale, unrelated Phase 2b summary,
correctly identified as stale by cross-checking against real
`git status` output rather than trusted. When work resumed,
`apps/risk/` was found genuinely mid-scaffold — every test file empty
except `test_rules.py` (already written), and `rules.py` itself
missing entirely, explaining a collection error that had briefly been
mis-attributed to a stale-container-image question (the same category
of issue from Phase 2b, but not what was actually happening this
time — confirmed by checking the real file state directly rather than
re-investigating the old, already-resolved question).

**A real, self-caught arithmetic error, correctly root-caused and
correctly *not* over-corrected.** While verifying `rules.py`, the
band-point maxima were found to sum to `90` (`15+15+20+30+10`), while
two docstrings claimed `100`. This was flagged as a genuine spec
question, not resolved unilaterally. **A wrong instruction from this
runbook's own author was caught in the process**: told "FR-005
confirms the scale is 0-100," Claude Code correctly declined to act on
that without re-reading the actual spec text first — and FR-005, read
directly, only requires a fixed, stated, bounded scale, no specific
number mandated. The error was owned and corrected in the same
message it was caught in, not left standing.

With the premise corrected, the actual fix was properly scoped: the
**real, working, independently-verified table sums to 90** — so `90`
is the true scale, and the two wrong docstrings were fixed to match
the code, not the other way around. The alternative (raising a factor
value to reach a true 100) was correctly identified as carrying real,
unwarranted cost — invalidating the entire 3,000-row validation, every
number in the tier-distribution table, and requiring a `RULE_SET_VERSION`
bump per `FR-004` — *"a real behavioral change bought to satisfy a
typo."* Fixed: `research.md` §5 (two lines), `rules.py`'s module and
`max_score()` docstrings, and `TIER_BANDS`' comment (left at 100 to
match the DB constraint, explicitly noted as inert headroom rather
than a real gap). No point value changed. `RULE_SET_VERSION` stays
`1.0.0`. The 3,000-row validation stands as originally measured.

**One consequence correctly caught in a second pass**: `T011`'s own
test-score list still included `100` as if it were a real,
reachable value, when it's now known-unreachable under the corrected
scale. Amended to include both `90` (the real reachable maximum) and
`100` (the DB constraint envelope), with each labeled for *why* it's
in the list — and, on top of the literal request, a self-updating
assertion (`tier_for(max_score()) == "high"`) rather than a hardcoded
`90`, so the test tracks the table automatically if the scale ever
does move in the future via the recorded `claims_history` 20→30 path.

**A second self-caught gap, one level deeper**: the *original* test
that surfaced this whole discrepancy (`test_max_score_is_the_sum_of_
every_factor_maximum`) still hardcoded `== 100` after everything else
was fixed — the one place the bug started was the one place not yet
corrected. Caught by actually re-running the test suite rather than
assuming the fix was complete once the code and docs agreed
(`1 failed, 52 passed`, then fixed and re-verified to `54 passed`).

**Final state as of this entry**: `apps/risk/rules.py` (the band
table, tier logic, `max_score()`) is done, verified, `54/54` tests
passing. Everything else in `apps/risk/` — models, serializers, views,
the engine itself, permissions, audit integration, the `computerisk`
management command, staleness handling — confirmed still empty stubs,
genuinely all of `T012` onward still ahead. Committed as `e1f15bd`
(22 files: the full `apps/risk/` scaffold, `config/settings/base.py`,
`config/urls.py` registering `/api/risk/` as a **top-level** prefix
— deliberately not nested under `/api/customers/`, to avoid
misattribution in the `audit_routes.py` registry — and the
`docker-compose.yml` bind-mount change documented in §2).

### 3.5 Implementation completion — six commits, a real self-caught investigation, and a genuine process gap

**Six clean, well-organized commits** carried the remaining implementation
from `T012` through `T099`, each mapped to a specific User Story range
rather than one large undifferentiated dump:

```
e1f15bd  T001-T014  apps/risk/ scaffold + rules.py (documented in §3.4)
f32dfe7  T015-T023  RiskAssessment and RiskFactor models
e01db27  T024-T039  User Story 1 — explainable risk assessments
4a639ca  T040-T048  User Story 6 — roles enforced on every risk operation
5df6622  T049-T059  User Story 2 — computerisk batch command
f3ed49e  T060-T071  User Story 3 (recompute) and User Story 5 (staleness)
cbe8624  T072-T083  User Story 4 — the audit trail, registry's 4th entry
```

**`T033` (the D1 audit-sequencing fix) and `T011a` (the factor-set
equality assertion) were independently re-verified against real source
lines, not accepted from a summary** — `engine.py:79-129` confirmed as
one unbroken `transaction.atomic()` block with `record_action()` as its
final statement, and `test_rules.py`'s `assert set(rules.FACTORS) ==
APPROVED_FACTORS` confirmed as a genuine hard equality, not a
containment check.

**A real process gap, caught and corrected rather than papered over**:
after all six commits landed, `tasks.md` still showed **zero** tasks
checked — the checkbox-tracking discipline that Customer, Policy, and
Claims all maintained throughout their own implementations simply
didn't happen here, despite the work itself being genuinely done. Before
trusting a reconciliation, the file's own timestamp was checked
directly against the commit history to rule out a stale-copy mixup
(`tasks.md` predated every implementation commit, confirming the gap
was real, not a file-mismatch illusion). The reconciliation itself was
done non-bulk — cross-referenced against real git history — and spot-
checked at the `T083`/`T084` boundary before being trusted: `T083`
landed at `[x]`, `T084` at `[ ]`, exactly where the real commit history
said the line should fall.

**Phase 3a's `T084`-`T090` scope: making `Customer.risk_score` a
denormalized mirror, engine-only.** The reasoning is a precise
application of Principle IV, worth restating: *"an API client setting
`risk_score` directly would create a score with no assessment and no
explanation — a black-box score, which Principle IV forbids."* This
required genuinely splitting an existing parametrized test
(`test_score_outside_range_refused`/`test_score_boundaries_accepted`)
that had treated `risk_score` and `cross_sell_score` identically as
writable fields — correctly recognized that a read-only field is
*silently dropped* from `validated_data` rather than validated and
refused, so the old shared test could no longer mean what it used to.

**The full `quickstart.md` (all 10 steps) was executed end-to-end
against real, running dev infrastructure — not just the test suite.**
This included the actual sum invariant across all 3,000 real
assessments (zero mismatches), a real double-run proving idempotency
byte-for-byte, and constructing a genuinely unassessable customer to
confirm the 422/404 paths live, not just in a fixture.

**A real, unrelated discrepancy — investigated properly rather than
hand-waved, on request.** During cleanup, a policy's premium was found
already restored to its correct value *before* the explicit restore
command ran — initially dismissed with *"regardless, it's confirmed
correct."* Pressed to find the actual cause rather than accept the
outcome alone, the investigation went back to the **append-only audit
trail** (not memory, not a guess) and found the real answer: a
`loaddataset` run performed for an unrelated check (verifying
`risk_score` wasn't reimported from the CSV) had, as an undocumented
side effect, silently reconciled *every* CSV-mapped field on that
policy — including `premium_usd`, which had nothing to do with what was
being checked. The two audit entries' distinct shapes (a clean
before/after diff on the intentional test PATCH versus a full-field,
empty-actor snapshot from the loader) were the actual distinguishing
evidence. **The original "regardless" dismissal was explicitly named as
wrong, not quietly corrected**: *"my 'regardless' was wrong to wave
off: it wasn't a benign coincidence, it was a real side effect... I
didn't notice at the time."* Recorded to persistent memory as a
standing lesson: `loaddataset`'s reconciliation is not scoped to
whatever a given run is checking — it silently rewrites every
CSV-mapped field on every row it touches, every time, which matters for
any future manual dev-DB verification work that happens to run the
loader for an unrelated reason while something else is under test.

**Two documentation-only gaps found during the quickstart run were
fixed immediately, not left as findings** — `quickstart.md`'s own
`max_score` expectation still said `100` after the `90`-vs-`100`
correction (§3.4) had already fixed the code and every other doc; and
its `curl`+Token-auth examples didn't match this platform's actual
session-only authentication. Both low-risk, pure-documentation fixes,
correctly judged not worth deferring the way the original scale
decision was.

**Final verified state**, independently confirmed at every number, not
accepted from any single completion summary:
```
100/100 tasks reconciled (verified via grep, not narrated)
1049 passed, 0 failed
100% coverage on every file in apps/risk/ (rules.py, engine.py,
  models.py, serializers.py, views.py, factories.py, urls.py,
  computerisk.py)
99% overall project coverage
3,000 customers confirmed in the dev database after cleanup
```
Committed across `15396ee` (task reconciliation) and `2272284`
(quickstart doc fixes), both pushed. `origin/main` confirmed matching
local `HEAD`.

---

## 4. Phase 3a — complete

**The platform's first genuinely explainable-AI-adjacent capability is
done.** A rules-based risk engine, transparent by construction — every
score traceable to a persisted, factor-level explanation, never
silently recomputed — built on top of everything Phase 1 and Phase 2
proved out (the same `HasRole` mechanism, the same audit-refusal
registry now genuinely proven as a fourth consumer requiring zero
changes to shared code, the same dual-manager archival pattern).

**The throughline holds again.** Every real finding this sub-phase
produced — the `90`-vs-`100` scale bug, the `tasks.md` reconciliation
gap, the `loaddataset` side-effect on an unrelated field — was found by
actually running the system, reading real audit entries, and checking
real file timestamps, not by however-careful a review of intent. The
one moment a plausible-sounding explanation was accepted without that
scrutiny (*"regardless, it's fine"*) was also the one moment briefly
worth correcting once pressed — consistent with every other phase in
this project, including the times this runbook's own author was the
one who needed correcting.

**Next**: Phase 3b (automatic recompute via Celery), the second half of
the original split decision — introducing asynchronous execution for
the first time, on top of an on-demand engine now fully proven.

---

## 5. Phase 3b — Automatic Recompute via Celery (complete)

### 5.1 What it delivers

Every risk assessment now stays current automatically. A `post_save`
signal on Customer, Policy, or Claim enqueues a Celery task
(`recompute_customer_risk`) via `transaction.on_commit()`, which calls
the *exact same* `engine.score_customer()`/`persist()` pair every
existing path (the manual API endpoint, `computerisk`) already used —
this feature adds a trigger, not a second scoring implementation. The
manual on-demand path from 3a remains fully available, unchanged,
protected by its own dedicated regression-safety user story. This is
the first time Celery is actually used in this project, after Redis
sat provisioned-but-idle since Phase 1's Foundational plan explicitly
deferred it.

### 5.2 Spec, plan, and tasks — scoped deliberately before any code existed

Three real design questions were decided explicitly via interactive
Q&A before `/speckit-specify` ran, not defaulted: trigger broadly on
Customer, Policy, *and* Claim changes (matching 3a's own
over-reporting staleness philosophy, rather than fine-grained field
tracking); failed tasks retry with backoff and alert only once
exhausted; and — the one requiring real thought — how to avoid
flooding Celery when `loaddataset` touches all ~3,000 customers/
policies on every run. **The answer chosen: let it flood, deliberately.**
`persist()`'s existing idempotency guarantees correctness regardless of
how many redundant tasks run; efficiency was explicitly named a future
optimization, not required now — a conscious, documented tradeoff, not
an oversight.

**The plan's two sharpest pieces of reasoning**, both independently
verified against the actual codebase before being trusted:
- **`transaction.on_commit()` for the enqueue is the deliberate
  opposite of `apps/audit/services.py`'s "no signals, no on_commit"
  stance** — and the plan states precisely why both are correct: an
  audit write must share its triggering transaction (so a failure
  rolls both back together), while a recompute enqueue must *never* be
  allowed to fail the write that triggered it. Two decisions,
  deliberately opposite, both justified from the same first
  principles.
- **A genuine tension with an already-passing Phase 3a test, named
  rather than silently broken.** Phase 3a's own `test_engine.py`
  asserted *the codebase contains no signal handler at all* —
  something this feature necessarily violates. The plan stated
  directly: *"this is the one point where this feature deliberately
  departs from an explicit prior decision, and that departure needs to
  be named, not smoothed over,"* specifying the correct resolution in
  advance: **revise**, not delete, narrowing the claim to what still
  holds (nothing recomputes *synchronously*).

Two proactive, unprompted task additions (`T043`/`T044`) exist purely
to document *why* signals are used here after being rejected elsewhere
— *"so the next reader doesn't 'fix' this into consistency with the
audit module's convention"* — the same guardrail pattern as Phase 2b's
`T071` (*"fix the per-module entry, never the shared handler"*).

Committed across two commits (`9fa7f74`, `8488da4`) — the second fixing
three small issues found on independent review: `T014`-`T016`'s wording
implying a `ready()` method already existed to "edit" (it didn't, per a
direct `grep` check), and `T029`'s unresolved file-placement hedge.

### 5.3 Implementation — a genuine infinite-recursion bug, and the most important self-correction in this entire project

**A real, production-serious bug, found through patient, honest
debugging under real pressure.** `engine.persist()`'s existing
`Customer.save()` call to mirror the score onto the customer bumped
`updated_at` via `auto_now` — which, once Phase 3b's signal was wired
up, re-fired `post_save` and re-enqueued a recompute of the *same*
customer, which called `persist()` again, which saved again,
recursing without bound. Under Celery's eager test mode this executed
synchronously rather than merely queuing infinitely, hanging the test
suite outright. **Two hypotheses were tested and correctly rejected
before the real cause was found** — a nested-`atomic()` theory,
disproven with a minimal repro; orphaned Postgres locks from repeated
hard-kills of the hung process, a real but secondary consequence, not
the root cause. The actual chain (`persist()` → `save()` → signal →
re-enqueue → `persist()`) was traced via `pg_stat_activity` and
explicit, honest labeling of what was self-inflicted noise versus what
was the real bug.

**The fix — `.update()` instead of `.save()` for the risk-mirror
write — was chosen over a signal-guard/sentinel alternative for a
concurrency reason, not convenience.** A flag suppressing "was this
save triggered from inside `persist()`" is a well-known fragile
pattern under genuinely concurrent Celery workers; `.update()` is
stateless and structurally cannot race. The fix also set
`updated_at`/`computed_at` from the *same* captured timestamp,
eliminating — by construction, not by careful sequencing — the exact
class of bug Phase 3a's own `T033` had once fixed by ordering alone.
Verified via a dedicated re-run of `test_staleness.py` specifically,
confirming the earlier fix's guarantee still held under the new
mechanism (`9c17e5d`).

**The single most valuable finding of this entire multi-week
project**, surfaced while completing `T042` (the test revision the
plan had already committed to): the original `test_no_signal_handler_
or_scheduled_task_touches_risk_scoring` had been **passing for the
wrong reason since it was first written in Phase 3a** — Django 5.1's
`Signal._live_receivers()` returns a 2-tuple of `(sync_receivers,
async_receivers)` lists, and the test's `for receiver in receivers:`
was iterating over that tuple itself, binding `receiver` to a *list*,
never an actual function. `getattr(a_list, "__module__", "")` silently
fell through to `""`, so the assertion was unconditionally true —
**this guard rail could never have failed, no matter what was ever
wired up, throughout the entirety of both Phase 3a and Phase 3b's own
implementation.** Found not by guessing, but by someone actually
reading Django's real return type instead of trusting an inherited
assumption. Fixed with a corrected, properly-unpacked iteration and
two more precise assertions; new paired tests (immediate-unchanged +
eventually-recomputes-via-`on_commit`) now specifically guard against
this exact class of silently-non-functional assertion recurring
(`9e35c80`).

**Two more genuine gaps, both self-caught during close review, not
found by external pressure:**
- `apps/risk/tests/test_no_business_actions.py`'s AST allowlist —
  itself a test *about* which ORM methods production code may call —
  had never been updated to permit `.update()` when the recursion fix
  landed, meaning it should have been failing (or silently not
  covering the new path) since that commit, until caught during
  `T030`'s regression sweep (`7f8d7e6`).
- `scripts/entrypoint.sh` was hardcoded to always launch `gunicorn`,
  ignoring any `command:` override — which would have silently made
  the new `celery-worker` service just run the web server instead of
  a worker. Found and fixed before it could ship unnoticed.

**A `tasks.md` process gap recurred, and was resolved with the same
discipline as Phase 3a's own version of this exact problem**: after
six real implementation commits, the file still showed zero tasks
checked. Confirmed genuine (not a stale-file mixup) by checking the
file's own timestamp against commit history, then reconciled non-bulk
and spot-checked at a specific task boundary before being trusted
(`d92a448`).

**Final verified state**: all 49 tasks complete across the full
implementation arc (`9c17e5d` through `2ffc0d1`). Full suite: **1084
passed, 0 failed**. **100% coverage on every file in `apps/risk/`**,
including the two new files this feature added (`tasks.py`,
`signals.py`).

### 5.4 The dev-database verification — two real writes, both explicitly approved, and one honestly-corrected finding

Both `T048` (read-only-adjacent, still confirmed before writing
throwaway data) and `T049` (a forced permanent failure, and a real
`loaddataset` re-run touching ~3,000 rows) were run live against the
persistent dev stack, each only after explicit go-ahead — the same
standing boundary established after Phase 2a's incident, holding
without exception through Phase 3b's two heaviest writes.

`T049`'s `loaddataset` step is the strongest single proof in this
sub-phase: a SHA-256 hash of every `(customer_id, score, tier)` row
was captured, the reload was run for real (not simulated), the
resulting flood of ~3,000 redundant recompute tasks was confirmed
fully drained via the Celery queue depth, and the hash was
re-computed and found **identical**. The accepted `loaddataset`-
redundancy tradeoff from §5.2 is not merely designed correctly — it
was proven correct, once, for real, against genuine volume.

**A count discrepancy (`3001` vs. the expected `3000`) was initially
waved off — *"let me not worry about that discrepancy now"* — and,
when pressed to actually trace it rather than accept the dismissal,
was investigated properly and its real, complete cause found.** The
first explanation offered (a single leftover `CustomerFactory`-
sequenced customer, `CL-90000`, three weeks old) was real but
**incomplete on its own** — insufficient by itself to produce the
discrepancy. The fuller cause, found on continued digging: `quickstart.
md`'s own Step 3 cleanup only ever deleted the throwaway *auth users*
it created, never the *customer and policy rows* those users had
created — meaning **each prior run of this exact quickstart step had
been silently leaving scratch data behind in the persistent dev
database.** Two such leaked customers (`CL-90001` from an earlier
session, `CL-90002` from this one) were found, confirmed to carry no
`RiskAssessment` first, then deleted — and `quickstart.md` itself was
permanently fixed to delete its own scratch rows going forward, so
this exact drift cannot recur.

**Worth stating plainly**: the first commit (`2ffc0d1`) credited only
the incomplete explanation. Rather than quietly let that stand once
the fuller cause was found, or rewrite already-pushed history to hide
the gap, a second commit (`ca2f72d`) stated openly what the original
message got wrong and why — see §2's new standing rule, which this
exact sequence established.

Committed across nine implementation-and-verification commits in
total for this final stretch (`eecc763` through `ca2f72d`).

---

## 6. Phase 3 — complete

**Both halves of the Risk Engine are done.** 3a built a transparent,
on-demand, explainable scoring engine — the platform's first real
exercise of constitution Principle IV. 3b made it automatic, without
weakening any of 3a's guarantees: the manual path is provably
unaffected, every score remains traceable to a persisted explanation,
and the append-only audit trail now distinguishes successful
computation, permanent failure, and human-triggered recompute as three
genuinely distinct, queryable outcomes.

**Real bugs found across the full Risk Engine phase, all through
actually running the system, none through however-careful a static
read**: the `90`-vs-`100` scale documentation error (3a); an infinite
signal-recursion bug with real production consequences (3b); and, the
standout of the entire project so far, a guard-rail test that had
been passing for the wrong reason since the moment it was first
written, discovered only by reading a framework's real behavior
instead of trusting an inherited assumption.

**The throughline holds a third time, across a genuinely different
kind of complexity than Phases 1 and 2 ever introduced** — the first
real concurrency, the first real background worker, the first real
async task queue in this project. Static review, careful specs, and
well-reasoned plans all mattered and all helped. None of them, alone,
would have caught the recursion bug or the vacuous test. Only running
the system, under real conditions, ever has.

**Next**: Phase 4 (AI/LLM Integration) — not started, to begin in a
future session.

---

## 7. Progress log


**2026-08-17 to 2026-08-18** — Phase 3a spec, plan, and analyze
remediation complete; implementation started and partially complete.
Spec review verified extensive evidentiary rigor: gender excluded on
both statistical and ethical grounds, the existing `risk_score` field
proven to be noise before replacement (not just asserted), a tier-
distribution simulation run against real data before committing to
SC-005, and a deliberate staleness-disclosure design kept after
explicit consideration rather than trimmed for convenience. Analyze
caught a real constitutional-weight bug (D1: the audit write for
score computation was scheduled eight phases after the write path it
needed to cover) plus two MEDIUM findings, one of which (C2, the
gender/location exclusion) was treated with more care than its label
implied given its regulatory weight — fixed with a hard equality
assertion on the exact factor set, not just an absence check.
Implementation hit a real interruption (an API error, a stale recap,
an auto-mode onboarding prompt correctly declined) and resumed to find
`apps/risk/` genuinely mid-scaffold. A real arithmetic error (band
maxima summing to 90, not the 100 claimed in two docstrings) was
found, correctly investigated as a spec question rather than resolved
unilaterally - and a wrong instruction from this runbook's own author,
claiming FR-005 mandated 100, was caught and corrected before it could
cause an unwarranted, costly fix. Corrected the documentation to match
the verified-working code; left all point values, `RULE_SET_VERSION`,
and the existing 3,000-row validation untouched. A second, deeper gap
(the originating test itself still hardcoding 100) was caught by
actually re-running the suite, not assumed fixed once the docs agreed
with the code. A live source bind-mount was added to `docker-compose.yml`,
likely closing the Phase 2b stale-image failure class permanently.
`rules.py` and its full test file are done and committed (`e1f15bd`,
54/54 tests); the remaining ~88 tasks are still ahead. Stopped
deliberately at this point given session length, with the
highest-risk file safely committed rather than left exposed in the
working tree.

**2026-08-19 to 2026-08-20 — Phase 3a complete.** T012 through T099
finished across six well-organized commits, each independently
verified rather than trusted as a batch. Both flagged checkpoints from
the prior session (T033's audit-write sequencing, T011a's factor-set
equality) were re-confirmed against real source lines before further
work proceeded. A genuine process gap was caught and fixed:
`tasks.md`'s checkboxes were never updated through six commits' worth
of real work - confirmed real (not a stale-file mixup) by checking the
file's own timestamp against commit history, then reconciled
non-bulk and spot-checked at the T083/T084 boundary. The
`Customer.risk_score` field was correctly made engine-only and
read-only (T084-T090), with the reasoning grounded directly in
Principle IV. The full quickstart (all 10 steps) ran end-to-end
against real dev infrastructure, including an empirical double-run
proving idempotency. A real, unrelated data discrepancy - surfaced
during cleanup and initially dismissed with "regardless, it's
correct" - was properly root-caused on request via the append-only
audit trail: an unrelated `loaddataset` run had silently reconciled
every CSV-mapped field on a policy, not just the one being checked,
overwriting a field under manual test as an undocumented side effect.
The original dismissal was explicitly named as wrong, not quietly
corrected, and the finding was recorded to persistent memory as a
standing lesson for future manual dev-DB work. Two documentation-only
gaps found during the quickstart run were fixed immediately rather
than deferred. Final, independently verified: 100/100 tasks, 1049/1049
tests passing, 100% coverage on every file in `apps/risk/`, 99%
overall, dev database confirmed clean at 3,000 customers. Committed
across `15396ee` and `2272284`, both pushed, `origin/main` confirmed
matching local `HEAD`. **Phase 3a is done.** Next: Phase 3b
(automatic recompute via Celery).

**2026-08-21 to 2026-09-01 — Phase 3b complete; Phase 3 (Risk Engine)
complete.** Automatic recompute via Celery, the first background
worker and first real async task queue in this project. Spec/plan
scoped three real decisions deliberately (broad trigger, retry/
backoff-then-alert, accept `loaddataset`'s redundant-task flood rather
than solve it), and correctly named a genuine tension with an
already-passing Phase 3a test (*"the codebase contains no signal
handler"*) as something to revise, not silently break. Implementation
surfaced a real, production-serious infinite-recursion bug
(`persist()` → `save()` → signal → re-enqueue → `persist()`), fixed
via `.update()` over a signal-guard specifically for concurrency
safety, chosen and explained rather than assumed. Found, while
completing the planned test revision, the single most valuable
finding of the whole project to date: a guard-rail test that had been
passing for the wrong reason - a Django API return-shape
misunderstanding - since the moment it was first written in Phase 3a,
meaning it could never have failed regardless of what was ever wired
up, through the entirety of both sub-phases. Two more genuine gaps
self-caught during review (a stale AST allowlist, an entrypoint script
ignoring command overrides). The dev-database verification proved the
`loaddataset`-redundancy tradeoff correct via a real SHA-256 hash
match across ~3,000 rows, and an initially-dismissed count discrepancy
was, on request, traced to its real and complete cause (leaked
quickstart scratch data across two prior sessions, not just the
single artifact first credited) - with the resulting correction made
as a new, honest commit rather than a silent rewrite of already-pushed
history. Final: 49/49 tasks, 1084/1084 tests, 100% coverage on every
`apps/risk/` file. Committed across `9fa7f74` through `ca2f72d`
(twenty-one commits total for the sub-phase), all pushed and
independently confirmed via a fresh terminal after one window
appeared to hang. **Phase 3 (on-demand + automatic risk scoring) is
done.** Next: Phase 4 (AI/LLM Integration), to begin in a future
session.