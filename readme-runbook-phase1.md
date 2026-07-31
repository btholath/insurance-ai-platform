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

**Result**: ⏳ PENDING

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
