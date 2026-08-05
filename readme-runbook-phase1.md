# Runbook — Phase 1 (Foundation)

**Living document.** This gets appended to as Phase 1 actually
progresses — sections marked `⏳ PENDING` are placeholders, filled in
with real output/commands/results once each step happens, the same
way `readme-setup-conclusions.md` grew during Phase 0. Nothing here is
retroactively invented; if a section is empty, that step hasn't
happened yet.

**Who this is for**: written assuming you're new to Spec-Driven
Development and Claude Code specifically — every term gets explained
on first use, not assumed knowledge.


---

## 1. What Phase 1 actually is

Per `README-Business-Requirements-Document.md`'s roadmap (§13), Phase
1 is the **foundation** — nothing user-facing yet, just the skeleton
everything else gets built on:

- A working Django 5.x project, structured into `apps/` (customers,
  policies, claims — matching the BRD's suggested layout)
- Docker Compose running PostgreSQL 16+ and Redis locally
- A custom `User` model implementing the BRD's 9 roles (Fraud Analyst,
  Claims Adjuster, Customer Service, Underwriter, Compliance Officer,
  Risk Manager, Product Manager, Executive Leadership, System
  Administrator)
- A health-check endpoint (so later phases/monitoring have something
  to actually check)

**Explicitly out of scope for Phase 1**: any AI/LLM/Ollama features.
Those are Module 7/8, informed by Phase 0's findings, but deliberately
not part of this phase's spec — mixing them in early would blur what
Phase 1 is actually testing.

---

## 2. Beginner glossary — Spec Kit terms used throughout this doc

| Term | What it means here |
|---|---|
| **Constitution** | The project's own governing rules document (`.specify/memory/constitution.md`), already ratified in an earlier session. Every later spec must comply with it. |
| **Spec** | A structured description of *what* a feature/phase must do — requirements, not implementation. Written by `/speckit-specify`. |
| **Plan** | The *how* — architecture and technical approach for satisfying a spec. Written by `/speckit-plan`. |
| **Tasks** | The plan broken into concrete, actionable steps. Written by `/speckit-tasks`. |
| **Implement** | Claude Code actually writing the code for those tasks. Run via `/speckit-implement`. |
| **Skill** | A predefined capability Claude Code can run as a slash command (e.g. `/speckit-specify`). Installed skills live in `.claude/skills/` — always safe to `ls` that folder if a command name looks unfamiliar. |

The four core commands run in this order, every time, for every
feature or phase: **specify → plan → tasks → implement.** You don't
skip steps or reorder them.

---

## 3. Prerequisites

Assumes `README-Local-Setup.md` has already been followed in full
(Spec Kit installed, Claude Code authenticated via **Pro subscription
— not an API key**, constitution ratified). If any of that hasn't
happened yet, do that first — this document picks up from there.

```bash
cd ~/insurance-ai-platform
pwd
```
**Expect**: `/home/bijut/insurance-ai-platform`

```bash
git status
```
**Expect**: clean working tree before starting any new phase work.

If you have a Python virtual environment active from a *different*
project (e.g. the Phase 0 spike's `venv`), deactivate it first — it
has nothing to do with this repo and can cause confusing package
conflicts later if left active by accident:
```bash
deactivate
```

---

## 4. Model selection strategy for this phase

Confirmed, not guessed — from Claude Code's own `/status` → Usage
panel, cost is **$0.0000** regardless of which model is used, as long
as authentication is via the Pro subscription (not an API key). What
changes between models is **usage quota consumption**, not dollars:

| Spec Kit command | Model | Why |
|---|---|---|
| `/speckit-constitution` | Opus | Already done — foundational, hardest to walk back |
| `/speckit-specify` | **Opus** | Defines scope/behavior for everything downstream |
| `/speckit-plan` | **Opus** | Architecture-level decisions, same stakes as specify |
| `/speckit-tasks` | Sonnet | Mechanically breaking an approved plan into steps — lower stakes |
| `/speckit-implement` | Sonnet | Routine code generation from already-approved tasks |
| Debugging a stuck/wrong implementation | Opus, situationally | Escalate for that one problem, then drop back to Sonnet |

**Practical habit**: don't switch models mid-session. Switching forces
Claude Code to reprocess the whole conversation at full cost instead
of reading from cache — so finish specify+plan in one Opus session,
then start a **fresh session** on Sonnet for tasks+implement, rather
than ping-ponging within one conversation.

Check real usage anytime with `/status` inside a Claude Code session,
then look at the Usage panel — shows actual 5-hour session % and
weekly % used, not an estimate.

### Real evidence, not just theory — from this project's actual `/speckit-*` run

The table above was a prediction before Phase 1 started. Here's what
actually happened, captured directly from `/status`:

| Step | Model | Real cost signal |
|---|---|---|
| `/speckit-plan` | Opus | Consumed **44-53% of the entire 24-hour usage window** on its own (the percentage shifted between two checks as other work added to the rolling window — both readings agree it was the dominant single consumer) |
| `/speckit-tasks` | Sonnet | **$0.87 notional cost** for 297 lines of real output (72 tasks across 8 phases) |

**One number needs a plain explanation, because it looks alarming out
of context**: `/status` shows a "Total cost" figure (e.g. `$0.87`) even
though we independently confirmed actual billing is `$0.0000` under
the Pro subscription (§ earlier in this doc — confirmed via
`Login method: Claude Pro account`, not an API key). **That "Total
cost" is a notional/reference number** — what the session *would* have
cost on pay-per-token API pricing, shown for comparison purposes. It
is not a real charge. Useful as a relative measure between steps (Opus
vs. Sonnet, one command vs. another), not as an actual bill.

**Practical lesson learned mid-project**: `/status` also showed
**75% of the current 5-hour session used** at one point, with the
reset about an hour away. That's not something to panic about, but it
is worth checking *before* starting another heavy `/speckit-*` command
— starting a long-running generation at 75% used risks hitting the
reset mid-task, which is an annoying place to be interrupted.
**Habit**: run `/status` before, not just after, any step expected to
be substantial (specify, plan, a large implement task), especially
later in a work session.

---

## 5. Step-by-step: running the Phase 1 spec cycle

### Step 5.1 — `/speckit-specify`

Model: Opus. Exact prompt used:

```
/speckit-specify Phase 1 - Foundation. Build the local dev environment: 
Django 5.x project skeleton (apps/ structure: customers, policies, 
claims per README-Business-Requirements-Document.md's suggested 
layout), Docker Compose with PostgreSQL 16+ and Redis, a custom User 
model implementing the 9 roles from the BRD's Primary Users list 
(Fraud Analyst, Claims Adjuster, Customer Service, Underwriter, 
Compliance Officer, Risk Manager, Product Manager, Executive 
Leadership, System Administrator), and a health-check endpoint. Per 
the constitution: RBAC must be enforced server-side (Principle III), 
an AuditLog model must exist even if minimally used in this phase 
(Principle II), and pytest + Factory Boy must be set up from the start 
(Principle V). No AI/LLM/prompt features in this phase - that's 
Module 7/8, informed by the Phase 0 findings, but not part of this 
spec.
```

**Approval habit**: when it prompts to write the spec file, approve
**one file at a time** (option `1. Yes`), not "allow all edits" — this
is a foundational artifact worth watching get created, not
rubber-stamping.

**What to check once it's written** (per the constitution's own
"Compliance review" rule): read the generated spec yourself and
confirm it explicitly addresses:
- [ ] Audit logging (Principle II) — not just implied, actually stated
- [ ] Server-side RBAC (Principle III) — not just "roles exist" but
      how they're enforced
- [ ] Test coverage expectations (Principle V) — pytest + Factory Boy
      referenced, not just "will be tested"

A spec that's silent on any of these is incomplete per the
constitution's own governance rule, not just light on detail — go
back and ask for revisions rather than proceeding to `/speckit-plan`
with a gap.

**Result**: ✅ VERIFIED via direct `cat` of the file (not terminal trust
alone — see §7's known-issue below for why that distinction mattered).
Saved at `specs/001-foundation-platform-skeleton/spec.md`. Five
prioritized user stories (P1: local environment + RBAC enforcement;
P2: audit logging, health check, testing infrastructure), 34 numbered
functional requirements grouped by area, explicit Key Entities
(User, Role, AuditLog, HealthStatus), 11 measurable Success Criteria,
explicit Out of Scope section, and Assumptions/Dependencies sections.

Compliance check — all three constitution principles explicitly
addressed:
- Audit logging (Principle II): FR-018 to FR-024, including the
  write-fails-but-action-succeeds edge case (FR-022)
- Server-side RBAC (Principle III): FR-008 to FR-017, explicitly
  stating UI-hiding alone is insufficient (FR-011)
- Testing infrastructure (Principle V): FR-029 to FR-034 — correctly
  written technology-agnostic ("automated test suite," "reusable
  test-data builders") rather than naming pytest/Factory Boy directly,
  since specs describe *what*, not *how*; watch for those names to
  appear in `/speckit-plan` instead

Also correctly enforces Principle VI (Phase 0 spike is not a
dependency) and Principle I (local-first, testable via "outbound
network blocked" acceptance scenario).

**Quality checklist** (`checklists/requirements.md`) also verified
saved — includes a full traceability matrix (every requirement group
→ user story → success criteria) and explicit confirmation that
Principle IV (Explainable AI) is deliberately non-applicable to this
phase rather than silently skipped. Self-assessed status: "Ready for
`/speckit-plan`" — agrees with the independent review above.

### Understanding what `/speckit-specify` actually did (for beginners)

**What its job is, in one sentence**: it turns a plain-English feature
description into a structured, testable **specification** — the
*what* and *why*, deliberately not the *how* (that's `/speckit-plan`'s
job). Its output is meant to be reviewable by a non-engineer, which is
why it's written in "the system MUST..." language rather than code or
architecture terms.

**What it actually did, step by step, in our run:**

1. **Checked for extension hooks** — looked for
   `.specify/extensions.yml` (a way projects can customize the Spec
   Kit workflow with pre/post steps). We don't have one, so it skipped
   straight to the real work.
2. **Read three files for context**: the BRD
   (`README-Business-Requirements-Document.md`), the constitution
   (`.specify/memory/constitution.md`), and the spec template
   (`.specify/templates/spec-template.md`). It didn't invent
   requirements from nothing — it grounded everything in documents
   that already existed. That's *why* the spec cites specific
   constitution principles by number, and references the BRD's exact
   9-role list.
3. **Decided on a name and number**: `foundation-platform-skeleton`,
   prefixed `001` because `specs/` was empty (first spec ever written
   for this project). Numbering is sequential — the *next* spec
   written will automatically become `002-something`.
4. **Wrote `.specify/feature.json`** — bookkeeping, not spec content.
5. **Wrote `specs/001-foundation-platform-skeleton/spec.md`** — the
   actual specification.
6. **Wrote `specs/001-foundation-platform-skeleton/checklists/requirements.md`**
   — a self-review checklist grading the spec it just wrote.

**Every file and folder it created, and what each is for:**

```
.specify/
└── feature.json                                    ← bookkeeping only

specs/
└── 001-foundation-platform-skeleton/                ← one folder per feature/phase
    ├── spec.md                                      ← the actual specification
    └── checklists/
        └── requirements.md                          ← quality self-check of spec.md
```

| File | Purpose | Who reads it next |
|---|---|---|
| `.specify/feature.json` | Records which feature directory is "active," so `/speckit-plan` and later commands know where to write without being told again | Every subsequent `/speckit-*` command in this feature's lifecycle |
| `specs/001-.../spec.md` | The real deliverable — requirements, user stories, success criteria, scope boundaries | `/speckit-plan` reads this to know *what* it's building a technical approach for |
| `specs/001-.../checklists/requirements.md` | A self-graded quality gate — did the spec meet Spec Kit's own bar (testable requirements, no leaked implementation details, no unresolved clarification markers)? | You, as a human reviewer — meant for a person deciding whether to proceed, not consumed by later automation |

**Why the folder is numbered `001-`**: every feature/phase gets its
own numbered folder under `specs/`. This gives a permanent, ordered
history — `001-foundation-platform-skeleton` today,
`002-whatever-comes-next` later, each self-contained, never
overwritten. Anyone can open `specs/` months later and read the entire
sequence of requirement decisions in order, like a changelog for
*requirements*, separate from the code's own git history.

**Anatomy of `spec.md` — why each section exists**, using our actual
spec as the reference:

| Section | Job | Example from our spec |
|---|---|---|
| Overview | One paragraph: why does this feature exist at all | "This feature establishes the foundation on which every later module will be built" |
| User Scenarios & Testing | Real people, real journeys, in priority order (P1 = must-have, P2 = important-but-not-blocking) | User Story 2: "Administrator Assigns Roles and the System Enforces Them" |
| Edge Cases | The things that break naive implementations | "The System Administrator role MUST NOT be silently treated as an unrestricted bypass" |
| Functional Requirements (FR-XXX) | Numbered, individually testable "the system MUST..." statements | FR-011: server-side enforcement, not UI-hiding |
| Key Entities | The data concepts involved, *without* saying which database/ORM — that's a plan decision | `User`, `Role`, `AuditLog`, `HealthStatus` |
| Success Criteria (SC-XXX) | Measurable, technology-agnostic pass/fail bars | SC-001: "reaches a fully running platform in under 30 minutes" |
| Out of Scope | Explicitly what this spec does NOT cover, so nothing gets silently assumed either way | AI/LLM features, dashboards, production deployment — deferred to named later phases |
| Assumptions | Judgment calls made when the request didn't specify something, stated openly rather than hidden | "Single role per user" — a real decision, written down instead of silently baked in |
| Dependencies | What this spec relies on already existing | The constitution, the BRD, a container runtime |

**The single most important thing to notice**: nowhere in `spec.md`
does it say "Django," "PostgreSQL," or "pytest" as part of a
*requirement* — those are locked in the *constitution* as pre-decided
facts (referenced, not re-decided), but the requirements themselves
are written so they'd still make sense even if the tech stack were
swapped. That's the whole discipline of spec-driven development:
**spec = what/why, plan = how.** `/speckit-plan` is where Django/DRF/
pytest actually get named as *decisions*.

**What this means for reviewing `/speckit-plan` next**: it doesn't
start from scratch — it reads `spec.md` (the file just described) and
produces the *technical* answer to every requirement in it: which
Django apps, which DRF permission classes enforce FR-011, how
`AuditLog` actually gets written to, where pytest+Factory Boy get set
up. The useful review question when the plan arrives is: **"does this
plan actually address every FR-XXX from the spec?"** — not just
"does this look like reasonable code architecture."

### Step 5.1a — Committing the verified spec artifacts

Purpose: get the verified `spec.md` and `checklists/requirements.md`
into version control, so this milestone is preserved and pushed before
moving on to `/speckit-plan`.

**First attempt failed** — the runbook file had been shown as "ready"
in chat but never actually saved to the WSL machine:
```bash
$ git add readme-runbook-phase1.md specs/
$ git status
fatal: pathspec 'readme-runbook-phase1.md' did not match any files
On branch main
Your branch is up to date with 'origin/main'.
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        .specify/feature.json
        specs/
```
**Lesson**: a file being generated and shown in chat is not the same
as it existing on disk — always confirm with `ls` before assuming a
save happened, the same discipline already applied to Claude Code's
own write prompts.

**Fixed** by actually downloading and placing the file:
```bash
$ ls readme-runbook-phase1.md
readme-runbook-phase1.md
```

**Staging revealed an unexpected extra file:**
```bash
$ git add readme-runbook-phase1.md specs/ .specify/feature.json
$ git status
Changes to be committed:
        new file:   .specify/feature.json
        new file:   readme-runbook-phase1.md
        new file:   specs/001-foundation-platform-skeleton/checklists/requirements.md
        new file:   specs/001-foundation-platform-skeleton/spec.md
        new file:   specs/001-foundation-platform-skeleton/spec.md-unfilled-SpecKit-template
```
`spec.md-unfilled-SpecKit-template` was never intentionally created by
either the runbook workflow or any `/speckit-*` command — real Spec
Kit output filenames are `spec.md`, not that. Most likely leftover
debug residue from the earlier write-rejection troubleshooting
(possibly a manual backup of the empty template made while diagnosing
that issue). **Honest gap**: its actual content was never verified
with `cat` before removal — it was deleted directly on the assumption
it was harmless template residue, not confirmed. Low-risk given the
filename strongly implies template boilerplate, but worth naming as an
assumption rather than a confirmed fact.

**Removed before committing:**
```bash
$ git restore --staged specs/001-foundation-platform-skeleton/spec.md-unfilled-SpecKit-template
$ rm specs/001-foundation-platform-skeleton/spec.md-unfilled-SpecKit-template
$ git status
Changes to be committed:
        new file:   .specify/feature.json
        new file:   readme-runbook-phase1.md
        new file:   specs/001-foundation-platform-skeleton/checklists/requirements.md
        new file:   specs/001-foundation-platform-skeleton/spec.md
```

**Committed and pushed:**
```bash
$ git commit -m "Phase 1: /speckit-specify complete for 001-foundation-platform-skeleton, verified spec + checklist"
[main 8327ed4] Phase 1: /speckit-specify complete for 001-foundation-platform-skeleton, verified spec + checklist
 4 files changed, 779 insertions(+)
 create mode 100644 .specify/feature.json
 create mode 100644 readme-runbook-phase1.md
 create mode 100644 specs/001-foundation-platform-skeleton/checklists/requirements.md
 create mode 100644 specs/001-foundation-platform-skeleton/spec.md

$ git push
To github.com:btholath/insurance-ai-platform.git
   831fb2a..8327ed4  main -> main

$ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
```

**Result**: exactly the 4 intended files landed in commit `8327ed4`,
pushed to `origin/main`, confirmed via a second `git status` — same
"verify, don't trust" discipline used for the spec file writes
themselves, applied here to the git workflow too.

### Step 5.2 — `/speckit-plan`

Model: Opus (same session as 5.1, per the no-mid-session-switching rule).

```
/speckit-plan
```

**Result**: ✅ VERIFIED. Created 8 files, confirmed via `git status`
and a full independent file listing (not terminal narration alone):

```
specs/001-foundation-platform-skeleton/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    ├── README.md
    ├── health.md
    ├── users.md
    └── audit.md
```

Ran cleanly on the first attempt this time — no rejected writes, no
stray files (contrast with the specify step's two rejections and one
unexplained extra file — see §7).

**Deep-reviewed in full** (not just skimmed): `plan.md`, `research.md`
(all 12 numbered decisions), and `contracts/users.md`. All three
independently verified via `cat`, cross-checked against `spec.md`'s
actual FR-XXX numbers rather than taken on the plan's own word.
`data-model.md`, `contracts/health.md`, `contracts/audit.md`,
`contracts/README.md`, and `quickstart.md` exist and are referenced
consistently by the files that *were* deep-reviewed, but were not
independently read line-by-line in this review pass — worth a look
before `/speckit-implement` if anything about their content becomes
load-bearing.

**Verdict: strong. Every principle-relevant requirement traced to a
specific technical decision, not a restatement of the spec.** Notable
catches — the kind of thing that separates a real plan from a
plausible-sounding one:

- **`AbstractBaseUser` over `AbstractUser`**: avoids Django's built-in
  `groups`/`user_permissions`, which would invite authorization logic
  to drift away from the single `HasRole` mechanism FR-015 requires.
- **`AUTH_USER_MODEL` timing**: flagged as "the single highest-cost
  ordering mistake available in this phase" — it cannot be changed
  after the first migration without a destructive reset. This is a
  real, commonly-hit Django trap.
- **404 vs. 403 by route type**: unauthenticated/unpermitted callers
  get `404` on detail routes (a `403` would confirm the record
  exists — FR-012) but `403` on collection routes. Applied
  consistently, including to the sign-in endpoint.
- **Audit write atomicity**: explicitly rejected both Django signals
  (can't see the acting user without thread-local state; fire on
  fixtures/migrations too) and a Celery task (would let the action
  commit before the log exists, violating FR-022) — both are the
  "obvious-looking but wrong" choices a less careful plan would reach
  for.
- **Two-layer audit immutability**: an ORM guard (fast, legible
  errors) plus a PostgreSQL `BEFORE UPDATE OR DELETE` trigger (the
  actual guarantee — the ORM guard alone can't stop `bulk_update` or a
  raw SQL session).
- **`actor_role` snapshot**: records what role the actor held *at the
  time of the action*, not their current role — a later role change
  would otherwise silently rewrite audit history's meaning.
- **Celery/pgvector correctly deferred, not skipped**: both explicitly
  traced back to `spec.md`'s own Out of Scope section, not presented
  as a fresh independent decision — confirmed by direct quote-check
  against the spec.
- **WSL2-specific bind-mount warning**: named volumes chosen over bind
  mounts specifically because of real WSL2 I/O/permission issues with
  Postgres, not a generic Docker best-practice.
- **FR-017 verification**: not addressed in `research.md`/`plan.md`
  directly — confirmed present instead in `contracts/users.md`
  ("All endpoints here are restricted to the System Administrator
  role"), which is the *correct* location for an endpoint-level
  permission declaration. Checked rather than assumed.

**Two things flagged for the validation checklist (§6)**, both real
operational gotchas the plan itself surfaced:
1. Tests must run via `docker compose exec web pytest`, not host-side
   — the host WSL Python (3.12.3) is a different interpreter than the
   container's (3.13).
2. Postgres/Redis ports are **not** published to the host by default
   in the compose file — a local `psql` connection needs the commented
   mapping uncommented first, it won't work out of the box.

### Understanding what `/speckit-plan` actually did (for beginners)

**What its job is, in one sentence**: it reads the spec (the *what/
why*) and produces the *how* — concrete technical decisions, with
alternatives considered and rejected, for every requirement that needs
one. This is where Django, DRF, pytest, and every other named
technology finally show up as decisions, not just referenced facts.

**What it actually did, step by step, in our run:**

1. Checked current repo state and the checklist artifacts — confirmed
   the spec and quality checklist from the previous step actually
   existed before building anything on top of them.
2. Caught a real environment mismatch: host WSL has Python 3.12.3,
   the constitution mandates 3.13. Reasoned through it correctly —
   since the app runs in a container, the container's interpreter is
   what matters, not the host's. Resolved, not ignored or silently
   downgraded.
3. Read the BRD's suggested project structure section — grounded the
   folder layout in an existing document, same pattern `/speckit-specify`
   used with the BRD and constitution.
4. Wrote `plan.md` — technical context, the pre-design Constitution
   Check, and the project structure with reasoning for every
   deviation from the BRD's suggested layout.
5. Generated the supporting design files — `research.md` (12 numbered
   decisions), `data-model.md`, `contracts/` (4 files), `quickstart.md`.
6. Ran a second Constitution Check, this time against the *finished*
   concrete design rather than just the initial intent, recorded
   directly in `plan.md`.
7. Reported "Planning complete" with a summary table and three things
   flagged for review before proceeding — all three independently
   verified afterward rather than taken on faith (see §5.2's Result
   above).

**Every file it created, and what each is for:**

| File | Purpose |
|---|---|
| `plan.md` | The top-level plan: technical context, the Constitution Check (run twice — once before design, once after, re-verifying nothing drifted), and the actual project folder/file structure with reasoning for every deviation from the BRD's suggested layout |
| `research.md` | The *why* behind every non-obvious technical choice — one numbered section per decision, each with a rationale and a list of alternatives considered and rejected. This is the file worth reading most closely; it's where real engineering judgment lives |
| `data-model.md` | The entities (`User`, `AuditLog`, `Role`, `HealthStatus`) with their actual fields/constraints — the technical version of the spec's more abstract "Key Entities" section |
| `contracts/` (a folder, not one file) | One file per API surface — `README.md` for shared conventions, `health.md`/`users.md`/`audit.md` for each endpoint group. Each documents exact request/response shapes, status codes, and which role can do what |
| `quickstart.md` | Setup steps from a clean clone, plus validation scenarios mapped back to the spec's user stories — this becomes the actual "how do I prove this works" reference |

**Anatomy of `plan.md` — why each section exists:**

| Section | Job | What it actually contained in ours |
|---|---|---|
| Summary | One paragraph, plain-language technical approach — fast orientation before the details | "Stand up the Django 5.x + PostgreSQL 16 + Redis local environment... make server-side RBAC and append-only audit logging structural from day one" |
| Technical Context | Pins down every concrete technical fact needed before evaluating anything else — language version, dependencies, storage, testing tools, target platform, performance goals, constraints, scale | The Python 3.13-in-container reasoning lives here, spelled out explicitly, not buried |
| Constitution Check (pre-design gate) | The actual gate — one row per principle: does it apply, how is it satisfied, pass/fail/N/A. A plan that fails here is supposed to stop before detailed design is wasted effort | All 6 principles evaluated; Principle IV correctly marked N/A (no AI surface this phase) rather than silently skipped |
| Project Structure | Two parts: the documentation layout (this feature's `specs/` folder contents) and the real source-code layout (`config/`, `apps/`, `docker/`, etc.) — plus a **Structure Decision** paragraph explaining every deviation from the BRD's suggested layout, with reasoning | The actual blueprint `/speckit-implement` follows — explains *why* `frontend/` isn't created, why `apps/core` and `apps/audit` exist beyond the BRD's original app list |
| Complexity Tracking | A table for recording any place the plan needs to break a constitution principle, forcing explicit written justification rather than silently doing it | "Not required — Constitution Check passed with no violations" — empty because nothing needed to violate anything |
| Post-Design Constitution Re-Check | Re-verifies every principle, but this time against the *finished* concrete design (the actual data model, actual contracts) rather than just the initial intent | Catches drift between "we intend to do audit logging right" (first check) and "here's the exact field-by-field design, does it actually satisfy Principle II" (second check) — both passed here |

**Why the two-check structure matters**: a plan can pass the first
Constitution Check by describing good intentions and still fail the
second one if the detailed design drifted somewhere along the way.
Ours passed both — meaning the final concrete design (immutability
triggers, the `HasRole` class, the 404-vs-403 split) actually delivers
what the early intent promised, not just gestures at it.

**Why `research.md` matters more than it might look like at first
glance**: every one of its 12 decisions follows the same shape —
*decision, rationale, alternatives considered and rejected.* That
last part is what separates a real plan from a plausible-sounding
one. Anyone can state a decision; stating *why the obvious alternative
was wrong* is what proves the reasoning actually happened rather than
being generated to sound authoritative. When reviewing your own future
plans, the alternatives-rejected sections are the highest-value thing
to actually read.

**What this means for reviewing `/speckit-tasks` next**: tasks should
be traceable back to *this* plan's concrete decisions, not just the
spec's abstract requirements. A good task references *how* (e.g. "add
the `HasRole` permission class to `apps/core/permissions.py`"), not
just *what* (e.g. "implement RBAC") — the plan already did the work of
turning "implement RBAC" into a specific, locatable decision; tasks
should inherit that specificity, not flatten it back out.

### Step 5.3 — `/speckit-tasks`

Model: Sonnet, **new session** (not continuing the Opus session from
5.1/5.2).

```
/speckit-tasks
```

**What to check**: tasks should be concrete and independently
completable, not vague restatements of the plan. If a "task" is really
still a paragraph of architecture description, that's a sign
`/speckit-plan` wasn't specific enough — worth revisiting before
proceeding to implementation.

**Result**: ✅ VERIFIED. Created 1 file — `tasks.md` — 72 tasks
(T001-T072) across 8 phases. Clean write on the first attempt, no
rejections, no stray files (confirmed via `git status` showing exactly
one untracked file). 297 lines of real content, confirmed via full
`cat` (no garbling, unlike one earlier read attempt during the plan
step). Two specific claims independently verified via `grep`/`sed`
against the real file rather than taken on the completion report's
word: the User-model-first-migration warning appears 5 separate times
across the document, and the US1/US4 execution reordering's stated
reasoning matches the actual recommended sequence. Real cost data
captured for this step: $0.87 notional cost (Sonnet) for the full
297-line output — see §4's "Real evidence" subsection for the
comparison against `/speckit-plan`'s Opus cost.

### Understanding what `/speckit-tasks` actually did (for beginners)

**What its job is, in one sentence**: it reads the plan (the *how*)
and breaks it into concrete, ordered, independently-completable
implementation steps — small enough to actually execute and verify
one at a time, organized by user story so each story can be built and
tested independently of the others.

**What it actually did, step by step, in our run:**

1. Checked for extension hooks (none — same as the previous two
   steps).
2. Loaded the design documents in parallel — `plan.md`, `research.md`,
   `data-model.md`, `quickstart.md`, and the spec, plus a shell
   command (likely listing the `contracts/` folder).
3. Loaded the `contracts/` files individually and the constitution,
   and checked Spec Kit's own tasks template.
4. Noted explicitly that the spec requires tests (FR-029 through
   FR-034) and that constitution Principle V mandates tests be written
   *before* the code they cover — stated this as a rule the generated
   tasks would have to follow, before generating anything.
5. Made a real structural decision before writing: recognized that
   User Story 1 (P1, "environment runs") depends on outputs that
   belong to Stories 2 and 4 (the User model, the health endpoint) —
   so it restructured the execution order into Setup → Foundational
   (everything that blocks every story) → Stories, rather than
   mechanically numbering phases in spec-priority order and letting
   the dependency problem surface later.
6. Wrote `tasks.md`.
7. Checked for post-execution hooks (none).
8. Produced a completion report: a phase/task-count breakdown table,
   parallel-execution opportunities, each story's independent test
   criteria (copied forward from the spec, not reinvented), a
   suggested MVP scope, and an explicit format-validation step (grep
   confirming every task followed the checkbox convention).

**Every file/folder it created:**

Just one file this time — no new folder, unlike the plan step:
```
specs/001-foundation-platform-skeleton/
└── tasks.md
```

| File | Purpose |
|---|---|
| `tasks.md` | The full implementation checklist — every task individually completable, ordered so dependencies are respected, grouped by user story so each story is independently buildable and testable |

**Anatomy of `tasks.md` — why each section exists:**

| Section | Job | What it actually contained in ours |
|---|---|---|
| Frontmatter + Input/Prerequisites | Confirms every design document this file depends on actually exists before generating tasks from them | Listed `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md` — "all present" |
| **Tests** policy statement | States up front whether tests are included and why — this is a project-level policy decision, not left implicit per-task | Explicitly cites FR-029 through FR-034 and constitution Principle V; states tests must be written and fail *before* their implementation task |
| Organization + Format | Explains the grouping principle (by user story) and the `[ID] [P?] [Story] Description` convention so every task is scannable at a glance | `[P]` = can run in parallel (different files, no dependency); `[Story]` = which user story this task belongs to |
| Path Conventions | Ties every task's file paths back to `plan.md`'s actual project structure, so tasks and plan can't silently drift apart | `config/`, `apps/<name>/`, `tests/`, `docker/`, `scripts/` — the exact same layout `plan.md` defined |
| Phase sections (Setup → Foundational → US1-US5 → Polish) | Each phase states its Purpose, lists Tests-then-Implementation tasks in that order, and ends with a Checkpoint describing what's provably true once the phase is done | The `⚠️ CRITICAL` callout in Foundational's header is a direct example — the phase description itself carries the User-model-ordering warning, not just a footnote |
| Dependencies & Execution Order | The real sequencing logic — which phases block which, and *why* the recommended order sometimes differs from spec-priority order | The US1/US4 reordering lives here, with its reasoning stated explicitly, not just implied by the task numbers |
| Parallel Example | A concrete, copy-pasteable illustration of what "these tasks can run together" actually looks like in practice | A 4-task example from User Story 2's test-writing phase |
| Implementation Strategy | Three framings of the same task list for different situations — MVP-first for a single developer, incremental delivery as a checklist, and a parallel-team split | The parallel-team version even assigns specific stories to hypothetical "Developer A/B/C" — useful if this project ever isn't solo |
| Notes | Cross-cutting reminders that don't belong in any one phase — repeats the User-model warning a final time, states the audit-immutability-tested-at-two-layers requirement, and recommends committing after each task or logical group | Reinforcement, not new information — the same critical facts stated once in Foundational's header show up again here for anyone skimming straight to the bottom |

**Why the "Tests" policy statement matters as its own section**: a
task list could easily bury "oh, and write tests too" as an implicit
expectation on every implementation task. Making it an explicit,
separate policy statement up front — citing the specific FRs and the
specific constitution principle — means nobody generating or reviewing
individual tasks later has to guess whether a given task needs a test
written first. It's decided once, for the whole document, not
re-litigated per task.

**Why the Dependencies & Execution Order section is the most
important one to actually read**: the phase *numbers* (Phase 3 = US1,
Phase 6 = US4) reflect spec priority, but the *recommended sequence*
correctly overrides that when priority and dependency conflict — this
is exactly the same "real reasoning, not mechanical pattern-matching"
signal we looked for in the plan step's alternatives-rejected
sections. A tasks.md that just numbered phases 1-8 and told you to do
them in that literal order would have handed you an unbuildable
sequence (Phase 3/US1's own checkpoint needs something Phase 6/US4
hasn't built yet).

**What happens next, now that you understand this**: `/speckit-analyze`
(already invoked, pending review) is a cross-artifact consistency
check — it reads spec, plan, and tasks together and looks for drift
between them, rather than reviewing any one document in isolation.
Once that's reviewed, `/speckit-implement` is where actual code
finally gets written. The review question shifts one more time: does
the generated code match *this* task list's specific file paths and
decisions — not just "does it compile" or "does it seem reasonable" —
and do tests genuinely get written and shown failing before their
implementation task, per the policy this document just established.

### Step 5.4 — `/speckit-implement`

Model: Sonnet (same session as 5.3).

```
/speckit-implement
```

**Result**: ✅ FOUNDATIONAL CHECKPOINT COMPLETE (Option B). Scoped
explicitly to Phase 1 (Setup) + Phase 2 (Foundational) only, per the
Option B checkpoint decision — `tasks.md` shows T001-T030 as `[X]`.
Both highest-stakes files (`permissions.py`, `audit/models.py`)
independently reviewed and verified with zero gaps — see the full
verification trail below. **User Stories (Phase 3+) intentionally not
started** — this is the review checkpoint itself, not a stopping
point due to a problem. First commit of the actual application code
still pending as of this entry — see §5.1a-style commit, to be done
at the start of the next session.

**Self-disclosed deviations from the literal task text** (Claude Code
reported these unprompted before asking for review — a good sign,
worth noting explicitly):

1. `apps/{accounts,audit,health,customers,policies,claims}/urls.py`
   are empty stubs (`urlpatterns = []`), not the real routes — those
   are explicitly scoped to out-of-run tasks (T044/T057/T063/T046).
   Pre-approved via the `config/urls.py` forward-reference discussion
   (see §7).
2. `docker-compose.yml` and the Docker image (nominally T029, part of
   T003) were built earlier than their task order, because generating
   T018's migration correctly required a real Django+Postgres
   environment, which only exists inside the container. Pre-approved.
3. `/health/` currently returns a Django `303` redirect to a
   locale-prefixed URL (`LocaleMiddleware`'s default behavior) rather
   than a real response — expected, since the health app is still a
   stub; will be superseded when US4 builds the real view (T062).
   **Independently verified** via `curl -sI` — confirmed the redirect
   is real and matches this explanation, not a guess. One oddity
   noted in the same response: a `Server: Splunkd` header, unusual for
   a Django dev response — flagged as worth watching for if odd
   responses recur, not chased further since the redirect itself is
   already fully explained.

**Independent verification performed** (not just accepting the
self-report):

- `apps/accounts/models.py` reviewed line-by-line against `plan.md`/
  `data-model.md`: `AbstractBaseUser` + `PermissionsMixin` (not
  `AbstractUser`, avoiding the groups/permissions drift risk from
  `research.md` §2), all 9 roles present and correctly named, `role`
  field has no `null=True` (the actual DB-level enforcement of
  FR-014's deny-by-default), `CheckConstraint` named `user_role_valid`
  exactly as `tasks.md` T016 specified, email lowercased on save.
- `apps/accounts/migrations/0001_initial.py` reviewed: `initial =
  True`, depends only on `auth` — confirmed genuinely first.
- **Migration confirmed actually applied**, not just generated —
  via direct `psql -c "\d accounts_user"` against the live container
  database (not trusting the migration file alone): every column,
  the unique+indexed `email`, the 9-value `CheckConstraint`, all
  matched exactly.
- **Discovered mid-verification**: `db`/`redis` had been stopped
  between turns (cause unclear — possibly incidental to the audit-row
  discussion). Restarted, re-verified healthy, re-ran the schema check
  against the *actual current* database state rather than assuming
  the earlier state still held.
- **Volume check** (`docker volume ls`) confirmed
  `insurance-ai-platform_postgres_data` survived the restart — this
  is genuinely the same database as before, not a fresh one, meaning
  Claude Code's disclosed "one stuck AuditLog row from a trigger test"
  is real and still present. Confirmed directly:
  ```
  SELECT * FROM audit_auditlog;
  → id=1, action=user.created, outcome=succeeded,
    actor_identifier=test@example.com,
    actor_role=system_administrator
  ```
  **Decision**: keep it rather than reset (`docker compose down -v`).
  Rationale — it's informal, free evidence the append-only trigger
  genuinely fired during real manual testing, before the formal
  pytest suite (T048/T049) exists to prove it properly. Resetting now
  would only mean redoing already-verified-correct migration work for
  no benefit.
- **Bonus discovery, not yet fully confirmed**: `\d accounts_user`'s
  output showed the `audit_auditlog` table already has a live FK to
  `accounts_user` — meaning the audit app (T021-T025) has *also*
  already been generated/migrated, ahead of its own independent
  review. `apps/audit/models.py` has **not** yet been reviewed with
  the same scrutiny as `accounts/models.py` — flagged as the next
  thing to check, not yet done as of this entry.

**Outstanding as of this entry**: `apps/audit/models.py` review, the
remainder of Foundational (T021-T030 — audit app close-out, health
checks, test fixtures, final Docker Compose verification), and the
first real commit of application code (currently nothing staged).

**2026-08-01 (continued) — Foundational declared complete by Claude
Code; independently re-verified, with one real correction along the
way.** Claude Code reported T007-T030 fully "complete, tested, and
matches tasks.md and data-model.md," with T029/T030 having been
pulled forward alongside T018 (as previously disclosed) — meaning the
Option B checkpoint had effectively already arrived.

**A wrong explanation caught and corrected before it became false
record**: `curl -sI http://localhost:8000/health/` returned `HTTP/1.1
303 See Other` with a `Location:` header pointing at a locale-prefixed
URL. Initially attributed to Django's `LocaleMiddleware`. This was
**wrong**, caught by actually reading `config/urls.py` before letting
the explanation stand: there is no `i18n_patterns()` anywhere in the
file, so Django itself cannot be the source of that redirect — a plain
`path()` route never triggers locale redirection. Cross-checking
against the container's own logs (`Not Found: /health/`, correctly
timestamped to match automated healthcheck polling) confirmed the
*real* Django behavior is a plain `404` — fully expected, since
`apps/health/urls.py` is still the disclosed empty stub. The `303` +
an unusual `Server: Splunkd` header (gunicorn would say `Server:
gunicorn`, never Splunkd) point to host-network interception — a
corporate proxy/security agent between the terminal and the container,
unrelated to anything built here. Same fingerprint as an identical
false lead earlier in this overall project (a different repo,
same root cause). **Lesson**: don't accept a first plausible
explanation for an HTTP-layer anomaly without actually reading the
relevant source file first — this one would have gone into project
memory as fact if it hadn't been checked against `config/urls.py`
directly.

**`apps/core/permissions.py` (`HasRole`) reviewed in full — passes
cleanly, no gaps found.** This is the single highest-stakes file in
Foundational, since every RBAC requirement (FR-011, FR-012, FR-014,
FR-015, FR-016) and constitution Principle III route through it.
Verified line-by-line:
- No `is_superuser` reference anywhere — only `user.role` is ever
  checked, correctly preventing the "administrator = unrestricted
  bypass" anti-pattern.
- Deny-by-default implemented as a **positive** membership check
  (`role in allowed`), not a negative exclusion check — a null/blank/
  garbage role simply isn't `in` anything, no special-casing needed
  or forgettable.
- `has_object_permission` (detail routes) raises `NotFound()`
  directly; `has_permission` (collection routes) returns `False`,
  letting DRF's normal machinery produce a `403` — the exact 404-vs-403
  split FR-012 requires, implemented precisely, not approximated.
- No caching — `request.user.role` read fresh every call, correctly
  satisfying FR-016's immediate-effect requirement.
- Docstring cites the actual FR numbers and `research.md` section
  per design decision — genuinely traceable, not just restating the
  code in prose.

**A genuine "tested" vs. "verified" precision gap, caught and
corrected.** Ran the real pytest suite for the first time this
session:
```bash
docker compose exec web pytest apps/core/tests/ apps/accounts/tests/ apps/audit/tests/ apps/health/tests/ -v
```
Result: **`collected 0 items`**. Confirmed via
`find apps -path '*/tests/*.py' -not -name '__init__.py'` returning
completely empty — every `tests/` directory contains only an empty
`__init__.py`, no real test files exist anywhere yet. This directly
contradicts "tested" in Claude Code's completion summary. Coverage
report from the same run corroborates it: `apps/core/permissions.py`
shows **0% coverage** (17 statements, 17 missed) despite passing full
manual review — proof the file has never actually been exercised by
an automated test, only read and reasoned about.

**This is not a functional problem** — per `tasks.md`'s own phase
design, the paired test tasks for this code (T036-T041 for RBAC,
T048-T054 for audit, T058-T061 for health) are correctly scoped to
their respective User Story phases, not Foundational, so their absence
right now is expected, not a bug. The actual issue is purely one of
**precise language**: "tested" implies an automated suite ran and
passed; what actually happened is "implementation complete, manually
spot-checked via direct `psql`/`curl` inspection." Flagged directly to
Claude Code for confirmation rather than silently correcting the
runbook's own language and moving on.

**One unrelated, low-priority finding surfaced for free by the pytest
run**: `apps/accounts/models.py:35` — `RemovedInDjango60Warning:
CheckConstraint.check is deprecated in favor of .condition`. Harmless
under Django 5.1, worth fixing before any future Django 6.0 upgrade.
Not blocking, logged here so it isn't forgotten.

**Claude Code's "by design, not an oversight" defense — independently
checked, holds up.** In response to the tested-vs-verified question
above, it explained that every test file for this code (`test_models.py`,
`test_permissions.py`, `test_immutability_db.py`, `test_checks.py`,
etc.) is task-scoped to US2/US3/US4, not Foundational, and that
`tests/conftest.py`'s fixtures (`api_client`, `user_in_role`) have no
consumers yet since no test file imports them. Both claims verified
independently rather than accepted on tone:
```bash
grep -n "test_permissions\|test_models\|test_immutability_db\|test_checks" specs/001-foundation-platform-skeleton/tasks.md
grep -rn "api_client\|user_in_role" apps/ tests/ --include="*.py" | grep -v conftest.py
```
Every test filename genuinely maps to a `[US2]`/`[US3]`/`[US4]` label
in the real file, none appear under Foundational; the fixture-consumer
search came back completely empty. The explanation was accurate, not
just confidently phrased.

**`apps/audit/models.py` reviewed in full against `research.md` §5-§7
and `data-model.md` — this closes the last open item from this
section, and audit immutability is now confirmed across all four
layers it's supposed to have, not just asserted:**

| Layer | Mechanism | How verified |
|---|---|---|
| Model `save()` | Raises if `self.pk is not None` | Read directly in `models.py` |
| Model `delete()` | Raises unconditionally | Read directly in `models.py` |
| QuerySet `.update()`/`.delete()` | Custom `AuditLogQuerySet` overrides both to raise | Read directly in `models.py` — this is a genuine fourth layer beyond what the plan review originally described; without it, `AuditLog.objects.filter(...).update(...)` would silently bypass the model-level guards entirely, since queryset-level bulk operations never call individual `save()`/`delete()` |
| Database trigger | `BEFORE DELETE OR UPDATE` on `audit_auditlog` | **Confirmed live** via `psql -c "\d audit_auditlog"` against the real running database — listed directly under the table's `Triggers:` section as `audit_log_immutable BEFORE DELETE OR UPDATE ... EXECUTE FUNCTION audit_log_immutable()`, not just present in the migration file |

Also confirmed: `actor` uses `SET_NULL` with a separate
`actor_identifier`/`actor_role` snapshot (FR-021), `before`/`after`/
`context` are generic `JSONField`s with `target_type`/`target_id`
rather than app-specific columns (FR-023's reusability requirement),
and the composite index on `(target_type, target_id, timestamp)`
matches the chronological-retrieval query pattern `plan.md` specified.
**Zero gaps found.**

**Foundational is now genuinely, fully verified complete** — both of
its highest-stakes files (`apps/core/permissions.py` and
`apps/audit/models.py`) independently reviewed line-by-line against
the actual spec/plan/data-model, with the audit trigger specifically
confirmed at the live database level, not taken on the migration
file's word alone. Nothing committed to git yet as of this entry —
see the next session's first action.

### Session resume after laptop restart, and US2 test-writing (T036-T041)

**Environment resume check.** After a laptop restart two days later,
confirmed containers survived rather than assuming: `docker compose
ps` showed `db`/`redis` healthy and `web` running (same
already-diagnosed `unhealthy` status from the stub `/health/` view,
not a new issue). A ~8-hour gap in the container's own healthcheck
polling logs (visible via `docker compose logs web --timestamps`)
lines up with the laptop sleeping overnight, not a crash — Docker
doesn't count sleep time as downtime the way it would a real restart.

**Audit table investigation — real explanation, not a regression.**
A second row appeared in `audit_auditlog` (`id=2,
reviewer@example.com, compliance_officer`) that wasn't visible in the
last direct check before the restart. Investigated with a full
column `SELECT` rather than assuming something new had happened:
both rows' timestamps are from **2026-08-01**, 7 minutes apart —
i.e., both from the *original* Foundational session, not new activity
from the restart. `target_id = 99` on row 2 references a `User` that
does not exist in `accounts_user` (currently empty) — accidental,
free proof that FR-021 (audit survives referencing a deleted/never-
persisted entity) genuinely holds, not a data-integrity problem.

**T036-T041 (US2 tests) written and verified via direct pytest
execution**, not accepted from the completion summary alone:
```
collected 54 items
40 passed, 14 failed
```

**One real fix disclosed and verified**: `tests/conftest.py`'s shared
fixtures (`api_client`, `user_in_role`, `authenticated_client`) were
invisible to `apps/**/tests/*.py` because pytest only auto-loads a
`conftest.py` for files under its own directory tree. Moved to the
repo root (`conftest.py`). Verified via `git status` (shown as a
clean rename, not delete+add) and `find` (exactly one `conftest.py`
on disk, at the root) before trusting it worked.

**The claimed test breakdown was close but incomplete — a genuine
finding, not just a rubber-stamp.** Summary claimed "31 passing
(T036/T037/T041), 14 failing (T038-T040)" = 45 tests. Actual: 54
collected. The missing 9 are in `TestGetUserDetailRbacMatrix`
(`test_unauthenticated_refused_404` + 8 per-role variants) — all
**passing**, but not mentioned in either bucket. Investigation showed
why: `apps/accounts/views.py`/`urls.py` don't exist yet (T042-T044,
not yet run), so every request to `/api/users/{id}/` hits Django's
own generic "no URL matched" 404 — which coincidentally equals the
*expected* status code for these specific tests, even though the real
`HasRole`-driven object-permission logic they're supposed to verify
has never actually run. Confirmed this reasoning against the sibling
test in the same class (`test_system_administrator_allowed_200`,
expecting a real `200`) correctly failing for the same "no view yet"
reason — proving these 9 aren't secretly working, just accidentally
passing on the wrong mechanism.

**Follow-up flagged for once T042-T044 land**: re-run these 9 tests
and confirm they're passing for the *right* reason going forward -
e.g. temporarily break something in `HasRole`'s object-permission
path and confirm these tests actually catch it, rather than trusting
a still-green result without ever having proven it means what it
claims to mean.

**Genuinely good, independently-verified outcome**: `apps/core/
permissions.py` went from 0% to **100% test coverage** - the file
hand-reviewed and trusted two sessions ago is now proven by automated
tests covering its full behavior matrix (no superuser bypass,
deny-by-default, the 404-vs-403 split), not just reasoned about from
reading the source.

Two new low-priority deprecation warnings surfaced (logged, not
blocking): `CheckConstraint.check` (already known from Foundational)
and a new one, `factory_boy`'s `UserFactory._after_postgeneration`
save-behavior change coming in a future major release.

**Verdict**: proceeded to T042-T047 (views/serializers/urls
implementation) on the strength of this verification - the false-
positive-pass finding is a real thing to re-check later, not a reason
to block moving forward now.

### US2 completion (T042-T047) — a real bug found in the highest-stakes file, fixed and proven

T042-T047 implemented `apps/accounts/serializers.py`,
`apps/accounts/views.py`, `apps/accounts/urls.py`,
`apps/accounts/auth_views.py` (login/logout), and the
`customers`/`policies`/`claims` placeholder RBAC endpoints.

**The follow-up flagged at the end of the T036-T041 entry above came
true, in exactly the way anticipated.** Once real views existed and
DRF's actual request pipeline ran (rather than tests calling
permission methods directly), a genuine bug surfaced in
`apps/core/permissions.py` — the same file that was independently
line-by-line reviewed with zero gaps found, twice, in earlier
sessions. This is not a failure of those reviews; it's a real
methodological limit worth internalizing: **permission-class logic
that depends on framework dispatch order cannot be fully verified by
reading the source or by unit tests that call its methods directly —
only by exercising it through the real request pipeline.**

**The bug**: DRF calls `has_permission()` in `APIView.initial()`,
*before* the handler runs, for every route type. A `False` there
short-circuits straight to 403/401 without ever reaching
`get_object()` → `has_object_permission()`. The original
implementation's `has_permission()` did the full role check
unconditionally — meaning on detail routes, a wrong-role caller was
blocked one layer too early, and `has_object_permission()`'s
FR-012-mandated 404 logic was structurally unreachable. Caught via a
live check against the running container, not a unit test.

**The fix**: `has_permission()` now defers entirely to
`has_object_permission()` on detail routes (detected via a lookup
kwarg like `pk` being present in `view.kwargs`), while remaining the
sole, authoritative check on collection routes. Verified by:
- Reading the full corrected file directly (not just the diff) —
  confirmed nothing else changed alongside the fix
- Tracing the fix's logic against DRF's actual dispatch order by
  hand, including the edge case where the target object doesn't exist
  at all (still correctly 404s, via `get_object_or_404`, before
  `has_object_permission` even runs)
- 3 new regression tests specifically targeting the fixed dispatch
  path (`test_has_permission_defers_to_object_check_on_detail_route_
  for_unauthenticated`, `..._for_wrong_role`,
  `test_has_permission_still_denies_on_collection_route_with_view_
  present`)
- Most importantly: the 9 tests flagged in the previous entry as
  "passing for the wrong reason" (coincidental URL-not-found 404s)
  are now genuinely passing *with the real permission code exercising
  them* — `test_system_administrator_allowed_200` passing alongside
  all 8 `refused_404` variants in the same test class is the actual
  proof the fix works end-to-end, not just in isolation

**Second real bug, self-caught and fixed**: `PageNumberPagination`
without an explicit `page_size` silently returns a bare list instead
of the contract's `{"count", "next", "previous", "results"}` shape.
Caught via a live check against the running container, not pytest.
Fixed with a dedicated `UserListPagination(page_size=50)` class,
confirmed live afterward, and now has a dedicated regression test
(`TestGetUsersListShape::test_response_has_count_and_results_per_
contract`).

**Two test-authorship bugs, self-disclosed rather than hidden**: a
fixture-sharing collision made two supposedly-separate API clients
the same underlying object; and `force_authenticate()` pins a stale
Python object rather than re-reading the database, meaning the
FR-016 "no re-login needed" test needed to go through a real session
login (`/api/auth/login/`) to actually prove what it claims, not just
call `force_authenticate` twice.

**Final verified state for T036-T047**, direct pytest execution:
```
96 passed, 0 failed, 99 warnings in 4.45s
```
Coverage: `apps/core/permissions.py` 100%, `apps/accounts/views.py`
100%, `apps/accounts/serializers.py` 100%, `apps/accounts/
auth_views.py` 100%, `apps/audit/services.py` 100% (incidental gain
from the login/logout audit-trail work). Overall project coverage:
**84%** (417 statements, 66 missed), up from 71% at the end of
T036-T041.

Test coverage added beyond the original T036-T047 scope, since these
were genuinely at 0% otherwise: auth login/logout
(`test_auth_views.py`, 6 tests) and the `user.deactivated`/
`user.updated` audit branches.

`tasks.md` now shows T036-T047 all `[X]`. Committed and pushed.

### US3 completion (T048-T057, +T053a/T053b) — a second real bug, in the other highest-stakes file

Implemented `apps/audit/serializers.py`, `apps/audit/views.py`
(`AuditListView`, `AuditHistoryView`), `apps/audit/urls.py`, and a new
migration. Test-first sequence followed correctly: all of
T048-T054/T053a/T053b written and confirmed red (routes didn't exist)
before any implementation, then T055 → T056 → T057 turned them green.

**A second genuine bug, in `apps/audit/models.py` — the other file
independently deep-reviewed with zero gaps found weeks earlier.**
Together with US2's `permissions.py` bug, this confirms the lesson
from that entry isn't a one-off: **static review of correctness logic,
however careful, cannot substitute for exercising it against real
interactions between subsystems** — here, specifically, the
interaction between two independently-correct-looking pieces (the
`SET_NULL` FK behavior for FR-021, and the append-only trigger for
FR-019) that had never been tested *together* until a real user
deletion actually needed to cascade through both at once.

**The bug**: `AuditLog.actor` uses `on_delete=SET_NULL` specifically
so audit entries survive actor deletion (FR-021, and directly
verified via a real cascade in `test_deleting_actor_leaves_audit_
entries_readable_with_actor_null`). But the existing `BEFORE UPDATE
OR DELETE` trigger (migration `0002`) rejected *any* `UPDATE`
unconditionally — including the exact `UPDATE ... SET actor_id =
NULL` that Django's own cascade issues when the referenced user is
deleted. Deleting any user who had ever taken an audited action would
have hard-failed with a database exception instead of cleanly nulling
the FK as designed.

**The fix**: migration `0003_audit_log_immutable_trigger_allow_actor_
null.py` replaces the trigger function with a narrow, explicit
exception — verified in full, not summarized:
```sql
IF NEW.actor_id IS NULL
    AND NEW.timestamp IS NOT DISTINCT FROM OLD.timestamp
    AND NEW.actor_identifier IS NOT DISTINCT FROM OLD.actor_identifier
    -- ...all 8 other columns, each IS NOT DISTINCT FROM its old value
THEN
    RETURN NEW;
END IF;
RAISE EXCEPTION 'audit_auditlog records are append-only...';
```
Verified this genuinely narrows to *only* the legitimate case, not a
general loosening: every column except `actor_id` must be provably
unchanged, and `actor_id` must specifically be transitioning to
`NULL` (not just changing). `IS NOT DISTINCT FROM` (rather than `=`)
is the correct operator choice here, since it handles `NULL`-to-`NULL`
comparisons correctly on the nullable `before`/`after`/`context`
columns, which a naive `=` would get wrong (SQL's `NULL = NULL`
evaluates to `NULL`, not `true`). Confirmed live via `psql`, not just
read from the migration file - the trigger is genuinely active on the
running table.

**`AuditHistoryView`'s deliberate deviation from the standard
`GenericAPIView.get_object()` pattern** — read and verified, not just
accepted: since a target's audit history can legitimately be an empty
queryset (T053a explicitly requires `200`/`count: 0`, not `404`, for
that case), the standard `get_object()`-based 404 flow would be wrong
here. The view instead declares `lookup_url_kwarg` purely as the
signal `HasRole` checks for route-type detection, then calls
`check_object_permissions(request, None)` explicitly — getting the
correct RBAC-driven 404 for unauthorized callers while preserving
T053a's empty-but-permitted 200 case. A well-reasoned, correctly
narrow deviation, not a shortcut.

**A live-verification false alarm, correctly chased down and
resolved rather than left ambiguous**: an ad-hoc `urllib`-based
end-to-end check showed `POST /api/audit/` returning `403` instead of
the expected `405`. Investigated properly rather than assumed
either "bug" or "fine": confirmed the test admin genuinely had
`system_administrator` role (ruling out a permissions explanation),
traced DRF's actual `dispatch()` order (`http_method_not_allowed` is
only reached *after* `initial()`'s permission checks, so a passing
permission check should reach it), then re-tested with a fresh
cookie jar and found the real cause: Django's `CsrfViewMiddleware`
rejecting the unauthenticated-token `POST` before DRF's view logic
ever ran — correct, expected framework behavior for session-
authenticated browser-style requests, not a bug. The pytest suite's
`APIClient` handles CSRF exemption transparently for tests, which is
why the real suite correctly saw `405`. Resolved with a specific,
verified explanation, not left as an unresolved discrepancy.

**Final verified state**, direct pytest execution:
```
143 passed, 0 failed, 175 warnings in 5.51s
```
Coverage: `apps/audit/views.py` 100%, `serializers.py` 100%,
`services.py` 100%, `models.py` 97% (one line, likely an unreachable
defensive branch). **Overall project coverage: 90%** (467 statements,
45 missed), up from 84% after US2.

**New this session: a project-scoped Claude Code memory system
discovered and reviewed.** Separate from this repo (stored at
`~/.claude/projects/-home-bijut-insurance-ai-platform/memory/`, not
version-controlled), Claude Code wrote two persistent memory files
this session: one capturing the trigger/`SET_NULL` gotcha technically
(for its own future reference), and one inferring this project's
established verification style (independent re-verification, precise
"tested vs. verified" language, mechanism-over-outcome explanations) -
reviewed directly and confirmed as an accurate read of the pattern
this runbook has enforced throughout, not something explicitly
requested. Worth remembering this exists and lives outside version
control - the substance worth keeping durably belongs here, in the
tracked runbook, not only in that untracked store.

`tasks.md` now shows T048-T057, T053a, and T053b all `[X]`. Committed
as `a4340df` (10 files, 591 insertions) and pushed.

### US4 completion (T058-T064) — a third real bug, and a weeks-old mystery finally closed

Implemented `apps/health/checks.py` (rewritten), `apps/health/views.py`,
`apps/health/urls.py`, and the Docker Compose `web` healthcheck (T064,
though pulled forward earlier alongside T029/T003 - see the
Foundational section above). Test-first sequence followed correctly.

**A third real bug, continuing this session's established pattern**:
`check_database()` originally reused Django's shared pooled database
connection, which has no `connect_timeout` configured. Verified
directly (not inferred) that a raw `psycopg` connection to an
*unroutable* host (as opposed to one that actively refuses the
connection) hangs indefinitely at the OS/TCP level - a genuine
violation of FR-027's per-probe 2-second bound and SC-006's 5-second
overall bound, specifically in a network-partition scenario a mocked
"raises an exception" test would never surface. **Fixed** by rewriting
`check_database()` to open its own fresh, explicitly-bounded connection
(`connect_timeout=2`) per call via a context manager, mirroring
`check_cache()`'s existing pattern - reviewed in full and confirmed
the connection is properly closed after use, not leaked. A dedicated
test (`test_check_database_against_unroutable_host_returns_error_
within_timeout`) verifies this against a genuinely unroutable address,
not a mock.

**Final verified state**: `157 passed, 0 failed` (up from 143 after
US3), `apps/health/checks.py` and `apps/health/views.py` both 100%
coverage. **Overall project coverage: 96%** (482 statements, 21
missed), up from 90%.

**Docker's own `web` service healthcheck genuinely reports healthy for
the first time this project** - confirmed via `docker inspect
insurance-ai-platform-web-1 --format '{{json .State.Health}}'`
showing `"Status": "healthy"`, `"FailingStreak": 0`, and four
consecutive real probe cycles each with `"ExitCode": 0`. This resolves
cleanly a mismatch that existed since Foundational: the healthcheck
was pulled forward before `/health/` had a real implementation, so it
had been correctly reporting `unhealthy` against a stub for the
entire project until this moment.

**The weeks-old `303`/`Server: Splunkd` mystery - fully diagnosed and
closed, not just deferred again.** This exact response has recurred
intermittently since the very first Docker smoke test at the start of
this whole project, always attributed provisionally to "probably
host-network interference" without ever being conclusively proven.
This session finally ran it to ground with a systematic elimination:

- Docker's own healthcheck (running **inside** the container's network
  namespace, using Python's `urllib` per `contracts/health.md`) gets a
  real response and reports healthy - proving the Django application
  itself is, and has been, entirely correct.
- A `curl` from the **host** shell, at the exact same moment against
  the exact same running container, gets the familiar `303 See Other`
  with `Location: .../en-US/health/` and `Server: Splunkd` - a header
  no Django/gunicorn response would ever send.
- Systematically ruled out every client-side explanation: `env | grep
  -i proxy` empty (no proxy env vars), `127.0.0.1` fails identically to
  `localhost` (rules out DNS/hostname-specific resolution), `curl
  --noproxy '*'` makes no difference (rules out any curl-configurable
  proxy setting).

**Conclusion**: this is host-level network interception - almost
certainly Splunk-branded endpoint security/traffic-inspection software
installed on the Windows host, operating below the layer any
WSL-side or curl-side configuration can see or bypass, intercepting
loopback traffic to at least port 8000 regardless of hostname.
**Not fixable from within this project or WSL alone.** Documented here
as a closed, understood environmental fact rather than an open
mystery: manual host-side `curl`/browser checks against local dev
ports on this machine will show this interception; the application
and Docker's own internal healthchecks are unaffected and are the
correct source of truth going forward. Worth raising with IT/security
for a local-dev-port allowlist exception at some point, not urgent.

`tasks.md` now shows T058-T064 all `[X]`. Committed and pushed.
Per the task list's dependency note, this also unblocks US1
(T031-T035), whose own checkpoint queries `/health/` - the deliberate
reason US4 was completed before US1 in this session.

### US1 completion (T031-T035) — the lightest sub-phase, verified with the same rigor as the heaviest

Implemented `apps/core/tests/test_settings.py` (T032),
`tests/integration/test_environment.py` (T031), and `README.md`
(T033) at the repo root - the first top-level project README this
repo has had. T034 (commented-out db port mapping) was confirmed
already satisfied from Foundational, needing no new work.

**T035's two success criteria were verified live, not asserted** -
consistent with the standard set by US4's unroutable-host test and
the network-isolation check below:

- **SC-010 (data survives restart)**: counted a real user row before
  `docker compose down`/`up`, confirmed the *same* row (not a fresh
  one) existed after - genuine persistence proof, not an assumption
  from "the volume is declared as named, so it should persist."
- **SC-011 (no external network dependency)**: brought the stack up
  under a temporary `internal: true` network override, confirmed
  outbound connectivity was genuinely blocked (`Network is
  unreachable` - the real failure mode, not silently succeeding some
  other way), and confirmed `/health/` still returned `200` under
  that actual hostile condition. The override was fully reverted
  afterward - independently confirmed via `git diff docker-compose.yml`
  returning empty before committing, not just trusted from the
  session's own "cleaned up" claim.

**`README.md` reviewed in full, not just confirmed to exist.** Both
gotchas repeatedly hit across this session are surfaced clearly and
actionably, not just mentioned in passing:
- The `.env`-overwrite gotcha (§7, `readme-runbook-phase1.md`'s own
  forward-note from the Foundational session) - the README gives a
  concrete pre-check command (`test -f .env && echo ...`) rather than
  just a warning.
- A **new** gotcha, not previously logged in this runbook: **no
  dev-volume-mount** - the production Docker image doesn't
  bind-mount source code, so running tests or the server against a
  stale image after a code change will silently exercise old code
  unless the image is explicitly rebuilt. Worth flagging here since
  this runbook hadn't named this specific failure mode before, even
  though its symptoms (confusing stale-behavior debugging) are exactly
  the kind of thing this project's earlier sessions could plausibly
  have hit without recognizing it for what it was.

**Final verified state**: `168 passed, 0 failed`, 96% coverage
(unchanged from US4 - T031/T032 exercise existing config/settings
code paths rather than adding new production code). Well under
SC-008's 2-minute bound at ~22 seconds.

`tasks.md` now shows T031-T035 all `[X]`. Committed as `f254a36`
(4 files, 247 insertions) and pushed. **Only US5 (T065-T068) and
Polish (T069-T072) remain to complete Phase 1 entirely** - 67 of 74
tasks done (90.5%).

---

## 6. Validation — how to actually confirm Phase 1 works

⏳ PENDING — this section fills in once implementation exists. Planned
validation, mirroring the rigor used for the Docker/Compose project
earlier in this overall effort:

- [ ] `docker compose up` brings up Postgres + Redis cleanly, both
      report healthy
- [ ] **Tests run via `docker compose exec web pytest`, not host-side**
      — the host WSL Python (3.12.3) is a different interpreter than
      the container's (3.13); a host-side pytest run would test the
      wrong runtime entirely and silently produce misleading results
- [ ] **A local `psql` connection requires uncommenting the port
      mapping** in `docker-compose.yml` first — Postgres/Redis ports
      are deliberately not published to the host by default
- [ ] Django migrations run without error against the real Postgres
      container (not SQLite — confirms the actual configured stack
      works, not a fallback)
- [ ] Custom `User` model: create one user per each of the 9 roles,
      confirm role field persists correctly
- [ ] RBAC: attempt a cross-role action that should be denied (e.g. a
      Customer Service user trying to access a fraud-investigation-only
      endpoint) and confirm it's actually rejected server-side, not
      just hidden in the UI
- [ ] `AuditLog` model: confirm at least one action writes an audit
      entry, and confirm entries are append-only (no update/delete
      path exposed)
- [ ] Health-check endpoint responds correctly
- [ ] `pytest` runs and passes against whatever test coverage
      `/speckit-implement` produced
- [ ] `git status` clean, meaningful commit history, nothing
      accidentally leaked (repeat the same CSV/secret-scanning
      discipline used in Phase 0 and the constitution setup)

---

## 7. Known issues / things that came up

**2026-07-30 — First `/speckit-specify` write was rejected, cause
unclear.** The terminal log showed `"User rejected update to
specs/001-foundation-platform-skeleton/spec.md"` — the file write did
not happen, and the on-disk file remained the raw, unfilled Spec Kit
template (confirmed by uploading it and finding only placeholder text
like `[FEATURE NAME]`, generic `FR-001` examples, no mention of
Django/RBAC/AuditLog/pytest). Whether the rejection was intentional
(pausing to review before approving) or accidental (a stray Esc/No)
wasn't clear from the transcript alone.

**Silver lining**: the terminal log captured the diff of what *would*
have been written before the rejection, so the drafted content itself
could still be reviewed. It held up well against the constitution
compliance checklist (§5.1) — explicit server-side RBAC language,
explicit append-only audit log acceptance criteria, explicit Factory
Boy test-data builders — even though it never got saved. Re-ran
`/speckit-specify` with the same prompt to actually get a saved
version; see §5.1 for the real, saved result.

**Lesson for later phases**: always confirm a write actually landed
(`cat` the file, or check `git status` for a new/modified file) rather
than trusting the terminal transcript alone — a rejected write can
still display convincing-looking diff content that never reaches disk.

**Resolution confirmed**: re-ran the same `/speckit-specify` command,
approved the write, then verified with a direct `cat` (not terminal
trust) — this time the real content was genuinely on disk. See §5.1.

**Second rejection, same session, different file**: immediately after
`spec.md` succeeded, the write to
`specs/001-foundation-platform-skeleton/checklists/requirements.md`
(the quality checklist) was *also* rejected — same
`"User rejected write to..."` pattern. Two rejections in one session
on substantive content is enough to be a real pattern, not
coincidence — possible causes: reviewing before approving each time
(fine, just means don't assume it landed), or a stray keystroke/paste
interaction hitting the approval menu unintentionally.

**Resolved**: regenerated with a deliberate pause-before-approving
habit (read the menu, confirm option 1, approve as a separate
intentional action rather than a reflex keystroke) and it succeeded on
the first attempt. Verified via direct `cat`, not terminal trust — see
§5.1. Not fully conclusive that this *was* the root cause (only one
clean data point), but no further rejections occurred once this habit
was adopted, so worth keeping as standard practice for the rest of
this project regardless.

**⏩ Forward-note for T033 (User Story 1's setup documentation, not yet
written)**: while manually working through Foundational's database
setup, discovered a real gotcha that T033's eventual `README.md`/setup
docs MUST warn about: **`cp .env.example .env` overwrites an existing
`.env` unconditionally**, with no prompt and no backup. This bit us
directly — `db`/`redis` had already started once using one set of
credentials, then `.env` got blindly overwritten with placeholder
values from `.env.example`, creating a real mismatch between what
Postgres's volume was actually initialized with and what `.env`
claimed. Required a full `docker compose down -v` + fresh `.env` +
fresh `up` to resolve cleanly. **When T033 is written**, it must
explicitly say: check whether `.env` already exists before copying the
example over it, and if the database volume already exists, changing
`.env`'s credentials afterward requires wiping the volume (`down -v`)
to actually take effect — Postgres does not re-read `.env` and update
an already-initialized user/password on restart alone. Also worth a
one-line placeholder-sweep habit in the docs: `grep -iE
"changeme|placeholder|your-|example" .env` should return nothing
before trusting the file.

---

## 8. Progress log

Dated entries, appended as work happens — newest at the bottom.

**2026-07-30** — Phase 1 runbook created. Prerequisites confirmed
(clean repo, correct working directory, Claude Code authenticated via
Pro subscription — `/status` confirmed `$0.0000` cost, 20% of current
5-hour session used, 16% of current week used, +50% weekly limits
promo active through Aug 19). Model strategy decided: Opus for
specify/plan, Sonnet for tasks/implement, no mid-session switching.
`/speckit-specify` command prepared and about to run.

**2026-07-30 (continued)** — `/speckit-specify` completed for
`001-foundation-platform-skeleton`, after two rejected writes (spec.md
once, the requirements checklist once) that were resolved by verifying
every write directly with `cat` rather than trusting the terminal
transcript, and by deliberately pausing before approving each write
prompt. Both `spec.md` and `checklists/requirements.md` independently
verified on disk with real content. Spec reviewed against the
constitution compliance checklist — passes on audit logging,
server-side RBAC, and testing infrastructure, with technology names
(pytest/Factory Boy) correctly deferred to the plan phase rather than
named in the spec. Ready to proceed to `/speckit-plan`.

**2026-07-30 (continued)** — Committed and pushed the verified spec
artifacts (commit `8327ed4`). Caught two real process gaps along the
way: (1) the runbook file itself hadn't actually been saved to the WSL
machine despite being shown as ready in chat — always `ls` to confirm
before trusting a "file is ready" claim; (2) an unexplained extra file
(`spec.md-unfilled-SpecKit-template`) appeared in `git status` output,
removed as presumed debug residue without its content ever being
verified — a minor gap in rigor worth naming rather than glossing
over. Final state confirmed clean via `git status` after push. See
§5.1a for full command-by-command detail.

**2026-07-30 (continued)** — `/speckit-plan` completed for
`001-foundation-platform-skeleton`, clean run with no rejected writes
(contrast with the specify step). 8 files created; `plan.md`,
`research.md` (all 12 decisions), and `contracts/users.md`
deep-reviewed and verified against `spec.md`'s actual FR-XXX numbers.
Verdict: strong — Constitution Check passed twice (pre- and
post-design), every principle-relevant requirement traced to a
specific technical decision with rejected alternatives shown, not
just restated. FR-017 specifically chased down and confirmed present
in `contracts/users.md` after not appearing in the two main files.
Two operational gotchas added to §6's validation checklist (tests must
run in-container; DB ports not published by default). Ready to
proceed to `/speckit-tasks`.

**2026-07-30 (continued)** — `/speckit-tasks` completed for
`001-foundation-platform-skeleton` on Sonnet, new session per the
model strategy. 72 tasks across 8 phases, clean write on the first
attempt (no rejections, no stray files — third clean file-hygiene run
in a row after the earlier specify-step issues). Two specific claims
independently verified via `grep`/`sed` directly against the real
file rather than taken on summary: the User-model-first-migration
warning appears 5 separate times, and the US1/US4 reordering's stated
reasoning matches the actual recommended sequence (US4 at position 3,
before US1 at position 4). Real cost data captured for the first time
this session: `/speckit-plan` (Opus) consumed 44-53% of the 24h usage
window vs. `/speckit-tasks` (Sonnet) at $0.87 notional cost for 297
lines — real evidence behind the model strategy in §4, not just
theory. Also caught session usage at 75% mid-review, prompting the
new "check `/status` before, not just after, heavy steps" habit now
documented in §4.

**2026-07-31 (continued)** — `/speckit-analyze` reviewed: no CRITICAL
findings, 2 HIGH (C1: missing formal Constitution Exceptions
cross-reference for the Celery/pgvector deferrals; F1: missing test
for the audit-history empty-result case), 2 MEDIUM (F2, F3), 2 LOW
(D1, A1). Applied fixes for C1 and F1 via Claude Code's own suggested
remediation, verified with `git diff` before committing — the fix also
incidentally closed F2 (T053b) as a bonus, correctly noticed rather
than silently accepted. F3/D1/A1 left open as genuinely non-blocking.
Committed as `0002c15`.

**2026-07-31 (continued)** — `/speckit-implement` started, scoped
explicitly to Phase 1+2 only (Setup + Foundational, stopping before
any User Story), per the Option B checkpoint decision. Caught a real
gap in `tasks.md` itself mid-implementation: `config/urls.py` (T012,
Foundational) mounts each app's `urls.py`, but those files are only
*created* by later, out-of-scope User Story tasks (T044/T057/T063/
T046) — Django would fail to boot on the missing imports. Resolved by
stubbing minimal per-app `urls.py` files now (Claude Code's own
recommended option), each intended to be populated by its real task
later. Also hit and resolved a real `.env` handling mistake during
manual database setup — see the forward-note in §7 for the full
gotcha, now flagged for T033's future documentation. Database and
Redis confirmed healthy with genuinely random (non-placeholder)
credentials via a direct `psql` connection test before proceeding to
T018 (the accounts migration). Migration generation itself still in
progress as of this entry.

**2026-08-01 (continued)** — `apps/accounts/models.py` and its
migration independently verified, not just accepted from Claude
Code's own summary: reviewed the model source line-by-line against
`plan.md`/`data-model.md`, then confirmed the applied schema directly
via `psql -c "\d accounts_user"` against the live container database.
Everything matched exactly — all 9 roles, the `user_role_valid` check
constraint, non-nullable `role` (the real DB-level enforcement of
deny-by-default), unique+indexed `email`. Along the way: `db`/`redis`
were found stopped between turns, restarted and re-verified rather
than assuming prior state still held; confirmed via `docker volume ls`
that the Postgres volume survived the restart, meaning a
previously-disclosed stuck `AuditLog` test row (id=1, from Claude
Code's own trigger testing) is genuinely still present — decided to
keep it as informal proof-of-immutability rather than reset. Also
discovered the audit app's table already exists in the live schema
(a live FK from `audit_auditlog` to `accounts_user`), meaning
`apps/audit/models.py` has been generated ahead of its own review —
flagged as the next thing to check. Nothing committed yet; Foundational
still has T021-T030 remaining.

**2026-08-01 (continued)** — Foundational (T007-T030) declared
complete by Claude Code. Independent re-verification found the
implementation genuinely solid — `apps/core/permissions.py`'s
`HasRole` reviewed line-by-line with zero gaps (no superuser bypass,
correct deny-by-default, correct 404-vs-403 split, no role caching) —
but caught two real precision issues along the way. First: an
earlier-recorded explanation for a `/health/` HTTP anomaly
(attributed to Django's `LocaleMiddleware`) was wrong, caught by
actually reading `config/urls.py` before letting it stand — the real
`404` is expected/correct, and the misleading `303` traces to
host-network interception (matching an identical false lead from
earlier in this project), not Django. Second: Claude Code's own
"complete, tested" summary was overstated — running the real pytest
suite returned `collected 0 items`, confirmed via a direct file search
that no test files exist yet anywhere, only empty `__init__.py`
stubs. Not a functional problem (the paired test tasks are correctly
scoped to later User Story phases per `tasks.md`'s own design), but
"tested" should have said "manually verified" — flagged directly to
Claude Code for confirmation rather than silently corrected. Also
logged a low-priority Django 6.0 deprecation warning surfaced by the
pytest run. Nothing committed yet.

**2026-08-01 (continued, session close)** — Claude Code's
"tested-vs-verified was by design" explanation independently checked
against `tasks.md` and the actual test-consumer search — confirmed
accurate. `apps/audit/models.py` reviewed to the same standard as
`permissions.py`: four-layer immutability confirmed (model `save()`,
model `delete()`, custom queryset override, and — critically —
the Postgres `BEFORE DELETE OR UPDATE` trigger confirmed **live**
against the running database via `psql`, not just present in a
migration file). Zero gaps found in either file. Foundational
(T001-T030) is now genuinely, independently verified complete — both
of its highest-risk components checked line-by-line against spec/plan/
data-model, not accepted on Claude Code's summary alone. Session ending
with the first commit of actual application code still pending —
first action for the next session. Started `/speckit-implement`
scoped correctly to US2 (T036-T041) as the next step once resumed.

**2026-08-02** — Resumed after a 2-day laptop restart. Confirmed
containers survived (not assumed) before proceeding. Investigated an
apparently-new second audit row and confirmed via timestamps it was
pre-existing from the original Foundational session, not new activity
- along the way found accidental proof that FR-021 (audit survives a
non-existent/deleted referenced entity) genuinely holds. Wrote and
verified T036-T041 (US2 tests) via direct pytest execution: 54
collected, 40 passed, 14 failed. Fixed a real `conftest.py` visibility
bug (moved repo-root). Caught a genuine gap in the completion
summary: 9 tests were passing for an unintended reason (Django's
generic 404 for a nonexistent URL coincidentally matching the
expected status code, not real permission logic that doesn't exist
yet) - flagged for re-verification once T042-T044 land. `apps/core/
permissions.py` reached 100% test coverage, up from 0%. Proceeded to
T042-T047 (views/serializers/urls implementation).

**2026-08-02 (continued)** — T042-T047 (US2 implementation) complete.
The follow-up flagged in the previous entry came true: real views
exposed a genuine bug in `apps/core/permissions.py` (twice-reviewed,
zero gaps found on paper) that only a live request through DRF's
actual dispatch pipeline could surface — `has_permission()` was
blocking wrong-role detail-route requests before
`has_object_permission()`'s FR-012 404 logic could ever run. Fixed
by deferring to object-level checks on detail routes; verified via
full-file re-read, hand-traced dispatch order, 3 new regression
tests, and confirming the previously-flagged 9 false-positive-pass
tests now pass for the real reason. Second bug self-caught and fixed:
`PageNumberPagination` without `page_size` silently broke the
contract's response shape. Two test-authorship bugs self-disclosed
(fixture-sharing collision, `force_authenticate` staleness requiring
real session login for the FR-016 test). Final state: 96/96 tests
passing, 84% overall coverage. Committed and pushed.

**2026-08-03** — T048-T057 (US3: audit trail, including analyze-
remediation tasks T053a/T053b) complete. A second real bug found in
previously-trusted code, confirming the US2 lesson generalizes: the
append-only trigger (correct in isolation) and the `SET_NULL` actor
FK (correct in isolation) had never been exercised *together* -
deleting a user who'd taken an audited action would have hard-failed
instead of cascading cleanly. Fixed via a new migration with a
narrowly-scoped trigger exception, verified both by full-file read
(confirmed the SQL condition genuinely narrows to only the legitimate
case) and by a real cascade test. `AuditHistoryView`'s deliberate
`get_object()` bypass (needed for T053a's empty-history-is-200 case)
reviewed and confirmed correctly scoped. A live-verification anomaly
(POST returning 403 instead of 405) was investigated to a specific,
confirmed root cause (Django CSRF middleware, not a real bug) rather
than left ambiguous. Final: 143/143 tests passing, 90% coverage, up
from 84%. Discovered and reviewed a project-scoped Claude Code memory
system (untracked, outside the repo) - confirmed its inferred
"user verification style" memory accurately reflects this runbook's
established pattern. Committed as `a4340df`, pushed.

**2026-08-05** — T058-T064 (US4: health check) complete. A third real
bug found, same established pattern: `check_database()` used Django's
untimeout'd pooled connection, which hangs indefinitely (not just
slowly) against a genuinely unroutable host - a real FR-027/SC-006
violation a mocked-failure test alone would never catch. Fixed with a
fresh, explicitly-bounded connection per call, verified against a real
unroutable address. 157/157 tests passing, 96% coverage, up from 90%.
Docker's own `web` healthcheck genuinely reports healthy for the first
time this project. Separately: finally ran the weeks-old `303`/
`Server: Splunkd` anomaly to ground with a systematic elimination
(proxy env vars, `127.0.0.1` vs `localhost`, `--noproxy`) - conclusively
host-level network interception (likely Splunk-branded endpoint
security software), not an application bug, proven by Docker's own
internal healthcheck getting a correct response at the same moment a
host-side `curl` doesn't. Documented as closed/understood rather than
left as a recurring unexplained asterisk. Committed and pushed. US1
now unblocked, as planned.

**2026-08-05 (continued)** — T031-T035 (US1: environment runs
locally) complete. Lightest sub-phase, but held to the same live-
verification standard as the heaviest: SC-010 (restart persistence)
proven by tracking a specific real row across an actual `down`/`up`
cycle, and SC-011 (no external network dependency) proven by
deliberately isolating the stack (`internal: true` override) and
confirming both a genuine outbound failure and a still-successful
`/health/` response under that real hostile condition - with the
override's full reversion independently confirmed via an empty
`git diff docker-compose.yml`, not just trusted. First top-level
`README.md` for the repo, reviewed in full: surfaces the known
`.env`-overwrite gotcha with a concrete pre-check command, plus a
newly-identified gotcha (no dev-volume-mount, meaning a stale image
can silently serve old code) not previously logged anywhere in this
runbook. 168/168 tests passing, 96% coverage, ~22s runtime. Committed
as `f254a36`, pushed. 67 of 74 tasks done (90.5%) - only US5 and
Polish remain.
