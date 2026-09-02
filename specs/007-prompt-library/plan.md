# Implementation Plan: Prompt Library

**Branch**: `007-prompt-library` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-prompt-library/spec.md`

## Summary

A new `apps/prompts` app holding a code-resident, versioned library of LLM
prompt templates, each declaring exactly which structured business fields it may
draw from. That declaration is the grounding contract Phase 4b's post-generation
validator will check generated text against, field by field. Nothing in this
phase calls a language model.

The work is small in volume and unusually load-bearing in correctness: roughly
one new Django app with no new database table, one registry entry, two API
routes, and a validation layer whose entire job is to make a class of mistake
impossible rather than merely unlikely.

Six decisions carry the design, each recorded in [`research.md`](./research.md):

1. **Phase 0 has 7 templates, not 18** (§1). The Phase 0 repository was not
   missing — it is at `~/insurance-ai-platform-phase0`, outside this project's
   directory, which is why the spec pass could not see it. Read directly:
   `app.py:43-101` defines 7 keys; `readme-setup-conclusions.md:192` says "All 7
   prompt templates tested." Both model findings — `llama3.1:8b` clean,
   `phi3:mini` disqualified for hallucinating claim IDs and policy numbers —
   are confirmed verbatim (`readme-setup-conclusions.md:121-124`). **FR-016 and
   the Assumptions bullet need the count corrected** (see Complexity Tracking).

2. **Five of the seven templates cannot be ported verbatim** (§2).
   `Client_Feedback`, referenced by 5 of 7, has no field anywhere in the
   platform — nor does `Last_Interaction`. They are Phase 0 CSV columns the
   production schema never adopted. The five are rewritten to drop the
   reference and record that divergence in their own metadata, rather than
   deferred (which would leave a 2-template library) or accommodated by adding
   a `feedback` column to `Customer` (which would invert the dependency the
   grounding contract exists to establish).

3. **The whitelist is a frozenset pinned by exact equality**, mirroring
   `apps/risk/tests/test_rules.py:270` (§3). Verified attack surface it closes:
   `User.password`, `User.is_superuser`, `User.role`, and `AuditLog.before`/
   `.after` are all genuinely-existing fields that FR-004–008 alone would have
   admitted. `AuditLog.before` is the sharpest — it holds prior-state snapshots
   of *other* records, so one approved declaration re-exposes arbitrary fields
   of arbitrary types through a single validating entry.

4. **Role sets are a genuinely fifth shape: view = all 9 roles, write =
   System Administrator alone** (§4). First universal view set on the platform,
   and first single-role write set. A template contains no customer data — only
   field *names*, never field *values* — so the restrictions protecting the
   other four modules have nothing to protect here. Executive Leadership, absent
   from all four existing view sets, can read prompt templates.

5. **Placeholders are `{RecordType.field_name}`, resolver but no renderer**
   (§5, §6). A qualified placeholder makes the body self-describing, so FR-005's
   both-directions check is a set comparison with no inference step — necessary
   because three eligible types already share field names (`archived_at` on
   Customer/Policy/Claim). The resolver (declaration → value) is what 4b's
   validator actually needs; the renderer (values → finished prompt string) has
   exactly one consumer that does not exist yet, so it waits for 4b.

6. **Audit refusals and writes, not successful reads** (§7). Verified: no module
   on this platform audits successful reads — `apps/risk/views.py` has zero
   `record_action` calls. FR-015's literal wording would make the prompt library
   the only module logging a row per GET, which contradicts FR-013/FR-014's
   premise that it behaves as the registry's fifth consumer. **FR-015 needs
   narrowing** (see Complexity Tracking).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Django 5.1, Django REST Framework 3.15 — both
unchanged. **This feature adds no new dependency.** No LLM client, no template
engine, no parser library; placeholder extraction is one `re` pattern from the
standard library.

**Storage**: PostgreSQL 16 — **no new table, no migration**. The library is a
Python module (`research.md` §6); its only database-visible effect is additional
rows in the existing `audit_auditlog` table via the existing refusal path.

**Testing**: pytest + pytest-django, Factory Boy where fixtures are needed
(most tests here need no database at all — the library is plain values, the same
property `apps/risk/rules.py` deliberately maintains).

**Target Platform**: WSL Ubuntu on Windows 11, Docker Compose — unchanged.

**Project Type**: Django web service (single project, `apps/*` layout).

**Performance Goals**: Library validation runs once at app-ready over 7
templates; it must not measurably affect startup. API reads are served from an
in-memory tuple with no query — the list route does zero database work.

**Constraints**: No language-model call anywhere in this feature or its tests
(FR-019, SC-008). No new dependency. No modification to the four existing
`audit_routes` entries (FR-014, SC-006).

**Scale/Scope**: 7 templates; 5 eligible record types; ~35 declared field
bindings in total; 2 read routes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

**Initial evaluation — PASS.** Re-evaluated post-design — **PASS**, with one
narrowed requirement recorded in Complexity Tracking.

| Principle | How this feature satisfies it |
|---|---|
| **I. Local-First** | No external service. FR-019 forbids any model call in this phase; no dependency is added at all. Strengthens rather than tests this principle. |
| **II. Auditability** | The module registers its own `audit_routes` entry (FR-013) — refusals recorded automatically through `apps/core/exception_handlers.py`, target type `prompts.PromptTemplate`, action prefix `prompt`. Append-only reuse of `record_action`; no new audit mechanism. The one deviation — not auditing successful reads — matches every existing module's actual behavior and is recorded in Complexity Tracking. |
| **III. RBAC (NON-NEGOTIABLE)** | `HasRole(*roles)` at the view layer, server-side (`apps/core/permissions.py`). View and write role sets chosen deliberately for this module (§4), not copied. No client-side or template-only restriction. |
| **IV. Explainable AI** | Satisfied *structurally*, which is this phase's contribution to it: the declared field list is the mechanism that will make a 4b output traceable to the exact structured data it was permitted to draw from. Principle IV's behavioral obligations (explanation accompanying a decision, human review, raw output not the record of truth) attach to the outputs 4b produces; 4a produces none. Building the traceability substrate before the first generated output is the correct ordering. |
| **V. Test-First (NON-NEGOTIABLE)** | The validation layer is business-rule code by the constitution's own definition ("prompt templates ... MUST have tests around their deterministic surface: input construction, output parsing/validation"). Tests precede implementation; the surface is fully deterministic (no model output is asserted against because none is produced). Coverage measured. |
| **VI. Spike stays disposable** | Phase 0's `app.py` is read for its *prompt text and findings*, never imported, copied wholesale, or refactored. §2's rewrite of five templates is authoring under this spec, not promoting spike code. The Streamlit app remains untouched and unreferenced by any production module. |

## Project Structure

### Documentation (this feature)

```text
specs/007-prompt-library/
├── plan.md              # This file
├── research.md          # Phase 0 output — 8 decisions
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── prompt-library-api.md
├── checklists/
│   └── requirements.md  # From /speckit-specify
├── spec.md
└── tasks.md             # /speckit-tasks — NOT created here
```

### Source Code (repository root)

```text
apps/prompts/                      # NEW app — the only new package
├── __init__.py
├── apps.py                        # ready(): validate library + register audit route
├── library.py                     # The 7 templates. Frozen dataclasses, no Django import
├── bindings.py                    # Whitelist frozenset, placeholder regex, resolver
├── validation.py                  # FR-005/006/007/008/010/023/024 enforcement
├── serializers.py
├── views.py                       # 2 read routes; VIEW_ROLES / WRITE_ROLES
├── urls.py                        # mounted at /api/prompts/
└── tests/
    ├── __init__.py
    ├── test_library.py            # Content: 7 templates, provenance, versions
    ├── test_bindings.py           # Whitelist equality pin, resolver, regex
    ├── test_validation.py         # Every rejection path; whole-library atomicity
    ├── test_permissions.py        # 9 view roles / 1 write role, both directions
    ├── test_audit.py              # Refusal rows; registry as fifth consumer
    └── test_views.py              # Response shapes, list/detail

config/urls.py                     # +1 line: path("api/prompts/", ...)
config/settings/base.py            # +1 line: "apps.prompts" in INSTALLED_APPS
apps/core/audit_routes.py          # +1 register() call in register_defaults()
```

**Structure Decision**: A new `apps/prompts` package following the established
per-module layout (`apps/risk` is the closest model: `models.py`-free logic in
`rules.py`, ORM boundary in `engine.py`, roles in `views.py`, routes in
`urls.py`). Two deliberate departures from that shape:

- **No `models.py`.** The library has no database table. `data-model.md`
  documents the in-memory structures instead.
- **`library.py` and `bindings.py` import no Django**, exactly as
  `apps/risk/rules.py` does not (`rules.py:11-18`). This is what lets the
  library and its validation be tested without a database, and it means the
  eligible-type whitelist is a table of strings rather than model classes —
  resolved to real fields only in `validation.py`, which does import Django.

The single new entry in `audit_routes.register_defaults()` is what FR-013's
"fifth consumer" means concretely: `prefix="/api/prompts/"`,
`target_type="prompts.PromptTemplate"`, `action_prefix="prompt"`, plus the two
role sets. No change to the four existing entries, and no change to
`exception_handlers.py`, which carries no per-module knowledge by design
(`exception_handlers.py:15-18`).

## Complexity Tracking

> Two spec amendments this plan requires, and one narrowed requirement. Recorded
> here rather than applied silently.

| Item | Why needed | Alternative rejected because |
|---|---|---|
| **FR-016 + Assumptions: correct "18 templates" to "7"** | Verified against the actual Phase 0 artifacts, which exist at `~/insurance-ai-platform-phase0` (outside this repo, hence unverifiable during `/speckit-specify`). `app.py:43-101` defines 7; `readme-setup-conclusions.md:192` states 7. The spec named FR-016/FR-018 as what to revise if reconciliation differed. | Authoring 11 net-new templates to reach 18 would put unvalidated content behind a requirement whose entire purpose is recording Phase 0 provenance. A template nobody ran against a model is not a "verified template." |
| **FR-015: narrow "every access — successful or refused" to "every refusal, and every write"** | No module on this platform audits successful reads — verified: `apps/risk/views.py` has zero `record_action` calls; customers/policies/claims audit create/update/destroy only. The literal reading would make the prompt library the sole module logging a row per GET, contradicting FR-013/FR-014's premise that it behaves as the registry's fifth consumer, and SC-006's requirement that existing behavior is unaffected. A template read also discloses no customer data. | Implementing it literally and accepting the divergence. Rejected because auditing reads is a platform-wide convention change affecting all five modules; if that is the real intent it belongs in its own spec, not introduced sideways in a phase whose spec says audit logging "reuses existing mechanisms." |
| Five Phase 0 templates rewritten to drop `Client_Feedback` | The field exists in no platform model (verified across all four model modules). FR-006 and FR-017 forbid declaring it. | Adding a `feedback` column to `Customer` — rejected as inverting the grounding contract's dependency direction (spec Key Entities states this feature "does not add to, modify, or read the data in" those record types). Deferring all five — rejected as leaving a 2-template library for no benefit. |

No constitutional violation requires justification. The three items above are
spec-accuracy corrections discovered by verification, not principle exceptions.
