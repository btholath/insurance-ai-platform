---
description: "Task list for Phase 4a — Prompt Library (Module 7)"
---

# Tasks: Phase 4a — Prompt Library

**Input**: Design documents from `/specs/007-prompt-library/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED and non-negotiable. FR-022 requires them, the user
description names test-first explicitly, and the constitution's Principle V
covers this module by name ("Prompt templates and LLM-integration code MUST have
tests around their deterministic surface"). Every surface here *is*
deterministic — no model output exists to be non-deterministic about. Test tasks
precede their implementation within every phase.

**Organization**: Grouped by user story so each can be implemented and tested
independently, following research.md's eight decisions and the API contract.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Include exact file paths in descriptions

## Path Conventions

Django web service, API-only. One new app, `apps/prompts/`. **No new database
table and no migration** — paths below are repository-root-relative, matching
plan.md's Project Structure.

## Before you start — three things this feature gets wrong if rushed

1. **The library is 7 templates, not 18.** The feature description said 18; the
   Phase 0 artifacts say 7 (research.md §1, verified). Do not author templates
   to reach a count — FR-016 now forbids it explicitly.
2. **Field existence is not eligibility.** `User.password` and `AuditLog.before`
   are real fields. The whitelist (T012–T014) is the only thing that rejects
   them. This is the single highest-value correctness surface in the feature.
3. **Do not audit successful reads.** FR-015 was narrowed during planning to
   match every existing module (research.md §7). Adding a `record_action` call
   to a GET path would silently diverge the platform.

---

## Phase 1: Setup (New App Scaffolding)

**Purpose**: Bring `apps/prompts` into existence as a registered Django app with
no behavior yet, so every later phase has somewhere to live.

- [X] T001 Create the `apps/prompts/` package with `__init__.py` and `tests/__init__.py` (plan.md Project Structure)
- [X] T002 Create `apps/prompts/apps.py` with `PromptsConfig` (`name = "apps.prompts"`, `label = "prompts"`, `default_auto_field = "django.db.models.BigAutoField"`), mirroring `apps/risk/apps.py`. Leave `ready()` unimplemented until T017/T031
- [X] T003 Add `"apps.prompts"` to `INSTALLED_APPS` in `config/settings/base.py`, after `"apps.risk"` (line 39)
- [X] T004 Verify the app loads and adds no migration: `docker compose exec web python manage.py check` clean, and `python manage.py makemigrations --check --dry-run` reports nothing pending for `prompts` (data-model.md — this feature adds no table)

**Checkpoint**: `apps.prompts` is a registered, empty Django app. Nothing else changed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The binding primitives and the whitelist. Every user story depends
on `FieldBinding`, `ELIGIBLE_RECORD_TYPES`, and the placeholder regex existing —
US1's validation, US2's version hashing, US3's serializers, and US4's templates
all consume them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for the binding primitives ⚠️

> Write these FIRST and confirm they FAIL before implementing T012–T016.

- [X] T005 [P] Create `apps/prompts/tests/test_bindings.py` with tests for `FieldBinding` construction: frozen (mutation raises), hashable, and equality by value (data-model.md §2)
- [X] T006 [P] Add tests to `apps/prompts/tests/test_bindings.py` for `extract_placeholders(body)`: extracts `{Customer.name}` as `("Customer", "name")`, handles multiple occurrences of the same placeholder as one entry, returns an empty set for a body with no placeholders, and treats `{{` / `}}` as escaped literals rather than placeholders (research.md §5)
- [X] T007 [P] Add a test to `apps/prompts/tests/test_bindings.py` asserting `extract_placeholders` ignores a bare `{name}` (unqualified) rather than silently guessing a record type — an unqualified token must surface as a validation failure later, never as a resolved binding (research.md §5)

### The whitelist equality pin — the feature's central assertion ⚠️

- [X] T008 Add `test_eligible_record_types_is_exactly_the_approved_five` to `apps/prompts/tests/test_bindings.py`, asserting `ELIGIBLE_RECORD_TYPES == {"Customer", "Policy", "Claim", "RiskAssessment", "RiskFactor"}` by **exact equality in both directions**. Docstring must state, in the voice of `apps/risk/tests/test_rules.py:270`: a subset check would admit a sixth type, a superset check would let one be silently dropped, and a failure means amending FR-023 deliberately — never relaxing the assertion (FR-024, research.md §3)
- [X] T009 [P] Add `test_identity_and_audit_types_are_ineligible` to `apps/prompts/tests/test_bindings.py`, asserting `"User"`, `"AuditLog"`, `"Session"`, and `"ContentType"` are each absent from `ELIGIBLE_RECORD_TYPES` (FR-025)
- [X] T010 [P] Add `test_ineligible_types_name_real_fields` to `apps/prompts/tests/test_bindings.py`: resolve `User.password`, `User.is_superuser`, `User.role`, `AuditLog.before`, `AuditLog.after` via `_meta.get_field()` and assert each **exists**. This test gives T008/T009 their teeth — it proves the whitelist is rejecting genuinely-valid fields, not merely typos (research.md §3, data-model.md §1)

### Implementation of the binding primitives

- [X] T011 [P] Create `apps/prompts/bindings.py` with a module docstring stating the Django-free constraint and why, mirroring `apps/risk/rules.py:11-18`: no ORM, no settings, no TextChoices, so the module is testable from a REPL with no fixtures. `validation.py` owns the ORM boundary
- [X] T012 Add `ELIGIBLE_RECORD_TYPES` as a module-level `frozenset` of the five type-name strings to `apps/prompts/bindings.py`, with a comment recording that `User` and `AuditLog` are excluded despite having real fields, and naming `AuditLog.before`/`.after` as the sharpest case (they hold prior-state snapshots of *other* records, so one approved declaration re-exposes arbitrary fields of arbitrary types) (FR-023, FR-025)
- [X] T013 Add the `FieldBinding` frozen dataclass (`record_type`, `field_name`, `placeholder`) to `apps/prompts/bindings.py` (data-model.md §2)
- [X] T014 Add `PLACEHOLDER_RE` and `extract_placeholders(body)` to `apps/prompts/bindings.py`, matching `{RecordType.field_name}` with the escape convention from research.md §5. Returns a set of `(record_type, field_name)` tuples
- [X] T015 Run `pytest apps/prompts/tests/test_bindings.py` — all Phase 2 tests green

**Checkpoint**: The whitelist exists and is pinned. Binding primitives are testable with no database. No template, no validation, no route yet.

---

## Phase 3: User Story 1 — A Template Declares Exactly What Data It May Use (Priority: P1) 🎯 MVP

**Goal**: The grounding contract is enforced. A template's declaration is exact
in both directions, names only existing fields on only eligible record types,
and the whole library fails loudly if any template violates any of that.

**Independent Test**: Read a template's declared field list and confirm by
inspection that body and declaration agree exactly; then attempt to add a
template with (a) an undeclared reference, (b) an unused declaration, (c) a
nonexistent field, (d) a real field on an ineligible type, (e) an unbound
placeholder — and confirm each is rejected and the whole library refuses to load.

### Tests for User Story 1 ⚠️

> Write these FIRST and confirm they FAIL before implementing T023–T027.

- [X] T016 [P] [US1] Create `apps/prompts/tests/test_validation.py` with `test_declaration_and_body_must_agree_exactly`: a template referencing an undeclared field is rejected naming that field, and a template declaring an unreferenced field is rejected naming that field. Both directions, separate assertions (FR-005)
- [X] T017 [P] [US1] Add `test_declared_field_must_exist_on_model` to `apps/prompts/tests/test_validation.py`: a binding naming a nonexistent field on an eligible type is rejected naming the field (FR-006)
- [X] T018 [P] [US1] Add `test_declared_record_type_must_be_eligible` to `apps/prompts/tests/test_validation.py`: bindings for `User.password`, `User.is_superuser`, `User.role`, `AuditLog.before`, `AuditLog.after` are each rejected, and the error identifies the **record type** as ineligible rather than reporting a missing field. Assert on the message, not just the exception type — a "no such field" message here would mean the whitelist is not what rejected it (FR-023, FR-025, quickstart.md Step 2)
- [X] T019 [P] [US1] Add `test_unbound_placeholder_is_rejected` to `apps/prompts/tests/test_validation.py`: a body containing an unqualified `{name}` or a placeholder with no matching binding is rejected (FR-007)
- [X] T020 [P] [US1] Add `test_duplicate_identifier_is_rejected` to `apps/prompts/tests/test_validation.py`: two templates sharing an `identifier` are rejected naming the collision (FR-001, spec edge case)
- [X] T021 [US1] Add `test_library_validation_is_all_or_nothing` to `apps/prompts/tests/test_validation.py`: given a library where one template is invalid and the rest are valid, `validate_library()` raises and validates **nothing** partially — no "skip the bad one and continue" path exists (FR-008)
- [X] T022 [P] [US1] Add `test_validation_needs_no_database` to `apps/prompts/tests/test_validation.py` — a test *without* `@pytest.mark.django_db` that constructs and validates bindings, proving the field-existence check reads model metadata only and touches no row (data-model.md §7)

### Implementation for User Story 1

- [X] T023 [US1] Create `apps/prompts/validation.py` with a module docstring explaining that this module owns the ORM boundary (it imports Django; `bindings.py` and `library.py` do not) and that validation runs for the whole library as a unit
- [X] T024 [US1] Implement `check_binding(binding)` in `apps/prompts/validation.py`: check `record_type in ELIGIBLE_RECORD_TYPES` **first**, raising an error that names the type as ineligible; only then resolve the model via the app registry and `_meta.get_field(field_name)`, raising an error naming the field if absent. Order matters — the eligibility error must be the one a caller sees for `User.password` (FR-023 then FR-006)
- [X] T025 [US1] Implement `check_template(template)` in `apps/prompts/validation.py`: run `check_binding` for every binding, then assert set-equality between `extract_placeholders(template.body)` and the template's declared `(record_type, field_name)` pairs, raising with the offending names on either mismatch direction (FR-005, FR-007)
- [X] T026 [US1] Implement `validate_library(templates)` in `apps/prompts/validation.py`: check identifier uniqueness across the collection, then run `check_template` for every template, raising on the first failure with the template's identifier in the message. No partial-success path (FR-008)
- [X] T027 [US1] Wire `validate_library(library.TEMPLATES)` into `PromptsConfig.ready()` in `apps/prompts/apps.py`, imported lazily inside the function for the same reason `apps/core/apps.py:8-15` does — the app registry is not populated at module import time. A malformed library now fails at startup, the loudest available failure (FR-008, research.md §6)
- [X] T028 [US1] Run `pytest apps/prompts/tests/test_validation.py apps/prompts/tests/test_bindings.py` — all green

**Checkpoint**: The grounding contract is enforced end to end. US1 is independently demonstrable via quickstart.md Steps 1 and 2, with no templates authored yet (tests construct their own fixtures).

---

## Phase 4: User Story 2 — Every Template Carries a Version That Cannot Drift (Priority: P1)

**Goal**: A version identifies exact template content. Editing a body or a
declaration without bumping the version fails loudly.

**Independent Test**: Change a template's body without changing its version and
confirm the suite fails naming that template; repeat for a declaration change.

### Tests for User Story 2 ⚠️

- [X] T029 [P] [US2] Create `apps/prompts/tests/test_library.py` with `test_every_template_has_a_semver_version`: each template's `version` matches the same semver shape `apps/risk/rules.py:85`'s `RULE_SET_VERSION` uses, and `PROMPT_LIBRARY_VERSION` likewise (FR-009)
- [X] T030 [P] [US2] Add `test_versions_are_independent_per_template` to `apps/prompts/tests/test_library.py`: each template carries its own `version` field rather than deriving it from a shared library constant (FR-009, US2 acceptance scenario 3)
- [X] T031 [US2] Add `test_template_content_matches_its_version` to `apps/prompts/tests/test_library.py`: hash each template's `body` + declared bindings and compare against a checked-in expected digest per template. Docstring must state that a failure means either bump the template's `version` or revert the content edit — the assertion is FR-010's only enforcement, since a constant alone cannot detect a body edited beneath it (FR-010, data-model.md §5)

### Implementation for User Story 2

- [X] T032 [US2] Add the `version: str` field to the `PromptTemplate` dataclass in `apps/prompts/library.py` and `PROMPT_LIBRARY_VERSION = "1.0.0"` as a module constant, with a comment referencing `apps/risk/rules.py:85`'s convention and noting that stamping the version onto generated output is Phase 4b's obligation (FR-009, data-model.md §5)
- [X] T033 [US2] Add the content-digest helper the T031 test consumes to `apps/prompts/tests/test_library.py` — test-only code, deliberately kept out of `library.py`, whose Django-free constraint (T011's rationale) is easier to hold if it carries nothing test-only. **Helper only** — the expected digests are populated in T071, once Phase 6 has authored the templates to hash
- [X] T034 [US2] Run `pytest apps/prompts/tests/test_library.py -k version` — green

**Checkpoint**: Version-content drift is impossible without a failing test. US2 is demonstrable via quickstart.md Step 3.

---

## Phase 5: User Story 3 — Permitted Roles Browse; Unpermitted Are Refused and Audited (Priority: P1)

**Goal**: Two read routes, server-side RBAC with the fifth distinct role shape,
and the module registered as the audited-route registry's fifth consumer — with
the four existing entries provably unaffected.

**Independent Test**: Call both routes as each of the nine roles and
unauthenticated; confirm the 9/1 role shape; query the audit trail and confirm
refusals appear under `prompt.*` / `prompts.PromptTemplate` and successful reads
add no rows.

### Tests for User Story 3 ⚠️

- [X] T035 [P] [US3] Create `apps/prompts/tests/test_permissions.py` with `test_all_nine_roles_may_read`: parametrized over every `Role` value, asserting 200 on both the list and detail routes. Docstring must call out that Executive Leadership returning 200 is the signal that matters — it is excluded from all four existing view sets, so a 403 there would mean the role set was copied rather than chosen (FR-012, research.md §4)
- [X] T036 [P] [US3] Add `test_write_methods_are_refused_for_non_admin_roles` to `apps/prompts/tests/test_permissions.py`: POST/PUT/PATCH/DELETE against both routes are refused for all eight non-Sysadmin roles (FR-012, contracts/prompt-library-api.md)
- [X] T037 [P] [US3] Add `test_unauthenticated_is_refused` to `apps/prompts/tests/test_permissions.py`: 403 on the collection route, **404** on the detail route (existence non-disclosure). Assert both codes explicitly — they differ by design per `apps/core/permissions.py:16-30`
- [X] T038 [P] [US3] Create `apps/prompts/tests/test_audit.py` with `test_refusal_is_recorded_under_this_modules_action_and_target`: an unauthenticated request writes one `AuditLog` row with `action="prompt.viewed"`, `target_type="prompts.PromptTemplate"`, `outcome="refused"`. Assert the action prefix is `prompt`, **not** `customer` — a prompt refusal recorded under another module's name would mean the prefix is being swallowed by an existing entry (FR-015, contracts/prompt-library-api.md)
- [X] T039 [US3] Add `test_successful_read_writes_no_audit_row` to `apps/prompts/tests/test_audit.py`: a permitted read leaves the `prompts.PromptTemplate` audit count unchanged. Docstring must record that this is deliberate and matches every existing module (`apps/risk/views.py` has zero `record_action` calls), per FR-015 as narrowed in research.md §7 — **not** an omission to be "fixed" later
- [X] T040 [P] [US3] Add `test_registry_has_five_entries_and_prompts_has_the_ninth_view_role` to `apps/prompts/tests/test_audit.py`: `audit_routes.all_routes()` returns five entries; the `/api/prompts/` entry has 9 view roles and 1 write role; and the four existing entries retain their exact prefixes, target types, and role-set sizes (7/2, 8/2, 5/2, 5/2) (FR-013, FR-014, SC-006)
- [X] T041 [P] [US3] Create `apps/prompts/tests/test_views.py` with response-shape tests: the list route returns `library_version`, `count`, and `results` each carrying `identifier`/`purpose`/`version`/`bindings`/`model_preference` but **not** `body`; the detail route additionally returns `body` (FR-011, contracts/prompt-library-api.md)
- [X] T042 [P] [US3] Add `test_list_route_executes_no_queries` to `apps/prompts/tests/test_views.py` using `django_assert_num_queries(0)` — the library is served from an in-memory tuple (plan.md Performance Goals). Session/auth queries, if any, must be excluded by authenticating before the assertion block
- [X] T043 [P] [US3] Add `test_detail_route_404s_on_unknown_identifier` to `apps/prompts/tests/test_views.py`: a permitted role requesting a nonexistent identifier gets 404 and **no** audit row (an ordinary miss, not a refusal — the distinction `apps/core/exception_handlers.py:50-67` draws)

### Implementation for User Story 3

- [X] T044 [US3] Create `apps/prompts/serializers.py` with `FieldBindingSerializer`, `ModelPreferenceSerializer`, and `PromptTemplateSerializer` (list variant without `body`, detail variant with it). Plain `Serializer` subclasses, not `ModelSerializer` — there is no model (data-model.md, contracts/prompt-library-api.md)
- [X] T045 [US3] Create `apps/prompts/views.py` with `VIEW_ROLES` (all nine `Role` values) and `WRITE_ROLES = (Role.SYSTEM_ADMINISTRATOR,)`, plus a module docstring recording *why* the view set is universal — a template carries field names, never field values, so it holds no customer data and the restrictions protecting the other four modules have nothing to protect here (research.md §4)
- [X] T046 [US3] Implement the read-only viewset in `apps/prompts/views.py`: `lookup_field = "identifier"`, `get_permissions()` returning `HasRole(*VIEW_ROLES)` (mirroring `apps/risk/views.py:55-57`), list and retrieve served from `library.TEMPLATES` with no queryset, raising `NotFound` for an unknown identifier
- [X] T047 [US3] Create `apps/prompts/urls.py` registering the viewset at `templates` with `basename="prompttemplate"`, plus a docstring recording why the mount is top-level and not nested — the same reason `apps/risk/urls.py` carries (a nested path is swallowed by an existing registry prefix and mis-audits every refusal under the wrong module's role set)
- [X] T048 [US3] Add `path("api/prompts/", include("apps.prompts.urls"))` to `config/urls.py`
- [X] T049 [US3] Add the fifth `register(AuditedRoute(...))` call to `register_defaults()` in `apps/core/audit_routes.py`: `prefix="/api/prompts/"`, `target_type="prompts.PromptTemplate"`, `action_prefix="prompt"`, `view_roles=` all nine, `write_roles=(Role.SYSTEM_ADMINISTRATOR,)`. Add a comment in the established voice of the existing four entries, recording that this is the first universal view set and the first single-role write set, and why (FR-013)
- [X] T050 [US3] Run `pytest apps/prompts/tests/test_permissions.py apps/prompts/tests/test_audit.py apps/prompts/tests/test_views.py` — all green
- [X] T051 [US3] Run the four existing consumers' suites unchanged: `pytest apps/customers apps/policies apps/claims apps/risk apps/audit apps/core` — all passing, nothing skipped (FR-014, SC-006)

**Checkpoint**: The API is live, RBAC enforced, and the registry has a fifth consumer with the other four provably untouched. Demonstrable via quickstart.md Steps 4 and 5.

---

## Phase 6: User Story 4 — The Library Covers Phase 0's Verified Prompt Set (Priority: P2)

**Goal**: The seven Phase 0 templates exist as validated, versioned library
entries with honest provenance — including the five that had to be rewritten.

**Independent Test**: Enumerate the library, confirm seven templates each
tracing to a Phase 0 prompt type, and confirm every one independently satisfies
US1's and US2's guarantees.

**⚠️ Read `research.md` §1 and §2 before starting.** The count is 7, not 18, and
five templates cannot be ported verbatim.

### Tests for User Story 4 ⚠️

- [X] T052 [P] [US4] Add `test_library_has_exactly_seven_templates` to `apps/prompts/tests/test_library.py`, asserting exact equality on the set of the seven identifiers. Docstring must record that the feature description said 18 while the Phase 0 artifacts define 7 (`app.py:43-101`, `readme-setup-conclusions.md:192`), and that FR-016 forbids padding the library to reach a count (FR-016, research.md §1)
- [X] T053 [P] [US4] Add `test_every_template_traces_to_a_phase0_origin` to `apps/prompts/tests/test_library.py`: every template has a non-empty `phase0_origin` naming one of the seven Phase 0 template names (FR-016)
- [X] T054 [P] [US4] Add `test_no_phase0_prompt_type_was_deferred` to `apps/prompts/tests/test_library.py`: assert the set of `phase0_origin` values across the library equals all seven Phase 0 template names exactly, so nothing was dropped. Docstring must record that FR-016's defer path is satisfied **vacuously** — research.md §2 determined all seven are portable (five with a `Client_Feedback` rewrite), so `DEFERRED_PHASE0_TYPES` is empty by construction. If a future template becomes unportable, that constant is where the deferral and its reason get recorded, and this test is what fails until it does (FR-016, SC-007)
- [X] T055 [P] [US4] Add `test_rewritten_templates_record_their_divergence` to `apps/prompts/tests/test_library.py`: the five templates whose Phase 0 source referenced `Client_Feedback` carry a non-empty `phase0_divergence`, and the two unchanged ones carry `None`. Provenance must not imply an untouched port (FR-016, research.md §2)
- [X] T056 [P] [US4] Add `test_no_template_declares_an_unmappable_phase0_column` to `apps/prompts/tests/test_library.py`: no binding names `feedback`, `client_feedback`, `last_interaction`, or any variant — these are Phase 0 CSV columns with no platform field (FR-017, research.md §2)
- [X] T057 [P] [US4] Add `test_model_preference_records_phase0_findings` to `apps/prompts/tests/test_library.py`: every template's `model_preference.preferred` is `"llama3.1:8b"` and its `disqualified` names `phi3:mini` with a reason mentioning hallucinated claim IDs / policy numbers (FR-018, research.md §1)
- [X] T058 [P] [US4] Add `test_no_template_declares_gender` to `apps/prompts/tests/test_library.py`: no binding names `Customer.gender`. Docstring must record this as a deliberate exclusion consistent with the risk module keeping a protected characteristic out of scoring (`apps/risk/rules.py:40-47`), not an accident of what Phase 0 happened to write (FR-021, research.md §3)
- [X] T059 [P] [US4] Add `test_every_template_records_a_pii_decision` to `apps/prompts/tests/test_library.py`: every template carries a non-empty `pii_note` (FR-021)
- [X] T060 [P] [US4] Add `test_every_template_has_a_meaningful_purpose` to `apps/prompts/tests/test_library.py`: every template's `purpose` is non-empty, is not merely a restatement of its `identifier`, and names both the output it produces and the business audience it serves. The identifier-restatement check is what makes this more than an emptiness assertion — a `purpose` of `"risk assessment summary"` on `risk_assessment_summary` satisfies FR-002's letter and nothing of its intent (FR-002)
- [X] T061 [US4] Add `test_risk_score_binds_to_the_authoritative_field` to `apps/prompts/tests/test_library.py`: any template drawing on a risk score declares `RiskAssessment.score`, never `Customer.risk_score` — the latter is a denormalized `score / 100` mirror explicitly documented as not a second source of truth (`apps/customers/models.py:122-131`, data-model.md §6)

### Implementation for User Story 4

- [X] T062 [US4] Create `apps/prompts/library.py` with the `ModelPreference` and `PromptTemplate` frozen dataclasses per data-model.md §3–§4, and a module docstring stating the Django-free constraint (mirroring `apps/risk/rules.py`) and recording the 7-vs-18 reconciliation with its evidence (FR-002, FR-003, FR-004)
- [X] T063 [US4] Add `DEFERRED_PHASE0_TYPES: tuple[tuple[str, str], ...] = ()` to `apps/prompts/library.py` — an empty `(prompt_type, reason)` tuple, empty today by construction (research.md §2). It exists so FR-016's defer path has somewhere to live rather than remaining unimplementable prose, and T054 is what holds it honest (FR-016, SC-007)
- [X] T064 [P] [US4] Author `risk_assessment_summary` in `apps/prompts/library.py` — rewritten from Phase 0's *Risk Assessment Summary*, `Client_Feedback` reference dropped. Bindings across Customer, Policy, Claim, RiskAssessment (data-model.md §6)
- [X] T065 [P] [US4] Author `fraud_high_risk_flag_summary` in `apps/prompts/library.py` — rewritten from *Fraud / High-Risk Flag Summary*, `Client_Feedback` dropped
- [X] T066 [P] [US4] Author `personalized_renewal_reminder` in `apps/prompts/library.py` — rewritten from *Personalized Renewal Reminder*, `Client_Feedback` dropped. Draws on Customer and Policy only
- [X] T067 [P] [US4] Author `cross_sell_recommendation` in `apps/prompts/library.py` — rewritten from *Cross-Sell Recommendation*, `Client_Feedback` dropped
- [X] T068 [P] [US4] Author `claim_summary_internal` in `apps/prompts/library.py` — rewritten from *Claim Summary (internal)*, `Client_Feedback` dropped
- [X] T069 [P] [US4] Author `behavioral_pattern_analysis` in `apps/prompts/library.py` — carried from *Behavioral Pattern Analysis* with no field divergence (`phase0_divergence = None`)
- [X] T070 [P] [US4] Author `executive_summary` in `apps/prompts/library.py` — carried from *Executive Summary (leadership review)*, `phase0_divergence = None`
- [X] T071 [US4] Populate the expected content digests for all seven templates using the T033 helper, now that the templates exist, and confirm T031 passes
- [X] T072 [US4] Run `pytest apps/prompts` — the full module suite green, including validation of the real seven templates at app-ready

**Checkpoint**: The library is populated, validated, versioned, and honestly attributed. All four user stories complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T073 [P] Add the resolver `resolve(template, **records)` to `apps/prompts/bindings.py`, returning `{FieldBinding: value}` for a supplied record set, plus tests in `apps/prompts/tests/test_bindings.py`. **Resolver only — no renderer.** Do not add value-into-body substitution; that is Phase 4b's, whose prompt-assembly needs (system prompts, few-shot examples, output-format instructions) do not exist yet (FR-020, research.md §6)
- [X] T074 [P] Add `test_resolve_returns_only_declared_fields` to `apps/prompts/tests/test_bindings.py`: the resolver's output keys equal the template's declared bindings exactly — nothing outside the declaration appears. This is the field-by-field mapping Phase 4b's post-generation validator will consume (FR-020, quickstart.md Step 6)
- [X] T075 [P] Add `test_no_llm_call_surface_exists` to `apps/prompts/tests/test_library.py` or a new `apps/prompts/tests/test_no_llm.py`: assert no module under `apps/prompts/` imports `requests`, `httpx`, `ollama`, `openai`, or `langchain`. FR-019/SC-008 as an executable assertion rather than a promise
- [X] T076 Run the full suite: `pytest` — every test across the project passing, no regressions in the 1084 tests Phase 3b left green
- [X] T077 Run coverage on the new module: `pytest apps/prompts --cov=apps.prompts --cov-report=term-missing` — 100% on every `apps/prompts/` file, matching the bar Phase 3b set for `apps/risk/` (Principle V, readme-runbook-phase3.md)
- [X] T078 Execute `specs/007-prompt-library/quickstart.md` Steps 1–7 against the running dev stack and record the results. Step 7's Ollama-stopped run is the strongest form of the no-LLM-call check and must change nothing
- [X] T079 [P] Add a Phase 4a section to `readme-runbook-phase4.md` (new file, following `readme-runbook-phase3.md`'s structure), recording the 7-vs-18 reconciliation, the `Client_Feedback` rewrite of five templates, the FR-015 narrowing, and the fifth registry entry's 9/1 role shape

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational. Blocks nothing, but US4's templates cannot be validated without it
- **US2 (Phase 4)**: Depends on Foundational. T033's digests need US4's templates to be populated (T071)
- **US3 (Phase 5)**: Depends on Foundational. Independent of US1/US2 — the routes serve whatever the library holds
- **US4 (Phase 6)**: Depends on Foundational **and** US1 — authoring templates without the validator means authoring them blind
- **Polish (Phase 7)**: Depends on all four stories

### User Story Dependencies

- **US1 (P1)**: Foundational only. The MVP.
- **US2 (P1)**: Foundational only, except T071's digest population, which trails US4
- **US3 (P1)**: Foundational only — genuinely independent of the other three
- **US4 (P2)**: Foundational + US1

### Within Each User Story

- Tests MUST be written and MUST FAIL before implementation
- `bindings.py` (Django-free) before `validation.py` (owns the ORM boundary)
- `library.py` before serializers that shape it
- Serializers before views; views before URL wiring; URL wiring before the registry entry

### Parallel Opportunities

- T005–T007, T009–T011 within Foundational (different concerns, one shared file — coordinate writes to `test_bindings.py`)
- T016–T020, T022 within US1 (all in `test_validation.py` — parallel authoring, serialized commits)
- T035–T038, T040–T043 within US3 (three distinct test files, genuinely parallel)
- **T064–T070 are the cleanest parallel block in the feature** — seven independent template definitions, one per developer if desired
- T073–T075, T079 within Polish

---

## Parallel Example: User Story 4's template authoring

```bash
# Seven independent template definitions, all in library.py — parallel
# authoring, serialized commits:
Task: "Author risk_assessment_summary (rewritten, Client_Feedback dropped)"
Task: "Author fraud_high_risk_flag_summary (rewritten)"
Task: "Author personalized_renewal_reminder (rewritten)"
Task: "Author cross_sell_recommendation (rewritten)"
Task: "Author claim_summary_internal (rewritten)"
Task: "Author behavioral_pattern_analysis (as-is)"
Task: "Author executive_summary (as-is)"
```

---

## Implementation Strategy

### MVP scope: Phase 1 + Phase 2 + Phase 3 (US1)

The grounding contract, enforced, with no templates and no API. That is a
coherent, demonstrable increment: quickstart.md Steps 1 and 2 both pass, and the
whitelist — the feature's highest-value correctness surface — is provably
closed. Everything after it is payload the contract carries.

### Incremental Delivery

1. Setup + Foundational → whitelist pinned, binding primitives testable
2. + US1 → the grounding contract is enforced (**MVP**)
3. + US3 → the library is reachable over the API, RBAC and audit proven, registry has five consumers
4. + US2 → version-content drift becomes impossible
5. + US4 → the seven real templates land, honestly attributed
6. + Polish → resolver, no-LLM assertion, full suite, coverage, quickstart, runbook

US3 before US2 is deliberate: US3 is the largest independent slice and needs
nothing from US2, while US2's digest task (T071) trails US4 anyway.

### Parallel Team Strategy

Once Foundational is complete:

- Developer A: US1 → US4 (the contract-and-content axis; US4 depends on US1)
- Developer B: US3 (the API/RBAC/audit axis — entirely disjoint files)
- Developer C: US2, then joins US4's template authoring (T064–T070)

---

## Notes

- **The whitelist tests (T008–T010) are the most important tasks in this
  list.** T010 in particular is what stops T008/T009 from being vacuous: it
  proves `User.password` and `AuditLog.before` are *real* fields, so the
  whitelist is rejecting genuinely-valid declarations rather than typos. Phase
  3b's experience is the precedent — a test that asserted vacuously for two
  phases because nobody checked it could actually fail.
- **Seven templates, not eighteen.** T052 pins this by exact equality. If it
  fails because someone added an eighth, the fix is deleting the eighth, not
  relaxing the test.
- **Do not add a `record_action` call to any GET path.** T039 asserts successful
  reads write no audit row; that is FR-015 as narrowed (research.md §7), not an
  oversight.
- **No renderer.** T073 stops at the resolver deliberately. A task list that
  grows a `render()` function has exceeded 4a's scope.
- **No new dependency.** Placeholder extraction is one `re` pattern from the
  standard library; if a task seems to need a template engine, re-read
  research.md §5 — a full template language would make FR-007 undecidable by
  static inspection.
- Commit after each task or logical group.
