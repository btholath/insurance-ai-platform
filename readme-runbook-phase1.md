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

**What to check**: does the plan actually reference the ratified
constitution's tech stack constraints (Python 3.13, Django 5.x, DRF,
PostgreSQL 16+, Redis, Celery)? A plan that silently substitutes a
different stack is a constitution violation, not a minor deviation.

**Result**: ⏳ PENDING

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

**Result**: ⏳ PENDING

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
