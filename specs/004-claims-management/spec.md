# Feature Specification: Phase 2c — Claims Management

**Feature Branch**: `004-claims-management`

**Created**: 2026-08-11

**Status**: Draft

**Input**: User description: "Phase 2c - Claims Management. Real Claim model and CRUD API (apps/claims/), replacing Phase 1's placeholder endpoint. Fields per the Phase 0 CSV dataset: claim_status (Approved/Denied/No Claim/Filed), claim_amount_usd. Claim belongs to exactly one Policy (foreign key to apps.policies.Policy, using the existing dual-manager all_objects pattern - and explicitly work out whether Claims needs its own live-scoped-vs-reserved uniqueness question the way Policy did, or whether no natural uniqueness constraint applies here at all, since the dataset doesn't suggest one). RBAC per the existing HasRole mechanism, audit logging via the existing apps/core/audit_routes.py registry (Claims is the registry's third consumer - confirm this is now genuinely a data-entry addition, not new refactor work, proving out the registry design's actual payoff). Tests first per constitution Principle V. The CSV loader extends to seed Claim records tied to the Policy rows it creates. This is the last of three planned specs (Customer done, Policy done, Claims now) - once this completes, Phase 2 (Core Domain) is fully done."

## Overview

This feature delivers the platform's third and final core-domain entity: the
Claim — the request for payment made against a policy. Phase 2a established who
the customer is; Phase 2b established what they are covered for; this feature
establishes what they have asked the business to pay. With it, Phase 2 (Core
Domain) is complete, and the Risk, Fraud, and Behavior phases that follow have
the full record they need to score against.

Every claim is made against exactly one policy, never against a person directly.
That indirection is deliberate and is what makes the claim meaningful: the policy
carries the coverage type, the term, and the premium, so a claim inherits its
business context from the contract it was filed under rather than restating it.

Three boundaries are deliberate. First, this feature stores and returns claim
status as supplied; it does not implement adjudication. Nothing here decides
whether a claim should be approved, computes a payout, or enforces a workflow
between statuses — a status is a recorded fact, not a state machine, and the
approval logic that would justify one is not in this phase. Second, nothing here
scores a claim for fraud; the dataset's fraud signals live on the customer record
and are Phase 4 work. Third, this feature deliberately answers one open modeling
question rather than deferring it: the source data's `No Claim` status describes
the *absence* of a claim, so this spec settles what the system stores for a
policy that has never been claimed against (see FR-004 and the Assumptions). Where
that source data contradicts itself — a status denying a claim beside an amount
implying one — no claim is invented, but the contradiction is retained as a
queryable signal rather than dropped, because the phases that follow are exactly
the consumers who will want it (FR-041).

This is also the point where an earlier design choice is tested. Phase 2b moved
per-module refusal-audit knowledge out of the exception handler and into a
registry, explicitly so that Claims would be the third consumer and would need
no handler changes. That prediction is now checkable, and this spec treats it as
a requirement rather than a hope (FR-030).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Claims Adjuster Reviews Claims Against a Policy (Priority: P1)

A Claims Adjuster working an account needs to see what has been claimed against
a given policy — the status of each claim and the amount involved — without
having to reconcile a spreadsheet against the policy record by hand.

**Why this priority**: This is the feature's core read value and the reason the
entity exists. Without it, claim data is present but unusable, and every later
phase that scores claims has nothing to read.

**Independent Test**: Seed a policy with claims, request the claim list filtered
to that policy as a Claims Adjuster, and confirm the returned claims are exactly
that policy's, each showing status and amount.

**Acceptance Scenarios**:

1. **Given** a policy with three claims recorded against it, **When** a Claims
   Adjuster requests the claims for that policy, **Then** all three are returned,
   each with its status and amount.
2. **Given** claims recorded against several different policies, **When** a Claims
   Adjuster requests the claims for one policy, **Then** only that policy's claims
   are returned.
3. **Given** a claim record, **When** it is retrieved individually, **Then** the
   response identifies the policy it was filed against, and that policy's coverage
   type, without the caller needing a second request.
4. **Given** more claims exist than fit one response, **When** the list is
   requested, **Then** results are returned in stable pages so that no claim is
   omitted or repeated across pages.
5. **Given** a set of claims with mixed statuses, **When** the list is requested
   filtered to one status, **Then** only claims of that status are returned.

---

### User Story 2 - Administrator Seeds Claims From the Source Dataset (Priority: P1)

A System Administrator loads the source dataset and gets customers, policies, and
now claims from the same file in one run — and can re-run it safely, without
duplicating claims that already exist.

**Why this priority**: Equal to Story 1. The dataset is the only source of claim
volume; without the load, there is nothing substantial to read, and re-run safety
is what makes the command usable more than once.

**Independent Test**: Run the load against the source file, confirm claim records
exist tied to the correct policies, run it a second time, and confirm the claim
count is unchanged and nothing was duplicated.

**Acceptance Scenarios**:

1. **Given** the source dataset, **When** the load runs on an empty system,
   **Then** each row's claim is recorded against the policy created from that same
   row.
2. **Given** a system already loaded, **When** the load runs again on the same
   file, **Then** no duplicate claims are created and the run reports the claims as
   updated rather than created.
3. **Given** a row whose claim data is invalid, **When** the load runs, **Then**
   that row is refused and reported, the run continues, and no partial record from
   that row is left behind — neither customer, policy, nor claim.
4. **Given** the source dataset, **When** the load runs, **Then** the run reports
   separate created, updated, and refused counts for claims alongside those it
   already reports for customers and policies.
5. **Given** the load is run in a preview mode that writes nothing, **When** it
   completes, **Then** it reports the claim counts it would have produced and no
   claim is stored.
6. **Given** a row whose claim indicates no claim was ever made, **When** the load
   runs, **Then** the system's handling of that row is consistent with FR-004 and
   is reflected truthfully in the reported counts.
7. **Given** a row whose status denies a claim while its amount is non-zero, **When**
   the load runs, **Then** no claim is created, the contradiction is retained as a
   queryable anomaly naming that row's policy, and the row's customer and policy are
   still loaded normally.
8. **Given** a file containing anomalous rows, **When** the load is run three times,
   **Then** the retained anomaly count after the third run equals the count after the
   first.
9. **Given** a retained anomaly, **When** a later run supplies a corrected version of
   that row, **Then** the anomaly is no longer reported as current and is recorded as
   cleared because it was corrected.
9a. **Given** a retained anomaly, **When** a later run's file does not contain that
    row at all, **Then** the anomaly is no longer reported as current, is recorded as
    cleared because it was absent rather than corrected, and is excluded from any
    count of confirmed corrections.
9b. **Given** an anomaly cleared as absent, **When** a later run supplies that row
    still conflicting, **Then** it is reported as a current anomaly again, and both
    clearings remain distinguishable by reason in the audit trail.
10. **Given** anomalies have been retained, **When** the load reports its counts,
    **Then** the anomaly count is reported distinctly from created, updated, and
    refused.

---

### User Story 3 - Claims Adjuster Records and Corrects a Claim (Priority: P2)

A Claims Adjuster records a new claim against a policy, and corrects the status or
amount of an existing one when better information arrives.

**Why this priority**: Write access matters, but the dataset load already produces
the volume the platform demonstrates, so reading and seeding come first.

**Independent Test**: As a Claims Adjuster, create a claim against a live policy,
retrieve it, amend its status, and confirm the change is reflected and the
original values are recoverable from the audit trail.

**Acceptance Scenarios**:

1. **Given** a live policy, **When** a Claims Adjuster records a claim against it
   with a valid status and amount, **Then** the claim is stored and returned with
   its own identifier.
2. **Given** an existing claim, **When** a Claims Adjuster amends its status,
   **Then** the new status is stored and the previous one is recoverable from the
   audit trail.
3. **Given** a claim submitted with a negative amount, **When** it is submitted,
   **Then** it is refused, the amount is named as the offending field, and nothing
   is stored.
4. **Given** a claim naming a policy that does not exist, **When** it is submitted,
   **Then** it is refused and the policy is named as the offending field.
5. **Given** a claim naming a policy that has been archived, **When** it is
   submitted, **Then** it is refused and the policy is named as the offending
   field.
6. **Given** an existing claim, **When** a Claims Adjuster removes it, **Then** it
   no longer appears in claim listings or retrievals, and the removal is reversible
   rather than destructive.

---

### User Story 4 - Compliance Officer Traces a Claim's History (Priority: P2)

A Compliance Officer reviewing a disputed claim needs to see who changed its
status and amount, when, and what the values were before — including attempts by
users who were refused access.

**Why this priority**: Constitution Principle II requires it and claims are the
platform's highest-liability record, but it depends on the write operations in
Story 3 existing first.

**Independent Test**: Perform a create, an amendment, a removal, and a refused
access attempt against claims, then read the audit trail as a Compliance Officer
and confirm all four are present with actor, action, and before/after values.

**Acceptance Scenarios**:

1. **Given** a claim is recorded, **When** the audit trail is read, **Then** it
   shows who recorded it, when, and the values stored.
2. **Given** a claim's status is amended, **When** the audit trail is read,
   **Then** it shows the previous and new status, and records only the fields that
   actually changed.
3. **Given** a user without claim access attempts to read a claim, **When** the
   audit trail is read, **Then** the refused attempt is recorded, and the response
   that user received did not reveal whether the claim exists.
4. **Given** claims are seeded by the dataset load, **When** the audit trail is
   read, **Then** those entries are attributable to the system load rather than to
   a person.
5. **Given** any claim change is recorded, **When** an attempt is made to alter or
   remove that audit entry, **Then** it is rejected.

---

### User Story 5 - Roles Are Enforced on Every Claim Operation (Priority: P1)

Only the roles whose work involves claims may read them, and only those
responsible for claim handling may change them. Claim data is not visible to the
whole organization by default.

**Why this priority**: Constitution Principle III is non-negotiable, and claims
carry both financial detail and fraud-investigation relevance, so an over-broad
default here is a compliance failure rather than a convenience.

**Independent Test**: Attempt each claim operation once per role and confirm the
permitted set is allowed and every other role is refused, with the refusal
recorded.

**Acceptance Scenarios**:

1. **Given** an unauthenticated caller, **When** any claim operation is attempted,
   **Then** it is refused.
2. **Given** a role permitted to read but not to write claims, **When** it attempts
   to record or amend a claim, **Then** it is refused and nothing is stored.
3. **Given** a role not permitted to read claims, **When** it requests a claim that
   exists, **Then** the response does not reveal that the claim exists.
4. **Given** a role not permitted to read claims, **When** it requests a claim
   identifier that does not exist, **Then** the response is indistinguishable from
   the previous case.
5. **Given** a role permitted to read claims, **When** it requests a claim
   identifier that does not exist, **Then** the miss is not recorded as a refusal.

---

### Edge Cases

- **A policy is archived while claims exist against it.** The claims must remain
  readable and retain their link to that policy, so claim history is not lost when
  coverage is withdrawn (FR-008). Archiving a policy does not archive its claims.
- **A claim's amount is zero.** Zero is a legitimate stored value in the source
  data and must be accepted, distinguished from an absent amount, and never
  confused with a refusal (FR-011).
- **A claim's status says `No Claim` while an amount is present.** The source data
  contains 390 such rows. FR-004 and FR-012 settle what is stored (no claim), and
  FR-041 settles what is retained (a queryable anomaly), rather than leaving the
  contradiction to the implementation.
- **The same anomalous row is loaded five times.** The anomaly count must remain 390,
  not grow to 1,950 — which is why anomalies are reconciled per row rather than
  appended to an immutable log (FR-043).
- **A previously anomalous row is corrected in a later export.** The stale anomaly
  must stop being reported as current, or the record would contradict the source it
  was derived from (FR-044).
- **A previously anomalous row simply vanishes from a later export.** The anomaly
  must also stop being reported as current, but MUST NOT be recorded as corrected:
  nothing observed it being fixed. The two clearing reasons stay distinguishable, so
  a later phase cannot mistake an unexplained disappearance for a verified
  correction (FR-044, FR-044a, FR-048a).
- **A row cleared as absent conflicts again two exports later.** It must be reported
  as a current anomaly again rather than staying cleared, and the trail must show
  both clearings and their reasons (FR-044b, FR-048a).
- **A claim is amended to a status it already has.** The change must succeed
  without recording a field-level difference that did not occur (FR-026).
- **A policy is removed while claims exist against it.** Removal is archival, not
  deletion, so no claim is ever orphaned; a hard deletion of a policy carrying
  claims must be prevented outright (FR-009).
- **The same claim row is loaded twice.** The load must reconcile it in place
  rather than creating a second claim (FR-035).
- **A claim references a policy the loader refused.** No claim may be written for a
  row whose policy did not land (FR-038).
- **A permitted user requests a claim that was removed.** It is not disclosed, and
  the request is treated as an ordinary miss rather than a refusal (FR-021).
- **The source file omits the claim columns entirely.** The load must fail before
  writing anything rather than loading customers and policies and silently skipping
  claims (FR-037).

## Requirements *(mandatory)*

### Claim record and identity

- **FR-001**: The system MUST store a claim record carrying the claim status and
  the claim amount.
- **FR-002**: Every claim MUST be filed against exactly one policy, and the system
  MUST refuse a claim that names no policy.
- **FR-003**: A policy MUST be able to carry more than one claim, and the system
  MUST NOT refuse a claim on the grounds that its policy already carries one.
- **FR-004**: The system MUST NOT store a claim record for a source row whose
  status indicates that no claim was made; the absence of a claim MUST be
  represented by the absence of a claim record, not by a stored record whose status
  denies its own existence.
- **FR-005**: The system MUST record when each claim was first created and when it
  was last changed.
- **FR-006**: The system MUST expose a stable identifier for each claim,
  independent of any value carried over from the source dataset.
- **FR-007**: The system MUST NOT impose any uniqueness constraint across claim
  records. Nothing in the claim record — alone or in combination — identifies a
  claim naturally, and two claims against the same policy with the same status and
  the same amount are legitimately distinct events.
- **FR-008**: A claim record MUST remain readable when the policy it was filed
  against has been archived, and MUST retain its link to that policy.
- **FR-009**: The system MUST prevent the destruction of a policy that carries
  claims, so that no claim can be left referring to a policy that no longer exists.

### Validation

- **FR-010**: The system MUST refuse a claim whose status is not one of the
  recognized values, and MUST name the status as the offending field.
- **FR-011**: The system MUST refuse a claim whose amount is negative, and MUST
  name the amount as the offending field. A zero amount MUST be accepted and MUST
  remain distinguishable from an absent amount.
- **FR-012**: The system MUST refuse a claim submitted through the interface whose
  status indicates no claim was made, and MUST name the status as the offending
  field, consistent with FR-004.
- **FR-013**: The system MUST refuse a claim that names a policy which does not
  exist, and MUST name the policy as the offending field.
- **FR-014**: The system MUST refuse a claim that names a policy which has been
  archived, and MUST name the policy as the offending field.
- **FR-015**: Every refusal for invalid input MUST identify which field was
  invalid and MUST leave stored data unchanged.

### Operations

- **FR-016**: Users MUST be able to retrieve a single claim by its identifier.
- **FR-017**: Users MUST be able to list claims, and the list MUST be returned in
  stable pages such that no claim is omitted or repeated across pages.
- **FR-018**: Users MUST be able to restrict a claim list to a single policy.
- **FR-019**: Users MUST be able to restrict a claim list to a single status.
- **FR-020**: Users MUST be able to record a new claim, amend an existing claim's
  status and amount, and remove a claim.
- **FR-021**: Removal MUST be reversible rather than destructive: a removed claim
  MUST NOT appear in listings or retrievals, MUST NOT be disclosed as existing, and
  MUST remain recoverable in storage.
- **FR-022**: The system MUST NOT permit a claim to be reassigned to a different
  policy after it has been recorded.
- **FR-023**: A single claim retrieval MUST identify the policy the claim was filed
  against and that policy's coverage type, without requiring a second request.
- **FR-024**: The system MUST NOT decide, derive, or recompute a claim's status or
  amount in this feature; it stores and returns only what was supplied.

### Access control

- **FR-025**: Every claim operation MUST enforce role checks server-side, and MUST
  refuse an unauthenticated caller.
- **FR-026**: Reading claims MUST be permitted to the roles whose work requires
  claim visibility — claim handling, fraud investigation, compliance review, risk
  management, and system administration — and MUST be refused to all others.
- **FR-027**: Recording, amending, and removing claims MUST be restricted to claim
  handling and system administration, and MUST be refused to every other role,
  including roles permitted to read claims.
- **FR-028**: A caller not permitted to read a given claim MUST receive a response
  that does not reveal whether that claim exists, and that response MUST be
  indistinguishable from the response for an identifier that does not exist.

### Audit

- **FR-029**: Every claim creation, amendment, and removal MUST write an audit
  entry recording who acted, what action was taken, when, and the affected values.
- **FR-030**: Extending refusal auditing to claim routes MUST be accomplished by
  registering the claims module with the existing audited-route registry, and MUST
  NOT require changes to the shared refusal-handling behavior itself. The role sets
  registered for claims MUST be the claim role sets, not those of another module.
- **FR-031**: Every refused claim access attempt MUST be recorded, without altering
  the response the refused caller receives.
- **FR-032**: A permitted user's request for a claim that does not exist MUST NOT
  be recorded as a refusal.
- **FR-033**: An amendment MUST record only the fields whose values actually
  changed.
- **FR-034**: Each audit entry MUST be written together with the change it
  describes, such that a stored change without its audit entry cannot occur, and
  MUST NOT be alterable or removable afterwards.

### Dataset load

- **FR-035**: The existing dataset load MUST additionally record each row's claim
  against the policy created or reconciled from that same row, and MUST be safe to
  re-run: a second run over an unchanged file MUST NOT create duplicate claims.
- **FR-036**: The load MUST report separate created, updated, and refused counts
  for claims, alongside the counts it already reports for customers and policies.
- **FR-037**: The load MUST fail before writing anything if the source file omits
  the claim columns, rather than loading customers and policies and silently
  skipping claims.
- **FR-038**: A row whose claim data is invalid MUST be refused in full: no
  customer, policy, or claim from that row may persist, and the run MUST continue
  with the remaining rows.
- **FR-039**: The load MUST attribute claim audit entries to the system load rather
  than to a person.
- **FR-040**: The load's preview mode MUST report the claim counts it would produce
  and MUST write no claim.

### Retaining discarded anomalies

- **FR-041**: When a source row's claim status indicates no claim was made while its
  claim amount is non-zero, the system MUST create no claim record (per FR-004) and
  MUST record the discrepancy as a structured, queryable record rather than
  discarding it or reporting it only as console output.
- **FR-042**: Each retained anomaly MUST identify the policy the source row relates
  to, the conflicting status and amount as supplied, and the load run that observed
  it, such that a later consumer can find every anomaly for a given policy without
  access to the source file.
- **FR-043**: Anomaly retention MUST be idempotent: re-running the load over an
  unchanged file MUST NOT accumulate duplicate anomaly records for the same row, and
  MUST leave the total anomaly count unchanged.
- **FR-044**: An anomaly that no longer holds on a later run MUST NOT continue to be
  reported as a current anomaly, so that a corrected source file is reflected rather
  than contradicted. The system MUST distinguish the two reasons an anomaly stops
  holding, and MUST NOT record them as the same outcome:
  - **Corrected** — the row was present in the latest load and its status and amount
    no longer conflict. The load observed the resolution directly.
  - **Absent from latest load** — the row did not appear in the latest load at all.
    The conflict was neither observed to persist nor observed to be resolved, and the
    cause is unknown: the row may have been fixed, withdrawn, or omitted by an export
    that no longer covers it.
- **FR-044a**: An anomaly cleared as absent MUST NOT be represented as verified,
  corrected, or resolved anywhere it can be queried. Absence is the failure to observe
  a conflict, not evidence that the conflict was fixed, and a consumer MUST be able to
  exclude absent-cleared anomalies from any count of confirmed corrections.
- **FR-044b**: An anomaly cleared as absent that conflicts again in a later load MUST
  be reported as a current anomaly once more, rather than remaining cleared on the
  strength of the run that did not observe it.
- **FR-045**: The load MUST report a count of retained anomalies distinctly from its
  created, updated, and refused counts. An anomaly is not a refusal: the row's
  customer and policy MUST still be loaded normally.
- **FR-046**: The load's preview mode MUST report the anomaly count it would retain
  and MUST write no anomaly record.
- **FR-047**: Anomalies MUST be readable only by the roles permitted to read claims
  (FR-026), since an anomaly discloses claim-adjacent financial detail.
- **FR-048**: Recording anomalies MUST NOT alter the audit trail's existing meaning:
  the anomaly record is the queryable signal, and any audit entry written for it MUST
  be attributable to the system load rather than to a person.
- **FR-048a**: The audit entry written when an anomaly is cleared MUST name which of
  FR-044's two reasons applied — corrected, or absent from the latest load — as a
  distinct recorded value rather than as prose a reader must interpret. Because the
  audit trail is append-only, this record is what lets a later phase distinguish "we
  verified this was fixed" from "we stopped seeing it and assumed it was fine" for
  every clearing that has ever occurred, including anomalies cleared and re-raised
  more than once (FR-044b).

### Replacing the placeholder

- **FR-049**: The placeholder claims endpoint delivered in Phase 1 MUST be removed
  once the real claim operations exist, so that only one claims surface remains.

## Key Entities

- **Claim**: A request for payment made against a policy. Carries a status
  (approved, denied, or filed), an amount, creation and change timestamps, a
  reversible removal marker, and a stable identifier of its own. Has no natural
  identifying value: claims are distinguished only by their identifier (FR-007).
- **Policy** (existing, from Phase 2b): The contract a claim is filed against. A
  claim belongs to exactly one policy; a policy may carry many claims. A claim
  inherits its coverage context from its policy rather than restating it.
- **Customer** (existing, from Phase 2a): Reachable from a claim only through its
  policy. No claim references a customer directly.
- **Claim load anomaly**: A retained observation that a source row's claim data
  contradicted itself — a status denying a claim alongside a non-zero amount — for
  which no claim was created. Carries the policy it relates to, the conflicting
  status and amount as supplied, and when the load last observed it. Also carries
  whether it is currently holding or has been cleared, and — when cleared — which of
  FR-044's two reasons applied: corrected, or absent from the latest load. Exists so
  the signal is queryable by later phases without the source file (FR-041, FR-042).
  It is a record of what the source said, never evidence that a claim occurred, and
  a cleared-as-absent anomaly is never evidence that a conflict was resolved
  (FR-044a).
- **Audit entry** (existing, from Phase 1): The append-only record of who did what
  to which claim and when, including refused attempts. Distinct from a load anomaly:
  an audit entry is immutable history of an action, whereas an anomaly is current
  state re-derived from the source on each load (FR-043, FR-044). The one thing an
  anomaly's current state cannot carry is its own history: a row that is cleared and
  conflicts again retains only the latest clearing reason, so the audit trail is
  where every past clearing and its reason survive (FR-044b, FR-048a).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Claims Adjuster can retrieve every claim against a given policy in
  a single request, with each claim's status and amount present, and without
  issuing a further request to learn which coverage it relates to.
- **SC-002**: Loading the source dataset produces one claim for every row that
  records an actual claim, each tied to that row's policy, and produces no claim
  for rows recording that no claim was made.
- **SC-003**: Re-running the load over an unchanged file leaves the total number of
  claims unchanged and reports every claim as updated rather than created.
- **SC-004**: Every claim creation, amendment, and removal is traceable to an actor
  and a time, and the values before an amendment are recoverable, for 100% of such
  operations.
- **SC-005**: Every role outside the permitted read set is refused claim access,
  and every role outside the permitted write set is refused claim changes, with no
  exceptions across a full pass over all nine roles.
- **SC-006**: A caller not permitted to read claims cannot distinguish, from the
  response alone, a claim that exists from one that does not.
- **SC-007**: No claim can be removed in a way that destroys it, and no policy
  carrying claims can be destroyed; claim history survives the withdrawal of the
  coverage it relates to.
- **SC-008**: Adding claims to refusal auditing requires no change to the shared
  refusal-handling behavior — the change is limited to registering the claims
  module and its role sets.
- **SC-009**: Business-rule behavior in this feature — validation, role
  enforcement, audit writing, and load reconciliation — is covered by tests that
  fail before the behavior exists.
- **SC-010**: A single request for a page of claims returns results in a
  predictable order such that paging through the whole set yields each claim
  exactly once.
- **SC-011**: Every source row whose claim data contradicts itself is retained as a
  queryable anomaly — 390 of them in the current dataset — and each names the policy
  it relates to, so a later consumer can answer "which policies had inconsistent
  claim data" without the source file.
- **SC-012**: Re-running the load over an unchanged file leaves the anomaly count
  unchanged rather than multiplying it by the number of runs.
- **SC-013**: For any cleared anomaly, a consumer can determine from stored records
  alone whether the clearing was a confirmed correction or merely an absence from the
  latest load, and can produce a count of confirmed corrections that excludes every
  absent-cleared anomaly. No cleared anomaly is ambiguous as to which reason applied.

## Assumptions

- **Source dataset shape is settled, and verified directly against the file**: All
  3,000 rows carry a claim status of `Approved` (769), `No Claim` (754), `Filed`
  (749), or `Denied` (728). No claim column is blank in any row. Amounts run from
  0.00 to 19,988.98, with 1,507 rows at exactly 0.00 and no negative value
  anywhere. There is no claim identifier column, and no date column specific to a
  claim.
- **`No Claim` is not a claim, and is not stored as one** (FR-004, FR-012): It
  describes a policy that has never been claimed against. Storing it as a claim
  record would mean 754 rows asserting the existence of a claim whose status denies
  that it exists — and would corrupt every later count, average, and fraud signal
  computed over claims, since "how many claims does this policy have" would answer
  1 for a policy with none. The absence of a claim is therefore represented by the
  absence of a record. The load consequently produces roughly 2,246 claims from
  3,000 rows, and a skipped `No Claim` row is a legitimate outcome rather than a
  refusal, which is why FR-036's counts and FR-040's preview must report it
  truthfully rather than as an error.
- **The 390 contradictory rows are resolved by the same rule, not by trusting the
  amount** (FR-041): 390 rows say `No Claim` while carrying a non-zero amount,
  ranging from 8.52 to 19,919.13. The status is treated as authoritative and no
  claim is stored, rather than inferring a claim from the amount. This is chosen
  because the status is the field the business fills in deliberately, the amount in
  these rows is not corroborated by any other column, and inventing claims from an
  uncorroborated number would fabricate roughly 390 payment events that the source
  never asserted.
- **A mismatch is discarded as a claim but retained as a signal** (FR-041 through
  FR-044): Not creating a claim row is not the same as losing the observation. A
  status that denies a claim alongside an amount that implies one is precisely the
  kind of inconsistency the later Fraud and Behavior phases will want to query —
  and a mismatch that exists only in the source file is unavailable to them, since
  the file is not committed and is supplied at run time. Each mismatch is therefore
  recorded as a structured, queryable anomaly at load time, carrying the policy it
  relates to and the values that conflicted, so the signal outlives the load
  without any claim being fabricated.
- **Not seeing a conflict is not the same as seeing it resolved** (FR-044, FR-044a,
  FR-048a): An anomaly stops holding for two very different reasons. If the row comes
  back with a status and amount that agree, the load has positive evidence the source
  was fixed. If the row simply does not appear, the load has no evidence at all — the
  export may have been filtered, truncated, scoped to a date window, or the row
  withdrawn for reasons unrelated to the conflict. Collapsing both into "resolved"
  would let a Fraud and Behavior query count unexplained disappearances as verified
  corrections, which is the precise direction an anomaly signal must not err in: it
  would understate inconsistency in the source and do so invisibly. The two reasons
  are therefore recorded distinctly, and absence never upgrades to correction on its
  own — only a later load that actually observes the row can do that.
- **No uniqueness constraint applies to claims — this is a genuine difference from
  Policy, not an oversight** (FR-007): The user asked this be worked out explicitly,
  and the answer is that the question Policy faced does not arise here. Policy
  needed a live-scoped-versus-reserved decision because `(customer, policy_type)`
  is a real business constraint — a customer cannot hold two live auto policies —
  so archival had to either release or reserve that slot. Claims have no equivalent
  natural key. The dataset carries no claim identifier, and nothing else
  identifies a claim: `(policy, status, amount)` is not unique in principle,
  because a policyholder can legitimately file two separate claims of the same
  amount that are both approved. Adding a constraint over those fields would refuse
  a valid second claim, so the correct constraint is none at all, and the
  live-scoped-versus-reserved question is therefore moot rather than answered
  either way. The internal identifier is the only identity a claim has.
- **The dataset seeds one claim per policy; the model permits many** (FR-003):
  Every `Client_ID` appears exactly once and every `(Client_ID, Policy_Type)` pair
  is unique, so each row yields at most one claim. That is a property of this
  export, not of the business — multiple claims against one policy over a term is
  the normal case — so the record permits many. Because the file gives the loader
  no claim identifier, re-run reconciliation matches a row's claim on its policy
  (FR-035); this is sound precisely because the export carries one claim per
  policy, and is recorded here as a property of the seed path, not a constraint on
  the record.
- **The anomaly is a dedicated record, not an entry in the refusal-audit registry**
  (FR-041 through FR-044): Both options were considered and the registry was
  rejected on inspection of what it actually is. The audited-route registry maps URL
  path prefixes to per-module role sets so the shared exception handler can tell a
  permission refusal from an ordinary miss; a load-time data anomaly has no request,
  no path, no actor, and no refusal, so using it would mean inventing a fake route
  prefix for a code path no route reaches. The underlying audit record was rejected
  for a stronger reason: it is strictly append-only by design, while FR-043 requires
  the anomaly set be re-derivable per run. An append-only log would gain 390 fresh
  entries on every load, so a Phase 4 query counting mismatches would be wrong by a
  factor of however many times the loader had been run — the exact silent-miscount
  failure this retention exists to prevent. A reconciled record answers "which
  policies currently have contradictory claim data" correctly on every run, and an
  audit entry attributable to the system load (FR-048) still records that the load
  observed anomalies, so the immutable history is not lost either.
- **Anomalies are keyed to the policy, not to a claim** (FR-042): There is no claim
  to key to — that is the point of the record. The policy is the durable anchor the
  row does produce, which is what makes the anomaly joinable to coverage data by a
  later phase.
- **Claims are reused, not re-derived, from the registry** (FR-030): Verified
  against the existing implementation, the shared refusal handler holds no
  per-module knowledge — route prefix, target type, action names, and the role sets
  that separate a refusal from an ordinary miss all come from the registry. Claims
  is therefore expected to be a registration entry and nothing more. FR-030 states
  this as a requirement so that if the expectation turns out to be wrong, the
  discrepancy is a visible failure against the spec rather than quietly absorbed as
  extra work.
- **Claim role sets follow the Phase 1 placeholder, widened for oversight**: The
  placeholder already restricted claims to Claims Adjuster, Fraud Analyst, and
  System Administrator, and those three remain the core. Reads additionally admit
  Compliance Officer and Risk Manager, whose oversight function requires claim
  visibility. Writes are narrowed to Claims Adjuster and System Administrator:
  a Fraud Analyst investigates claims but does not adjudicate them, so read
  access without write access is the correct shape. Customer Service, Underwriter,
  Product Manager, and Executive Leadership are excluded from record-level claim
  access entirely — this is a narrower read set than Policy's, deliberately, because
  claim detail is financially and legally sensitive in a way product mix is not.
- **A claim cannot be moved between policies** (FR-022): Reassignment would silently
  rewrite the coverage context a claim was judged under, which is precisely the
  history an audit trail exists to preserve. Correcting a misfiled claim is
  therefore a removal plus a new record, both of which are audited.
- **Archiving a policy leaves its claims untouched** (FR-008): Consistent with
  Phase 2b's treatment of customers and policies, and for the same reason —
  cascading is not symmetric, since restoring the policy would leave claims
  archived unless a reverse cascade were also specified. Claim history outliving the
  coverage it relates to is also the behavior compliance review requires.
- **Zero is a value, not an absence** (FR-011): 1,507 rows carry an amount of
  exactly 0.00, so zero must be storable. A negative amount is refused even though
  the data contains none, because a negative claim is a data error rather than a
  refund, and the constraint is cheaper to add now than after later phases score
  against the field.
- **No claim date is stored**: The dataset has no claim-specific date column.
  `Last_Interaction` is a customer-level field and is not repurposed as a claim
  date, because doing so would assert a filing date the source never recorded. The
  creation timestamp (FR-005) records when the record entered this system, which is
  a different fact and is not presented as the claim's filing date.
- **Status is a recorded fact, not a workflow**: No transition rules are enforced
  between statuses — a claim may be amended from any status to any other permitted
  one. Enforcing a lifecycle would require an adjudication process that this phase
  does not deliver, and inventing one now would encode a workflow no requirement
  has specified.
- **The loader remains one command**: Extending the existing load is preferred over
  a separate claims loader, for the reason Phase 2b gave — all three records come
  from the same row of the same file, and a claim is meaningless without its policy.
- **Existing mechanisms are reused, not rebuilt**: Role enforcement uses the
  existing role-checking mechanism; audit entries use the existing append-only
  record and its established write path; refusal auditing uses the existing
  registry. This feature is expected to add no new permission mechanism, no new
  audit mechanism, and no new refusal-handling behavior.
- **No interface beyond the API**: This feature delivers claim data and its
  operations; screens are not in scope, consistent with the platform's API-first
  phasing.

## Dependencies

- **Phase 1 foundation (spec 001)**, complete: the user and role model, the
  role-checking mechanism, the append-only audit record and its write path, and the
  test and factory setup. Also supplies the placeholder claims endpoint this
  feature removes (FR-049).
- **Phase 2a Customer (spec 002)**, complete: the customer record and the CSV
  loader this feature extends further.
- **Phase 2b Policy (spec 003)**, complete: the policy record a claim is filed
  against, its dual-manager archival behavior, and the audited-route registry this
  feature registers with as its third consumer.
- **Source dataset file**, present at a path supplied at run time; not committed.

## Out of Scope

- Claim adjudication: deciding whether a claim should be approved or denied,
  computing a payout, or enforcing permitted transitions between statuses.
- Fraud scoring, fraud indicators, or fraud investigation queues over claims
  (Phase 4 Fraud). Retaining a load anomaly (FR-041) is explicitly *not* scoring it:
  this feature records that the source contradicted itself and stops there. Treating
  an anomaly as a fraud signal, weighting it, surfacing it in a queue, or drawing any
  inference from it belongs to Phase 4.
- Risk scoring that consumes claim history (Phase 3 Risk).
- Any interpretation of the discarded amounts in anomalous rows — they are retained
  as reported values, never as a claim, a payout, or an exposure figure.
- Alerting, notification, or escalation when anomalies are detected during a load.
- Claim reserves, reinsurance, recoveries, subrogation, or salvage.
- Payment, disbursement, or settlement of an approved claim.
- Claim documents, photographs, attachments, or adjuster notes.
- Claimant or third-party parties to a claim distinct from the policyholder.
- Any AI or language-model involvement in claim data.
- Backfilling a filing date for claims the source dataset did not date.
- User-facing screens for claims management.
- Customer self-service access to their own claims.
- Bulk create, bulk update, or data export through the interface.
