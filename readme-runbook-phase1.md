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

**Result**: ⏳ PENDING — paste the actual output here once run, including
where the spec file was written.

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

⏳ PENDING — filled in as real problems surface, same honest-disclosure
approach as `readme-setup-conclusions.md` (e.g. the Claude Code
billing/API-key issue, the constitution's dot-vs-hyphen syntax bug) —
if something breaks, it gets documented here with the real fix, not
smoothed over.

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
