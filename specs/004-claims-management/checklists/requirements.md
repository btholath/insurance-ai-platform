# Specification Quality Checklist: Phase 2c — Claims Management

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-11
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

Per the constitution's requirement that every module's spec state how Principles
II, III, and IV are satisfied:

- [x] **Principle II (Auditability)**: FR-029 through FR-034 — creation,
  amendment, removal, refused attempts, system-load attribution, changed-fields-only
  diffs, same-transaction writes, and immutability.
- [x] **Principle III (RBAC)**: FR-025 through FR-028 — server-side enforcement,
  separate read and write role sets, existence non-disclosure.
- [x] **Principle IV (Explainable AI)**: Not applicable — this feature involves no
  AI or model-generated output, and FR-024 explicitly forbids deriving claim status
  or amount. Recorded as a justified non-applicability rather than silently omitted.
- [x] **Principle V (Test-First)**: SC-009 requires tests that fail before the
  behavior exists.
- [x] **Principle I (Local-First)**: No external service is introduced.

## Validation Notes

Three items required spec revision during initial validation and were fixed:

1. **Uniqueness question was initially left implicit.** The user asked for it to
   be worked out explicitly. Resolved by adding FR-007 (no uniqueness constraint)
   plus a dedicated assumption explaining *why* the live-scoped-versus-reserved
   question is moot for claims rather than answered either way.
2. **`No Claim` handling was the spec's largest latent ambiguity.** Verified
   against the dataset: 754 rows carry that status, 390 of them with a non-zero
   amount. Left unresolved this would have surfaced as a modeling decision made
   silently during implementation. Resolved by FR-004 and FR-012.
3. **Registry-payoff claim needed to be falsifiable.** "Confirm this is a
   data-entry addition" is an expectation, not a requirement. Restated as FR-030
   and SC-008 so a failed expectation shows up as a spec violation.

No [NEEDS CLARIFICATION] markers were needed: every open question was resolvable
from the dataset, the existing three-module implementation, or the constitution.

## Revision — 2026-08-11 (user review)

Two corrections raised by the user after the first draft:

1. **Factual error corrected.** The Assumptions section cited $19,438.61 as the
   maximum amount among the 390 non-zero `No Claim` rows. That figure is a real row
   (CL-00018) but ranks 13th, not 1st — it came from an early three-row sample and was
   written up as a maximum without ever being computed over the subset. The verified
   maximum is **$19,919.13**; the range is now stated as 8.52 to 19,919.13. The user
   caught this by independent verification.
2. **Anomaly retention added (FR-041 through FR-048, SC-011, SC-012).** The first draft
   discarded the 390 mismatches, noting the decision only in prose. Per user direction,
   no fabricated claim rows are created (that reasoning stands) but the anomaly is no
   longer silently lost: each is retained as a structured, queryable record so the later
   Fraud and Behavior phases can consume it.

**Mechanism decision, since the user offered two options.** The `audit_routes.py`
registry was rejected: it maps URL path prefixes to per-module role sets for the shared
refusal handler, and a load-time anomaly has no request, path, actor, or refusal — using
it would require inventing a fake route prefix. The underlying `AuditLog` was rejected
for a stronger reason: it is strictly append-only (queryset, `save()`, and a DB trigger),
so 390 fresh rows would accumulate on every load and a Phase 4 mismatch count would be
wrong by a factor of the number of runs. A **dedicated, per-row-reconciled anomaly
record** was chosen instead, which satisfies the load's existing idempotency requirement
(FR-035) — with a system-attributed audit entry alongside it (FR-048) so immutable
history of the observation is still kept.

Requirements were renumbered so the document reads in FR order: the anomaly block
took FR-041–FR-048 and the placeholder-removal requirement moved from FR-041 to FR-049.
Re-validated: FR-001–FR-049 contiguous and in order, SC-001–SC-012, no gaps, no
duplicates, no dangling references, no implementation-detail leaks.

## Revision — 2026-08-12 (user review, second pass)

**FR-044 refined: absence is not correction.** As first written, FR-044 cleared an
anomaly whenever it "no longer conflicts on a later run," which silently treated a row
vanishing from an export the same as a row coming back fixed. Only the second is
positive evidence; the first is the absence of evidence, and an export can drop a row
for reasons unrelated to the conflict (filtered, truncated, date-scoped, withdrawn).
Collapsing them would let a Phase 4 query count unexplained disappearances as verified
corrections — understating source inconsistency, and doing it invisibly.

FR-044 now names two clearing reasons, **corrected** and **absent from latest load**,
and the distinction propagates:

- **FR-044a** — an absent-cleared anomaly may not be presented as verified/corrected
  anywhere queryable, and confirmed-correction counts must be able to exclude it.
- **FR-044b** — an absent-cleared anomaly that conflicts again is re-raised as current,
  rather than staying cleared on the strength of a run that never observed it.
- **FR-048a** — the clearing audit entry records *which* reason applied, as a distinct
  value rather than prose. This is the load-bearing one: the anomaly record holds only
  the latest clearing, so for a row cleared and re-raised more than once, the
  append-only trail is the only place the full clearing history survives.
- **SC-013**, acceptance scenarios **9a**/**9b**, two edge cases, the `Claim load
  anomaly` entity, and a new Assumptions bullet were updated to match.

**Numbering.** Suffixed IDs (FR-044a, FR-044b, FR-048a) were used rather than
renumbering FR-045–FR-049 again. The previous revision already moved the
placeholder-removal requirement once; renumbering a second time would break references
in the spec body and this checklist for no analytical gain. Re-validated: FR-001–FR-049
contiguous with the three suffixed additions in place, SC-001–SC-013, no gaps, no
duplicates, no dangling references, no implementation-detail leaks.

**Left open for the user.** FR-044b re-raises an absent-cleared anomaly on a later
conflict. Whether an anomaly cleared as *corrected* that conflicts again should be
treated as a fresh anomaly or a recurrence is not specified — it needs a decision only
if Phase 4 wants to distinguish "chronically inconsistent row" from "newly inconsistent
row," and it is recorded here rather than guessed.

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`
