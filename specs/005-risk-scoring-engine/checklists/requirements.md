# Specification Quality Checklist: Phase 3a — Risk Scoring Engine

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-17
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

- [x] **Principle II (Auditability)**: addressed — FR-048 through FR-054 cover
      computation, refusal, batch-run, and rule-version auditing on the existing
      append-only record.
- [x] **Principle III (RBAC)**: addressed — FR-041 through FR-047 restrict reads to
      five roles and recomputation to two, enforced at the interface, with
      existence non-disclosure preserved.
- [x] **Principle IV (Explainable AI Outputs)**: addressed as the feature's central
      requirement — FR-019 through FR-029. This is the first phase where the
      principle applies; specs 001, 003 and 004 each recorded it N/A, verified in
      their plan.md files.
- [x] **Principle V (Test-First for Business Rules)**: addressed — SC-015 requires
      tests before or alongside the scoring code, covering every band and both
      sides of every tier boundary.

## Validation Notes

Validation run 1 (2026-08-17): all items pass on first iteration.

**Data grounding verified before finalizing factors.** The user required that
actual field distributions be checked against the real seeded dataset rather than
assumed. All queries were read-only against the running dev database
(3,000 customers / 3,000 policies / 2,246 claims / 390 open anomalies):

- Age 18–75, mean 46.5, quartiles 31/47/61 → five populated bands. **Adopted.**
- Policy type near-uniform: Property 767, Auto 767, Health 739, Life 727.
  **Adopted.**
- Claims history: 2,246 of 3,000 customers claim; Approved 769 / Filed 749 /
  Denied 728; 754 customers have no claim. **Adopted**, with zero-amount claims
  (1,143 of 2,246) as a distinct case per FR-013.
- Premium-to-claims ratio: exceeds 1× for 957 of 1,103 non-zero claims, 3× for
  695, 5× for 460; max 155×. Most discriminating factor available. **Adopted**,
  with a bounding top band.
- Denied claim present for 728 customers. **Adopted** as a factor distinct from
  claim existence.
- Gender (1,042/998/960) and lead source (770/747/746/737): near-uniform, no
  discriminatory power; gender additionally protected. **Rejected** — FR-017.
- Source `risk_score`: correlation 0.0018 with age, 0.0179 with premium, 0.0036
  with claim amount; flat mean across fraud flags (0.544/0.559/0.535); only 91
  distinct values over 3,000 rows. Indistinguishable from noise — **evidence for
  FR-055's replace-rather-than-preserve decision.**

**Tier discrimination pre-validated.** The adopted five-factor band structure was
simulated in SQL against all 3,000 seeded customers before SC-005 was written.
Resulting distribution: 33.4% / 32.0% / 16.9% / 17.7% across four tiers, observed
range 0–90 of 100. Every tier clears the 5% floor SC-005 asserts, so that success
criterion is known achievable rather than aspirational.

**No clarifications were required.** The request specified scope, the trigger
model, the RBAC mechanism, the audit mechanism, and the testing requirement
explicitly; every remaining decision was resolvable against the constitution, the
existing three modules, or the measured dataset, and each such decision is
recorded in Assumptions.
