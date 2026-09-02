# Specification Quality Checklist: Prompt Library

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-02
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Constitution Alignment

Per the constitution's Compliance Review clause, checked before `/speckit-tasks`:

- [x] **Principle I (local-first)**: No external service introduced; FR-019
      forbids any model call in this phase.
- [x] **Principle II (auditability)**: FR-013/FR-014/FR-015 and SC-005/SC-006
      cover the module's own audited-route entry and append-only trail.
- [x] **Principle III (RBAC)**: FR-012 requires server-side enforcement;
      SC-004 measures it. Exact role sets deferred to planning as a deliberate
      per-module decision, matching how the four existing entries were set.
- [x] **Principle IV (explainable AI)**: Addressed structurally — the declared
      field list is the traceability mechanism; noted in Assumptions that the
      behavioral obligations attach to Phase 4b's outputs.
- [x] **Principle V (test-first)**: FR-022 requires tests before/alongside
      implementation over the deterministic surface.
- [x] **Principle VI (spike stays disposable)**: Assumptions state Phase 0
      informs content only; templates are authored fresh.

## Notes

**Iteration 1 findings, resolved in the spec before this checklist was marked
complete:**

1. *Success criteria were partly untestable as first written.* SC-009
   originally read as a subjective comprehension claim. Rewritten as a
   verifiable property (the declaration alone is sufficient to state the
   permitted fields, without reading the body).

2. *"No implementation details" needed a judgment call.* The spec names
   existing platform mechanisms (the audited-route registry, the rule-set
   versioning convention, the five business record types) because the user's
   description makes reuse of those specific mechanisms a **requirement**, not
   an implementation choice — FR-013's whole point is that the registry gains a
   fifth consumer. Concrete file paths, class names, syntax, and framework
   names are kept out. Judged as passing.

3. *Phase 0's numbers could not be verified from this repository.* The
   `insurance-ai-platform-phase0` repo is not present, and
   `readme-runbook-phase1.md` mentions Phase 0 only in passing without a
   template inventory or model-evaluation results. Rather than asserting the
   18-template count and model findings as established fact, the spec records
   them in Assumptions as taken-as-given from the user's description, and names
   FR-016/FR-018 as what to revise if reconciliation against the real Phase 0
   artifacts turns up different numbers. This is a **live item for planning**,
   not a closed one.

4. *Three scope decisions were deliberately left to planning* rather than
   guessed at in the spec, each recorded in Assumptions: exact per-module role
   sets (FR-012/FR-013), placeholder syntax (FR-007), and whether 4a ships an
   inert renderer or only the binding contract (FR-019). Each is a design
   choice with a defensible default, not a requirements gap — none blocks
   `/speckit-plan`.

**Iteration 2 — gap found by the user during spec review, now closed:**

5. *Nothing constrained which record types were eligible to be declared
   against.* FR-004-008 validated that a declared field **exists** on the record
   type it names, but never that the record type itself was approved. The
   whitelist existed only as prose in Key Entities and Assumptions. A template
   declaring `User.password`, `User.role`, `User.is_superuser`, or
   `AuditLog.before` would have passed every check cleanly — the field genuinely
   exists, the body references it, the declaration is exact — while licensing a
   credential hash or a permission flag into a prompt. Verified against the real
   models: `apps/accounts/models.py:19` has `User(AbstractBaseUser,
   PermissionsMixin)`, so `password` and `is_superuser` are real inherited
   fields, and `apps/audit/models.py:35-36` carries `before`/`after` JSONFields.

   `AuditLog.before`/`after` is the sharpest instance: those snapshots hold
   prior state of *other* records, so one approved declaration against them
   would re-expose arbitrary fields of arbitrary record types, including
   ineligible ones — a full bypass of the grounding contract through a single
   validating entry.

   Closed by **FR-023** (closed whitelist, hard-enforced, field existence
   explicitly declared necessary-but-not-sufficient), **FR-024** (exact-equality
   pinning in both directions, mirroring
   `apps/risk/tests/test_rules.py:270`'s `test_factor_set_is_exactly_the_
   approved_five` — a subset check would admit a sixth type, a superset check
   would let one be silently dropped), and **FR-025** (identity, auth, and audit
   record types named as permanently ineligible). Supported by US1 acceptance
   scenario 4, a revised Independent Test, two new edge cases, and **SC-002a**.
   FR-022's test surface gained record-type eligibility.

   Worth noting for planning: FR-024's equality assertion is what keeps this
   from decaying into prose the way the original whitelist did. It should fail
   loudly and carry its own "do not relax this — amend FR-023 first" docstring,
   exactly as the risk module's factor-set test does.

**Iteration 3 — `/speckit-plan` verification, two amendments applied:**

6. *Phase 0's count was wrong: 7 templates, not 18.* Note 3 above flagged this
   as a live item. It is now closed — the Phase 0 repo was never missing, it is
   at `~/insurance-ai-platform-phase0`, outside this project's working
   directory. `app.py:43-101` defines exactly 7 keys in `PROMPT_TEMPLATES`, and
   `readme-setup-conclusions.md:192` states "All 7 prompt templates tested
   against `llama3.1:8b`". **Both model findings are confirmed verbatim** —
   `llama3.1:8b` clean on 8/8 runs, `phi3:mini` disqualified for hallucinating
   claim IDs and policy numbers (`readme-setup-conclusions.md:121-124`).
   FR-016 corrected to seven, with an added clause forbidding padding the
   library to hit a count; the Assumptions bullet rewritten to record the
   verification. FR-018 needed no change. See `research.md` §1.

   A second finding fell out of the same read: `Client_Feedback` (referenced by
   5 of the 7 templates) and `Last_Interaction` map to **no platform field
   anywhere**. Those five are carried over rewritten to drop the reference,
   recorded as a new Assumptions bullet. This is FR-017 working as designed —
   it caught exactly the case it was written for.

7. *FR-015 required auditing successful reads; no module on this platform does
   that.* Verified: `apps/risk/views.py` contains zero `record_action` calls,
   and customers/policies/claims audit only create/update/destroy. Refusals are
   audited centrally for every module via
   `apps/core/exception_handlers.py:90`. Implementing FR-015 literally would
   have made the prompt library the sole module writing an audit row per GET —
   contradicting FR-013/FR-014's premise that it behaves as the registry's
   *fifth consumer*, and SC-006's requirement that existing behavior is
   unaffected. FR-015 and SC-005 narrowed to refusals-and-writes, with the
   original wording and reasoning recorded inline. See `research.md` §7.

   This is the one place planning knowingly narrowed a written requirement, so
   it is also in plan.md's Complexity Tracking rather than only here. If
   auditing reads is genuinely wanted, it is a platform-wide change for all five
   modules and belongs in its own spec.

8. *The three deferred decisions from note 4 are now settled*, each recorded in
   the spec's Assumptions with its reasoning and a `research.md` reference:
   role sets = 9 view / 1 write (§4), placeholder syntax =
   `{RecordType.field_name}` (§5), renderer = out of scope but resolver in
   scope (§6).
