# Feature Specification: Phase 3a — Risk Scoring Engine

**Feature Branch**: `005-risk-scoring-engine`

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "Phase 3a - Risk Scoring Engine. A rules-based risk scoring system for Customer, replacing the currently-unused, storage-only risk_score field established in Phase 2a. Ground this explicitly in constitution Principle IV (Explainable AI Outputs) - this is the first phase where that principle applies (Phase 1's plan marked it N/A, no AI surface existed yet). The score MUST be a tiered/thresholded rules engine, not a black-box calculation - every score must be explainable via a dedicated read endpoint (e.g. GET /api/customers/{id}/risk-assessment/) that returns the score, its tier, and the specific factors that produced it (age, policy type, claims history, premium-to-claims ratio, or whichever factors the spec settles on against the real seeded dataset - verify actual field distributions before finalizing which factors are usable). Computation is on-demand only in this phase - a management command and/or an explicit API trigger recompute the score; NO automatic recompute on data changes, no Celery, no signals - that is explicitly out of scope, deferred to Phase 3b. RBAC per the existing HasRole mechanism, audit logging via the existing audit_routes.py registry (prove out the registry again as a fourth consumer), tests first per constitution Principle V. This is the first of two planned specs (3a now, 3b - automatic recompute via Celery - next)."

## Overview

This feature delivers the platform's first computed business decision. Phase 2
established the three core records — who the customer is, what they are covered
for, and what they have asked the business to pay. Every score field on those
records was stored exactly as the source file supplied it and interpreted by
nothing. This feature ends that: it computes a customer's risk from the platform's
own data, by a rule set stated in advance, and it makes every computed score
answerable to the question *why*.

That question is the feature. A risk score that cannot be explained is not usable
in an insurance context — a Risk Manager cannot defend it, a Compliance Officer
cannot audit it, and a customer cannot contest it. So the explanation is not a
reporting nicety layered on afterwards: the score and the reasons that produced it
are produced together, and the assessment operation returns both or neither. This
is the first phase in which constitution Principle IV (Explainable AI Outputs) has
any surface to apply to — Phases 1, 2b and 2c each recorded it as *not applicable*
because no feature produced a decision — and this spec is written to satisfy it
rather than to claim exemption from it.

The scoring itself is deliberately a **tiered, thresholded rule set, not a model**.
No training, no weights fitted to data, no opaque function. Each factor is a named
band with a stated point contribution, every contribution is attributable to a
specific fact about a specific record, and the total is their sum. This choice is
what makes the explanation truthful rather than reconstructed: the assessment does
not describe what the score *probably* came from, it reports the actual arithmetic
that produced it. A generated narrative that merely accompanies an opaque number
would satisfy the letter of an "explanation" and betray its purpose.

Three boundaries are deliberate. First, **computation is on demand only**. A score
changes when someone asks for it to be recomputed — through a batch command or an
explicit per-customer trigger — and never as a side effect of editing a customer,
a policy, or a claim. Automatic recomputation is real work with real failure modes
(ordering, retries, partial updates, queue outages) and it is the whole subject of
Phase 3b; smuggling it in here would deliver it untested and unspecified. The
consequence — that a stored score can be out of date relative to the data it was
computed from — is not hidden but surfaced, so that a stale score is visibly stale
rather than silently wrong.

Second, **the score is a recommendation, not an action**. Nothing in this feature
declines cover, adjusts a premium, flags a customer for investigation, or changes
any record other than the score and its assessment. Principle IV requires human
review, and this phase delivers exactly the input to that review.

Third, this feature **replaces the source-supplied `risk_score` values rather than
preserving them**, and the reason was verified rather than assumed. Measured
against the seeded dataset, the supplied score correlates with customer age at
0.002, with policy premium at 0.018, and with claim amount at 0.004; its mean is
flat across all three fraud-risk bands (0.544 / 0.559 / 0.535). It carries no
recoverable relationship to any fact the platform holds — it is indistinguishable
from noise, and it is the field this feature is asked to make real.

This is also the fourth consecutive test of an earlier design bet. Phase 2b moved
per-module refusal-audit knowledge out of the shared exception handler into a
registry so that each new module would be a registration entry rather than handler
surgery. Claims confirmed that for a third module; this feature registers a fourth
and treats the outcome as a requirement rather than a hope (FR-041).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Risk Manager Sees Why a Customer Scored As They Did (Priority: P1)

A Risk Manager reviewing a customer needs to see not just the risk score but the
reasoning behind it — which characteristics of this customer pushed the score up,
which pulled it down, and how much each one contributed — so they can judge
whether the assessment is sound before acting on it.

**Why this priority**: This is the feature's reason for existing and the
constitutional requirement it is built to satisfy. A score without its factors is
precisely the black-box output Principle IV forbids, so this story is not merely
the highest-value slice — it is the slice without which the feature must not ship.

**Independent Test**: Compute an assessment for a customer with known
characteristics, request that customer's risk assessment, and confirm the response
carries the score, its tier, and one entry per contributing factor naming the
factor, the customer's actual value for it, the band that value fell into, and the
points it contributed — with the contributions summing to the reported score.

**Acceptance Scenarios**:

1. **Given** a customer with a computed assessment, **When** a Risk Manager
   requests that customer's risk assessment, **Then** the response contains the
   numeric score, the named tier, and the list of factors that produced it.
2. **Given** an assessment returned by the system, **When** the individual factor
   contributions are added together, **Then** they total exactly the reported
   score, with no unexplained remainder.
3. **Given** a factor that contributed to a score, **When** its entry is examined,
   **Then** it states which factor it is, the customer's actual value for that
   factor, the band that value fell into, and the points that band contributed.
4. **Given** two customers whose scores differ, **When** both assessments are
   retrieved, **Then** the difference is fully accounted for by differences in
   their factor entries.
5. **Given** a factor that applied to a customer but contributed no points,
   **When** the assessment is retrieved, **Then** that factor is still reported
   with a zero contribution rather than omitted, so the absence of an effect is
   distinguishable from the absence of an evaluation.
6. **Given** a customer for whom a factor could not be evaluated because the
   underlying data is absent, **When** the assessment is retrieved, **Then** that
   factor is reported as not evaluable with the reason stated, rather than
   silently scored as zero.

---

### User Story 2 - Risk Manager Recomputes Scores Across the Book (Priority: P1)

A Risk Manager or System Administrator needs to compute risk scores for the whole
customer base — after the initial data load, after the rules are revised, or
simply to refresh assessments — through a single operation that reports what it
did.

**Why this priority**: Without a batch path there is no way to score 3,000
customers, and the feature would deliver a read operation with nothing to return. It
shares P1 with the explanation because the two together are the minimum viable
feature: the ability to produce scores and the ability to justify them.

**Independent Test**: Run the recompute operation across a seeded population and
confirm every eligible customer ends with a score, a tier, and a stored
assessment, with the operation reporting counts of what it scored, what it skipped,
and why.

**Acceptance Scenarios**:

1. **Given** a seeded customer population with no assessments, **When** the batch
   recompute is run, **Then** every eligible customer has a score, a tier, and a
   retrievable assessment.
2. **Given** a completed batch run, **When** its output is read, **Then** it
   reports how many customers were scored, how many were skipped, and the reason
   for each skip.
3. **Given** a population that has already been scored, **When** the batch is run
   again with no underlying data changed, **Then** the resulting scores are
   identical to the previous run.
4. **Given** a batch run over a large population, **When** it completes, **Then**
   the operation is recorded in the audit trail as a single attributable event
   rather than leaving the run itself untraceable.
5. **Given** a customer whose data cannot produce a score, **When** the batch runs,
   **Then** that customer is skipped with a stated reason and the run continues
   rather than aborting.
6. **Given** a batch run that fails partway through, **When** the failure occurs,
   **Then** customers already scored retain valid, complete assessments and no
   customer is left with a score whose factors are missing or a partial assessment.

---

### User Story 3 - Underwriter Triggers a Fresh Assessment for One Customer (Priority: P2)

An Underwriter looking at a single customer whose circumstances have just changed
needs that one customer's score recomputed immediately, without waiting for a
batch run over the entire book.

**Why this priority**: Valuable and clearly needed for day-to-day work, but the
feature is already viable with batch computation plus explanation. This is a
convenience and latency improvement over an existing capability rather than a new
one.

**Independent Test**: Change a customer's underlying data, trigger a recompute for
that customer alone, and confirm their score updates to reflect the change while
no other customer's score is touched.

**Acceptance Scenarios**:

1. **Given** a customer whose data has changed since their last assessment,
   **When** an authorised user triggers a recompute for that customer, **Then**
   their score and factors are recalculated from current data.
2. **Given** a single-customer recompute, **When** it completes, **Then** no other
   customer's score or assessment is modified.
3. **Given** a recompute that changes a customer's score, **When** the audit trail
   is examined, **Then** it records who triggered it, when, and both the previous
   and the new score.
4. **Given** a recompute that leaves the score unchanged, **When** the audit trail
   is examined, **Then** the recompute is still recorded as having occurred.
5. **Given** a customer with no prior assessment, **When** a recompute is
   triggered, **Then** an assessment is created rather than the request failing.

---

### User Story 4 - Compliance Officer Establishes What Was Decided and When (Priority: P2)

A Compliance Officer reviewing how a customer was treated needs to establish what
score the customer carried at a given time, what rules produced it, and who caused
it to be computed — without relying on anyone's recollection.

**Why this priority**: Auditability of a decision is a constitutional requirement
(Principle II) and the reason scoring can be used in a regulated context at all.
It sits below the primary explanation because it depends on scores existing first.

**Independent Test**: Trigger several recomputes for a customer over time, then
retrieve the audit history for that customer and confirm each computation is
recorded with actor, time, and the score before and after.

**Acceptance Scenarios**:

1. **Given** a customer whose score has been computed several times, **When** the
   audit history is retrieved, **Then** every computation appears with its actor,
   its timestamp, and the score before and after.
2. **Given** an assessment, **When** it is examined, **Then** it states which
   version of the scoring rules produced it, so a score computed under superseded
   rules is not mistaken for one computed under the current set.
3. **Given** an attempt to retrieve an assessment by a user whose role does not
   permit it, **When** the attempt is made, **Then** it is refused and the refusal
   is recorded in the audit trail.
4. **Given** an assessment record, **When** anything attempts to alter the audit
   entries describing it, **Then** the alteration is refused, consistent with the
   platform's append-only audit guarantee.

---

### User Story 5 - Stale Assessments Are Visibly Stale (Priority: P2)

Anyone reading a risk assessment needs to know whether it reflects the customer's
current data or data as it stood at some earlier point, so that an out-of-date
score is treated as out of date rather than as current.

**Why this priority**: This is the direct and foreseeable consequence of the
deliberate decision to compute on demand only. Without it, the phase boundary
between 3a and 3b becomes a correctness defect rather than a scope decision.

**Independent Test**: Compute an assessment, change data that feeds the score
without recomputing, retrieve the assessment, and confirm it is identifiable as
possibly out of date and states when it was computed.

**Acceptance Scenarios**:

1. **Given** an assessment, **When** it is retrieved, **Then** it states when it
   was computed.
2. **Given** a customer whose scoring-relevant data changed after their assessment
   was computed, **When** the assessment is retrieved, **Then** it is identifiable
   as potentially out of date.
3. **Given** a customer whose data has not changed since their assessment was
   computed, **When** the assessment is retrieved, **Then** it is not reported as
   out of date.
4. **Given** an out-of-date assessment, **When** it is retrieved, **Then** the
   stored score and factors are still returned as computed, rather than suppressed
   or silently recalculated on read.

---

### User Story 6 - Roles Are Enforced on Every Risk Operation (Priority: P1)

The organisation needs risk scores readable only by roles with a legitimate need,
and recomputation restricted more narrowly still, enforced at the interface rather
than by hiding controls.

**Why this priority**: Principle III is non-negotiable, and a risk assessment is
a judgment about a person that carries more sensitivity than the underlying record
it derives from. Enforcement must land with the first version of these operations, not
after.

**Independent Test**: Attempt every risk operation as each role and confirm
permitted roles succeed, non-permitted roles are refused, and refusals on
individual customers do not disclose whether that customer exists.

**Acceptance Scenarios**:

1. **Given** a user in a role permitted to read assessments, **When** they request
   one, **Then** it is returned.
2. **Given** a user in a role not permitted to read assessments, **When** they
   request one, **Then** the request is refused.
3. **Given** a user permitted to read assessments but not to trigger
   recomputation, **When** they trigger a recompute, **Then** it is refused and no
   score changes.
4. **Given** a user in a role not permitted to read assessments, **When** they
   request an assessment for a customer that does not exist and separately for one
   that does, **Then** the two responses are indistinguishable.
5. **Given** an unauthenticated caller, **When** they request any risk operation,
   **Then** it is refused.
6. **Given** any refused risk operation, **When** the audit trail is examined,
   **Then** the refusal is recorded with the actor and what they attempted.

---

### Edge Cases

- **A customer has no policy.** No premium and no coverage type exist, so two
  factors cannot be evaluated. The customer must not be scored as though those
  factors contributed zero, because zero is a real contribution meaning "this
  characteristic carries no additional risk" and that is a different claim from
  "this characteristic is unknown". Such a customer is skipped with a stated
  reason (FR-018).
- **A customer has a policy but no claims.** Every factor is evaluable: no claims
  is a genuine, favourable observation, not missing data. The customer is scored,
  with the claims factors contributing their no-claims band.
- **A customer's only claim has an amount of exactly 0.00.** 1,143 of the seeded
  claims are exactly zero, so this is a bulk case, not a curiosity. A zero-amount
  claim is a claim event that occurred but cost nothing; it must be scored
  differently from both "no claim at all" and "a claim of substance" (FR-013).
- **A customer's claim amount divided by premium is enormous.** The seeded maximum
  is 155× premium. The ratio factor must be bounded by its top band rather than
  scaling without limit, so a single extreme value cannot dominate the total score.
- **A customer is archived.** Archived customers are invisible to normal operation
  platform-wide; a recompute must neither score them nor fail because of them.
- **A policy is archived but the customer is not.** The customer's coverage-derived
  factors must be computed from live policies only, consistent with the platform's
  archival semantics elsewhere.
- **A claim is archived.** Archived claims do not count toward claims history, for
  the same reason.
- **A customer holds several policies.** The seeded data has exactly one policy per
  customer, but the model permits many, so the rules must state unambiguously how
  multiple policies combine rather than depending on the shape of one export.
- **A score is requested for a customer who has never been assessed.** The
  assessment does not exist yet; the response must say so distinctly rather than
  returning a zero score, which would be indistinguishable from a genuine
  lowest-possible assessment.
- **The rules change between two computations.** Assessments computed under
  different rule versions must remain distinguishable, so a score is never compared
  against another computed under different rules without that being apparent.
- **Two recomputes for the same customer run at once.** The customer must end with
  one internally consistent assessment — a score and the exact factor set that
  produced it — never a score from one run beside factors from another.
- **A customer's data changes during a batch run.** The assessment must reflect a
  single consistent read of that customer's data, not a mixture of before and after.
- **Every factor lands in its lowest band.** The minimum achievable score must be a
  legitimate, retrievable result and must not be confused with "not yet scored".
- **A customer's age is at a band boundary.** Band boundaries must be stated
  inclusively or exclusively without ambiguity, so a customer aged exactly 25
  cannot fall into two bands or neither.
- **A recompute is triggered for an archived or non-existent customer.** The
  response must be consistent with the platform's existence-non-disclosure rule for
  callers without read permission.

## Requirements *(mandatory)*

### The scoring rule set

- **FR-001**: The system MUST compute a customer's risk score by a deterministic
  rule set in which every factor is a named band with an explicitly stated point
  contribution, and the total is the sum of the contributions. No trained model, no
  fitted weights, and no non-deterministic step may participate in producing a
  score.
- **FR-002**: The same input data MUST always produce the same score, the same
  tier, and the same factor contributions.
- **FR-003**: The rule set MUST be defined in one place that is the single source
  of truth for both the computation and the explanation, so that the two cannot
  disagree about what the rules are.
- **FR-004**: The rule set MUST carry a version identifier that changes when the
  factors, bands, point values, or tier thresholds change.
- **FR-005**: The score MUST be expressed on a fixed, stated scale with defined
  minimum and maximum values, and MUST NOT be capable of falling outside that
  scale for any input the system accepts.
- **FR-006**: Every score MUST map to exactly one named tier, with thresholds
  stated in advance, and the tier MUST be derivable from the score alone.
- **FR-007**: Tier boundaries MUST be unambiguous — every possible score falls into
  exactly one tier, with no gap and no overlap.
- **FR-008**: The rules MUST state, for each factor, how a customer holding
  multiple policies is handled, rather than assuming one policy per customer.

### The factors

- **FR-009**: The system MUST use customer age as a scoring factor, banded, with
  the bands and contributions stated in the rule set.
- **FR-010**: The system MUST use the coverage type of the customer's policies as a
  scoring factor, banded by type.
- **FR-011**: The system MUST use the customer's claims history — whether claims
  exist and how many — as a scoring factor.
- **FR-012**: The system MUST use the ratio of claimed amount to premium as a
  scoring factor, banded, with a top band that bounds the contribution so no single
  extreme ratio can dominate the total.
- **FR-013**: A claim of exactly zero amount MUST be scored as a distinct case from
  both the absence of any claim and a claim of non-zero amount.
- **FR-014**: The system MUST use the presence of a denied claim as a scoring
  factor, distinct from the existence of a claim as such.
- **FR-015**: Every factor MUST be computable from data the platform already holds,
  with no new customer-supplied input required.
- **FR-016**: Factors MUST be computed from live records only — archived customers,
  policies, and claims MUST NOT contribute.
- **FR-017**: The system MUST NOT use any factor whose value distribution makes it
  incapable of discriminating between customers in the seeded data, and MUST NOT
  use gender or location as scoring factors.
- **FR-018**: When a factor cannot be evaluated because the data it requires is
  absent, the system MUST distinguish that from a factor evaluated as contributing
  zero, and MUST NOT produce a score that silently treats unknown as zero.

### The explanation

- **FR-019**: The system MUST provide a dedicated read operation returning a
  customer's risk assessment: the score, its tier, and the factors that produced it.
- **FR-020**: Each factor in the explanation MUST identify the factor, the
  customer's actual value for it, the band that value fell into, and the points
  that band contributed.
- **FR-021**: The contributions reported in the explanation MUST sum exactly to the
  reported score, with no unexplained remainder and no undisclosed adjustment.
- **FR-022**: A factor that contributed zero points MUST still appear in the
  explanation, so that no effect is distinguishable from no evaluation.
- **FR-023**: A factor that could not be evaluated MUST appear in the explanation
  marked as such, with the reason it could not be evaluated.
- **FR-024**: The explanation MUST be generated from the same stored factor record
  that the score was computed from, never reconstructed by re-deriving the reasoning
  after the fact.
- **FR-025**: The explanation MUST be intelligible to a business reader without
  reference to the implementation — factors and bands are named in business terms.
- **FR-026**: The assessment MUST state which rule-set version produced it.
- **FR-027**: The assessment MUST state when it was computed.
- **FR-028**: The system MUST present the score as an assessment for human review
  and MUST NOT take, trigger, or record any business action on the basis of it.
- **FR-029**: Requesting an assessment for a customer who has never been assessed
  MUST produce a response distinguishable from an assessment with a low score.

### Computation and triggering

- **FR-030**: The system MUST provide a batch operation that computes or recomputes
  scores across the customer population.
- **FR-031**: The batch operation MUST report how many customers it scored, how
  many it skipped, and the reason for each skip.
- **FR-032**: The batch operation MUST continue past a customer it cannot score,
  rather than aborting the run.
- **FR-033**: The batch operation MUST be re-runnable: running it again over
  unchanged data produces the same scores and does not accumulate duplicate
  assessments.
- **FR-034**: The system MUST provide an explicit per-customer recompute trigger
  that recalculates one customer's score without affecting any other.
- **FR-035**: A customer's score and the factor record explaining it MUST be
  written together as one atomic unit — no state may exist in which a stored score
  is accompanied by absent, partial, or superseded factors.
- **FR-036**: The computation MUST NOT be triggered automatically by the creation,
  modification, or archival of any customer, policy, or claim record.
  > **Superseded** by `specs/006-automatic-risk-recompute/spec.md`: this
  > requirement was scoped to this feature (Phase 3a) only, and automatic
  > recompute now exists platform-wide, triggered exactly as this FR
  > forbade — see 006's spec for the explicit, tested introduction of that
  > behavior and its own rationale. A reader of this spec alone should not
  > conclude automatic recompute still doesn't exist.
- **FR-037**: The computation MUST read each customer's data as a single consistent
  snapshot, so a change occurring mid-computation cannot produce an assessment
  mixing old and new values.
- **FR-038**: The system MUST record when each customer's underlying scoring data
  last changed, or otherwise provide a basis for determining whether a stored
  assessment predates a relevant change.
- **FR-039**: A retrieved assessment MUST indicate whether it may be out of date
  relative to the customer's current data.
- **FR-040**: An out-of-date assessment MUST still return its stored score and
  factors as computed, and MUST NOT be recalculated as a side effect of being read.

### Access control

- **FR-041**: Role enforcement MUST use the platform's existing role-checking
  mechanism, and refusal auditing MUST use the existing audited-route registry as a
  fourth registration entry, adding no new permission mechanism and no new
  refusal-handling behaviour. This is stated as a requirement so that if the
  registry proves insufficient, the shortfall is a visible failure against this spec
  rather than absorbed silently as extra work.
- **FR-042**: Reading a risk assessment MUST be restricted to Risk Manager,
  Underwriter, Fraud Analyst, Compliance Officer, and System Administrator.
- **FR-043**: Triggering a recomputation MUST be restricted to Risk Manager and
  System Administrator — a narrower set than the read set, because recomputation
  changes the record of a decision.
- **FR-044**: Access checks MUST be enforced at the interface layer on every risk
  operation, and MUST NOT rely on any client-side or presentation-level restriction.
- **FR-045**: A caller without permission to read a given customer's assessment
  MUST NOT be able to determine from the response whether that customer exists.
- **FR-046**: An unauthenticated caller MUST be refused every risk operation.
- **FR-047**: A role with permission to read assessments MUST NOT thereby gain
  permission to modify any customer, policy, or claim record.

### Audit

- **FR-048**: Every computation of a score MUST be recorded in the audit trail with
  the actor, the time, the customer affected, the previous score, and the new score.
- **FR-049**: A recomputation that leaves the score unchanged MUST still be
  recorded as having occurred.
- **FR-050**: A batch run MUST be recorded as an attributable event in its own
  right, distinguishable from the individual customer computations within it.
- **FR-051**: Every refused risk operation MUST be recorded with the actor, what
  they attempted, and the refusal outcome.
- **FR-052**: Audit entries for risk operations MUST use the platform's existing
  append-only audit record and its established write path, and MUST NOT be
  updatable or deletable.
- **FR-053**: An audit entry describing a computation MUST be written in the same
  transaction as the score it describes, so a failure to record leaves the score
  uncommitted.
- **FR-054**: The audit trail MUST identify the rule-set version under which each
  computation was performed.

### Replacing the stored field

- **FR-055**: The system MUST replace the source-supplied risk score values with
  computed ones, rather than preserving source values alongside computed ones as
  two competing meanings for the same field.
- **FR-056**: A customer's stored risk score MUST, after this feature, always be
  either a value this system computed under a stated rule version or absent — never
  an uninterpreted value carried over from an external file.
- **FR-057**: The dataset load path MUST NOT reintroduce source-supplied risk
  scores as though they were computed assessments.

## Key Entities

- **Risk Assessment**: The record of one customer's computed risk at one point in
  time — the score, its tier, the rule-set version that produced it, when it was
  computed, and who caused it. It is the record of truth for the decision, and it
  is never valid without its factors. Exactly one current assessment exists per
  scored customer.
- **Risk Factor Contribution**: One factor's part in one assessment — which factor,
  the customer's actual value, the band that value fell into, the points
  contributed, and whether the factor could be evaluated at all. These are the
  explanation. An assessment's contributions must sum to its score.
- **Risk Tier**: A named band of scores — the human-facing summary of a numeric
  result, derivable from the score alone, covering the full scale without gap or
  overlap.
- **Rule Set Version**: The identifier of the factors, bands, point values, and
  tier thresholds in force when an assessment was computed. It makes an assessment
  interpretable after the rules move on.
- **Customer** *(existing)*: The subject of an assessment. Its stored risk score
  becomes a computed output of this feature rather than a stored input.
- **Policy** *(existing)*: Supplies coverage type and premium — two factors and the
  denominator of a third.
- **Claim** *(existing)*: Supplies claims history, claimed amounts, and denial
  status.
- **Audit Log** *(existing)*: The append-only history of who computed what, when,
  and with what effect.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of computed assessments, the reported factor contributions
  sum exactly to the reported score.
- **SC-002**: For 100% of computed assessments, every factor in the rule set is
  represented in the explanation — as a contribution, a zero contribution, or an
  explicitly non-evaluable entry — with no factor silently omitted.
- **SC-003**: A Risk Manager can determine why any given customer received their
  score from a single request, without consulting a second source, reading the
  rules, or contacting anyone.
- **SC-004**: Running the scoring twice over unchanged data produces byte-for-byte
  identical scores, tiers, and factor contributions for every customer.
- **SC-005**: Across the full seeded population of 3,000 customers, every tier
  contains at least 5% of scored customers, demonstrating the rules discriminate
  rather than collapsing the book into one band.
- **SC-006**: The batch operation scores the full seeded population in a single run
  and reports counts of scored and skipped customers that together account for
  every customer in the population.
- **SC-007**: 100% of customers who cannot be scored are reported with a stated
  reason, and none is left with a score that was computed from incomplete data.
- **SC-008**: 100% of score computations appear in the audit trail with actor,
  timestamp, previous score, and new score.
- **SC-009**: 100% of attempts to read or recompute an assessment by a role without
  the required permission are refused and recorded.
- **SC-010**: For a caller lacking read permission, responses for an existing and a
  non-existent customer are indistinguishable in every observable respect.
- **SC-011**: No score changes as a result of any customer, policy, or claim being
  created, modified, or archived — verified by changing such data and confirming the
  stored score is unchanged until a recompute is explicitly requested.
  > **Superseded** by `specs/006-automatic-risk-recompute/spec.md` — see the
  > FR-036 note above. The still-true, narrower claim this feature's own
  > tests now verify is that no such change recomputes *synchronously*;
  > an asynchronous recompute is enqueued and eventually applied.
- **SC-012**: An assessment computed before a change to the customer's scoring data
  is identifiable as potentially out of date on retrieval, in 100% of such cases.
- **SC-013**: After this feature runs, 0% of customers carry a stored risk score
  that originated from the source file rather than from a computation under a
  stated rule version.
- **SC-014**: Every assessment identifies the rule-set version that produced it, so
  no two assessments computed under different rules can be compared without the
  difference being apparent.
- **SC-015**: Business-rule scoring code has tests written before or alongside it
  per constitution Principle V, with every factor band and every tier boundary
  covered by at least one test, including both sides of each boundary.

## Assumptions

- **The factor set was chosen against the real seeded data, not assumed**: Every
  candidate factor named in the request was checked against the 3,000-customer
  seeded database before being adopted or rejected. Age spans 18–75 (mean 46.5,
  quartiles 31 / 47 / 61) and populates five bands. Policy type is near-uniform
  across Property (767), Auto (767), Health (739) and Life (727). Claims exist for
  2,246 of 3,000 customers, split Approved 769 / Filed 749 / Denied 728, with 754
  customers having no claim at all. Premium runs 100.68–4,997.79 (median 2,576.47).
  The premium-to-claims ratio is the most discriminating factor available: among the
  1,103 non-zero claims it exceeds 1× for 957, 3× for 695 and 5× for 460, with a
  maximum of 155×. All five adopted factors discriminate on this data.
- **Gender and location are excluded deliberately, not overlooked**: Gender is
  near-uniform (1,042 / 998 / 960) and so carries almost no signal, and both fields
  are protected or proxy-protected characteristics whose use in insurance pricing
  carries regulatory exposure that a portfolio platform has no reason to incur.
  Their exclusion is a requirement (FR-017), not an omission.
- **Lead source is excluded**: Also near-uniform across four values (770 / 747 /
  746 / 737) and with no plausible causal relationship to claim risk. Including a
  factor of no discriminatory power would pad the explanation with noise, which
  works directly against the purpose of explaining.
- **The existing `fraud_risk_flag` is not used as a risk factor**: It is a Phase 5
  concern, it is itself an uninterpreted source value like the risk score this
  feature replaces, and its mean risk score is flat across all three of its levels
  (0.544 / 0.559 / 0.535) — so it would import unvalidated source data into a
  computation whose entire premise is that its inputs are known and stated.
- **The source-supplied risk score is noise, and this was measured**: Its
  correlation with age is 0.0018, with premium 0.0179, and with claim amount 0.0036,
  across 3,000 rows and only 91 distinct values. Nothing in the platform's data
  explains it. This is the evidence for FR-055's decision to replace rather than
  preserve it: there is no interpretation under which keeping it alongside a
  computed score would give the field a coherent meaning.
- **The claims-history factor must treat zero-amount claims as their own case**:
  1,143 of 2,246 seeded claims carry an amount of exactly 0.00 — a claim event that
  cost nothing. Folding them in with no-claim customers would erase the fact that an
  event occurred; folding them in with substantive claims would overstate exposure
  for half the claiming population. Hence FR-013.
- **A customer with no policy cannot be scored, and is skipped rather than
  defaulted**: Two of the five factors derive from a policy. The seeded data has one
  policy for every customer so this case does not arise there, but it arises the
  moment a customer is created through the API before cover is written. Scoring such
  a customer as though the missing factors contributed zero would state that their
  coverage carries no additional risk, which is a claim about data the system does
  not have.
- **Multiple policies are handled by an explicitly stated rule**: The seeded export
  carries exactly one policy per customer, but that is a property of the export, not
  of the business, and the record permits many. FR-008 therefore requires the rule
  set state the combination rule rather than letting the single-policy shape of this
  dataset become an unexamined assumption in the logic.
- **Scores are stored, not computed on read**: Storage is what makes the score
  auditable, comparable over time, and attributable to a rule version and an actor.
  Computing on read would make every retrieval a new decision with no history, would
  make Principle II's audit requirement meaningless for scoring, and would make the
  Phase 3b work of keeping scores fresh unnecessary in a way that hides rather than
  solves the staleness problem.
- **Staleness is disclosed rather than prevented**: On-demand-only computation
  necessarily allows a stored score to lag its inputs. That is an accepted
  consequence of the phase boundary, not a defect — but an undisclosed stale score
  is a defect, because a reader cannot tell a current assessment from an obsolete
  one. FR-039 makes the lag visible so that the deliberate scope limit does not
  become a correctness problem, and Phase 3b closes the lag itself.
- **The assessment is a decision input, never an action**: Nothing in this feature
  declines cover, prices a premium, opens an investigation, or notifies anyone.
  Principle IV requires human review of any output influencing a business decision,
  and this phase delivers the input to that review and stops there.
- **Rules-based, not model-based, is the point rather than a simplification**:
  Principle IV requires explanation of contributing factors, and a thresholded rule
  set makes the explanation identical to the computation. A fitted model would
  require the explanation to be a separate approximation of the score — a second
  artefact that can disagree with the first, which is precisely the failure mode the
  principle exists to prevent.
- **The registry is expected to absorb this module as configuration**: Verified
  against the existing implementation, the shared refusal handler holds no
  per-module knowledge — prefix, target type, action names and role sets all come
  from the registry. This feature is expected to need a registration entry and
  nothing more, and FR-041 states that as a requirement so a shortfall is visible.
- **Risk role sets are narrower than Customer's, deliberately**: Reading an
  assessment is restricted to five roles against Customer's seven, because a risk
  judgment about a person is more sensitive than the record it derives from —
  Customer Service has no need to see it, and Product Manager and Executive
  Leadership are excluded consistent with every prior module. Recomputation is
  narrower still at two roles: it rewrites the record of a decision, so an
  Underwriter may read an assessment without being able to change one.
- **Existing mechanisms are reused, not rebuilt**: Role enforcement uses the
  existing role-checking mechanism; audit entries use the existing append-only
  record and its established write path; refusal auditing uses the existing
  registry; batch computation follows the existing management-command pattern. This
  feature is expected to add no new permission mechanism, no new audit mechanism,
  and no new refusal-handling behaviour.
- **No interface beyond the API**: This feature delivers risk assessments and their
  operations; screens are not in scope, consistent with the platform's API-first
  phasing.

## Dependencies

- **Phase 1 foundation (spec 001)**, complete: the user and role model, the
  role-checking mechanism, the append-only audit record and its write path, and the
  test and factory setup.
- **Phase 2a Customer (spec 002)**, complete: the customer record, its age field,
  the storage-only risk score field this feature makes real, and the dataset loader.
- **Phase 2b Policy (spec 003)**, complete: coverage type and premium, and the
  audited-route registry this feature registers with as its fourth consumer.
- **Phase 2c Claims (spec 004)**, complete: claim existence, amounts, and status —
  three of the five scoring factors read from it.
- **Seeded dataset**, present: 3,000 customers, 3,000 policies, and 2,246 claims,
  against which the factor distributions in the Assumptions were verified.

## Out of Scope

- **Automatic recomputation of any kind (Phase 3b)**: no background jobs, no queue,
  no scheduled runs, no signal or hook on record changes, and no recomputation
  triggered by a read. This is the single largest exclusion and the reason this spec
  is 3a rather than 3.
- Any machine-learning model, trained scorer, fitted weight, or statistical
  inference — the exclusion is definitional, not deferred.
- Any language-model involvement in producing or narrating a score. The explanation
  is the computation's own record, not generated prose.
- Fraud scoring, fraud indicators, and any use of the existing fraud risk flag
  (Phase 4/5 Fraud).
- Renewal probability, cross-sell scoring, and behaviour or retention scoring —
  each is its own later phase, and each has its own storage-only field that this
  feature does not touch.
- Automatic action on a score: declining cover, adjusting a premium, opening an
  investigation, escalating, alerting, or notifying anyone.
- Premium pricing, rating tables, and underwriting rules.
- A stored history of every past assessment for trend analysis. This feature keeps
  the current assessment and the audit trail of computations; time-series risk
  analytics is a reporting-phase concern.
- Configuring the rules at run time — editing bands, thresholds, or point values
  through an interface. The rule set is defined in code with a version identifier.
- Backtesting, calibration, or validation of the rules against realised loss
  experience. The rules encode stated business judgment, and the seeded data carries
  no outcome column to calibrate against.
- Scoring any subject other than a customer — policy-level, claim-level, and
  portfolio-level risk.
- User-facing screens, dashboards, or reports for risk.
- Customer-facing disclosure of their own risk assessment.
- Bulk export of scores through the interface.
