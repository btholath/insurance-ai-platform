# Feature Specification: Phase 2b — Policy Management

**Feature Branch**: `003-policy-management`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Phase 2b - Policy Management. Real Policy model and CRUD API (apps/policies/), replacing Phase 1's placeholder endpoint. Fields per the Phase 0 CSV dataset: policy_type (Life/Auto/Property/Health), policy_start_date, policy_end_date, premium_usd, plus renewal_probability (nullable, storage only per the same deferred-scoring pattern as Customer's risk/fraud/cross-sell fields). Policy belongs to exactly one Customer (foreign key to apps.customers.Customer, using the existing dual-manager all_objects pattern for the same archived-row-reconciliation reasons as Customer). RBAC per the existing HasRole mechanism, audit logging including refusal tracking per the existing exception_handlers.py pattern, tests first per constitution Principle V. The loadcustomers-style CSV import extends to seed Policy records tied to the Customer rows it creates - same file, same gitignore discipline, same idempotency requirement. This is the second of three planned specs (Customer done, Policy now, Claims next) - Claims will depend on Policy, so keep this spec's Policy model genuinely complete and stable."

## Overview

This feature delivers the platform's second business entity: the Policy — the
contract that connects a customer to the coverage they hold. Phase 2a
established the customer record; a customer without a policy is a contact, not
a policyholder. This feature makes the platform describe actual insurance
business.

Every policy belongs to exactly one customer, and a customer may hold several.
That relationship is the point: it is what lets the organization ask what a
person is covered for, when that coverage lapses, and what they pay — and it
is the foundation Claims will build on, since a claim is made against a policy,
not against a person directly.

Three boundaries are deliberate. First, the policy record carries a renewal
probability, but this feature only **stores and displays** the value supplied
by the source data; nothing here computes or interprets it, exactly as Phase 2a
treated risk, fraud, and cross-sell scores. That logic is Phase 5 work. Second,
this feature adds no billing, payment, quoting, or underwriting-decision
behavior — a policy here is a record of an agreement, not a process that
produces one. Third, this is the second of three sequential specs, so the
policy record is settled now rather than sketched: Claims will reference these
policies, and the fields, identity rules, and removal behavior are decided here
precisely so the dependent feature need not revisit them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Underwriter Reviews a Customer's Coverage (Priority: P1)

An Underwriter examining an account opens a customer and sees every policy that
person holds — the type of coverage, when it starts and ends, and what it
costs. They can also search the whole book of business by policy type or by the
customer's details, to understand exposure across a segment rather than one
account at a time.

**Why this priority**: Reading policies is the most frequent interaction with
policy data and the reason the record exists. It is also what every later
feature depends on: Claims is meaningless without a policy to claim against,
and renewal and risk work both read from here. A working read path over
imported data is a demonstrable product on its own.

**Independent Test**: Load the source dataset, then open a known customer and
confirm their policies are listed; filter the full policy list by type and
confirm only matching policies return. Delivers value on its own: a searchable
book of business over real data.

**Acceptance Scenarios**:

1. **Given** policies exist, **When** an Underwriter requests the policy list,
   **Then** they receive policies in a stable, repeatable order, delivered in
   pages rather than all at once.
2. **Given** a customer holding policies, **When** the Underwriter requests
   that customer's policies, **Then** only that customer's policies are
   returned.
3. **Given** a known policy reference, **When** the Underwriter requests that
   single policy, **Then** the full record is returned including coverage type,
   both dates, premium, the owning customer, and any stored renewal
   probability.
4. **Given** policies of differing types, **When** the Underwriter filters by
   one coverage type, **Then** only policies of that type are returned.
5. **Given** a policy that does not exist, **When** the Underwriter requests it,
   **Then** the system reports that no such policy was found and reveals
   nothing further.
6. **Given** a policy list, **When** the Underwriter filters to policies whose
   coverage has already ended, **Then** only those policies are returned.

---

### User Story 2 - Administrator Seeds Policies From the Source Dataset (Priority: P1)

An operator loads the organization's existing dataset and receives both
customers and their policies in one step, each policy correctly attached to the
customer that holds it. Running the load again — after a crash, a partial run,
or a refreshed export — reconciles both record types rather than creating
duplicates of either.

**Why this priority**: Without data, none of the other stories can be
demonstrated at realistic volume. The idempotency requirement is P1 for the
same reason it was in Phase 2a: the natural operator response to a failed run
is to run it again, and a loader that duplicates on re-run is actively
dangerous. Attaching policies to the right customers is the part that cannot be
verified by eye at 3,000 records.

**Independent Test**: Run the load against the source file, confirm the
expected policy count and that every policy is attached to a customer; run it a
second time unchanged and confirm both counts are identical with no duplicates.
Delivers value on its own: a populated, reproducible book of business.

**Acceptance Scenarios**:

1. **Given** an empty platform and a valid source file, **When** the operator
   runs the load, **Then** customers and their policies are both created, every
   policy is attached to the customer named on its source row, and the operator
   is told how many of each were created.
2. **Given** the load has already been run once, **When** it is run again on the
   same unchanged file, **Then** the total number of policies is unchanged, no
   duplicate policies exist for any customer, and the operator is told that
   records were matched and updated rather than created.
3. **Given** the load has already been run and a source row's policy details
   have since changed, **When** the load is run again, **Then** the existing
   policy reflects the new details rather than a second policy being created
   for that customer.
4. **Given** a customer whose record was archived after an earlier load,
   **When** the load is run again, **Then** that customer's policy reconciles
   against the existing archived customer rather than creating a duplicate
   customer or an orphaned policy.
5. **Given** a source row whose policy details fail validation, **When** the
   load runs, **Then** the operator is told which row failed and why, and no
   partial policy is left behind from that row.
6. **Given** a source file with columns the policy record does not use, **When**
   the load runs, **Then** the extra columns are ignored without error, so that
   claim columns in the same file cause no failure here.

---

### User Story 3 - Underwriter Creates and Corrects Policy Records (Priority: P2)

An Underwriter writes a new policy for an existing customer, and later corrects
one when a premium is repriced, a term is extended, or a coverage type was
recorded wrongly. The system rejects entries that are not coherent — a policy
that ends before it starts, a negative premium, an unrecognized coverage type,
or a policy attached to no customer at all.

**Why this priority**: Create and update are essential to a complete policy
module, but the platform is usable and demonstrable without them once the
dataset is loaded and readable. They rank below the read and load paths that
everything else depends on.

**Independent Test**: Create a policy against an existing customer and confirm
it is retrievable from that customer's policy list; attempt several incoherent
entries and confirm each is refused with a clear reason.

**Acceptance Scenarios**:

1. **Given** an existing customer, **When** an Underwriter creates a policy for
   them with valid details, **Then** the policy is stored, attached to that
   customer, and immediately retrievable.
2. **Given** an existing policy, **When** the Underwriter changes only the
   premium, **Then** that field is updated and every other field retains its
   previous value.
3. **Given** an entry whose end date is on or before its start date, **When** it
   is submitted, **Then** the system refuses it and identifies the dates as the
   problem.
4. **Given** an entry with a negative or zero premium, **When** it is
   submitted, **Then** the system refuses it and identifies the premium as the
   problem.
5. **Given** an entry naming a customer that does not exist, **When** it is
   submitted, **Then** the system refuses it and identifies the customer as the
   problem.
6. **Given** an entry with an unrecognized coverage type, **When** it is
   submitted, **Then** the system refuses it and names the coverage type as the
   problem.
7. **Given** a customer who already holds a policy, **When** a second policy of
   a different type is created for them, **Then** it is stored successfully,
   because holding several policies is normal.

---

### User Story 4 - Compliance Officer Traces Who Changed a Policy (Priority: P2)

A Compliance Officer investigating a coverage dispute examines the history of a
specific policy and sees every creation, modification, and removal — who
performed it, when, and what the values were before and after. Attempts that
were refused for lack of permission are recorded too. The record of those
actions cannot be altered or erased.

**Why this priority**: Auditability is constitutionally non-negotiable
(Principle II) and cannot be reconstructed after the fact, so it ships with the
write operations it describes. It is P2 because it has no meaning until those
write operations exist.

**Independent Test**: Create, update, and delete a policy, then retrieve that
policy's history and confirm three corresponding entries with actor, timestamp,
and before/after values; attempt a refused operation and confirm it is recorded
as a refusal.

**Acceptance Scenarios**:

1. **Given** an Underwriter creates a policy, **When** the Compliance Officer
   examines its history, **Then** an entry records who created it, when, and
   the values it was created with.
2. **Given** a policy's details are changed, **When** the Compliance Officer
   examines the history, **Then** an entry records the changed fields with both
   their previous and their new values, and no unchanged field appears.
3. **Given** a policy is removed, **When** the Compliance Officer examines the
   history, **Then** an entry records who removed it, when, and the values it
   held at the time of removal.
4. **Given** an attempt to create or change a policy that the system refuses for
   lack of permission, **When** the Compliance Officer examines the history,
   **Then** the refused attempt is recorded as a refusal, with the policy record
   itself unchanged.
5. **Given** a change to a policy fails partway through, **When** the outcome is
   examined, **Then** either both the policy change and its history entry are
   present, or neither is — never one without the other.

---

### User Story 5 - Roles Are Enforced on Every Policy Operation (Priority: P1)

Each role can do only what its job requires with policy data. Roles whose work
depends on coverage context can read policies. Only the roles responsible for
underwriting may create, change, or remove them. Every other role is refused,
and the refusal happens on the server regardless of how the request was
constructed.

**Why this priority**: Principle III is non-negotiable and applies the moment
business data exists. Policy data carries premium and coverage terms — the
commercial terms of a customer relationship — so enforcement cannot lag behind
the data by even one release.

**Independent Test**: Attempt every policy operation once as each of the nine
roles and once with no identity, and confirm the outcome matches the permission
matrix in FR-026.

**Acceptance Scenarios**:

1. **Given** a user holding a role permitted to view policies, **When** they
   list or open a policy, **Then** the request succeeds.
2. **Given** a user holding a role not permitted to view policies, **When** they
   request the policy list, **Then** the request is refused.
3. **Given** a user permitted to view but not to modify policies, **When** they
   attempt to create, change, or remove one, **Then** the request is refused and
   the data is unchanged.
4. **Given** a user with no established identity, **When** they request a
   specific existing policy, **Then** the request is refused without revealing
   whether that policy exists.
5. **Given** a user whose role is changed by an administrator, **When** they next
   attempt a policy operation, **Then** the decision reflects their new role
   rather than their previous one.

---

### Edge Cases

- **Policies of an archived customer**: Archiving a customer does not archive
  their policies, and does not hide them. The policy remains readable and keeps
  its link to that customer, so coverage and claims history are never destroyed
  by a removal performed on the customer record. This is the deliberate
  counterpart to the Customer feature's guarantee that removal never orphans
  downstream records.
- **Creating a policy for an archived customer**: Refused. A customer that has
  been removed from active use must not acquire new coverage; the refusal names
  the customer as the problem.
- **Removal of a policy with dependents**: Claims do not yet exist but will
  reference policies. Removing a policy must never become a mechanism for
  silently destroying future claim history, so the removal behavior in FR-021 is
  chosen now rather than revisited when Claims arrives.
- **Multiple policies per customer**: A customer may hold several policies. The
  source dataset happens to carry exactly one per customer, but that is a
  property of this export, not of the business, and the record must not encode
  it as a rule.
- **Coverage that has already ended**: A policy whose end date has passed
  remains a valid, readable record. Expiry is a property to be observed and
  filtered on, not a reason to hide or delete the record.
- **Backdated and future-dated policies**: A policy may legitimately start in the
  past or in the future. Neither is refused; only an end date that fails to
  follow its start date is.
- **Missing renewal probability**: Renewal probability is absent for any policy
  created through the interface rather than loaded from the dataset. An absent
  value must be distinguishable from a value of zero, and must not be displayed
  or treated as a computed score.
- **Interrupted load**: A load that stops partway must leave both customers and
  policies in a state the operator can reason about, and re-running must
  reconcile rather than duplicate either record type.
- **Search with no matches**: A search or filter matching no policies returns an
  empty result set, not an error.

## Requirements *(mandatory)*

### Policy record and identity

- **FR-001**: The system MUST store a policy record carrying the coverage type,
  the start date, the end date, and the premium amount.
- **FR-002**: Every policy MUST belong to exactly one customer, and the system
  MUST refuse a policy that names no customer.
- **FR-003**: A customer MUST be able to hold more than one policy, and the
  system MUST NOT refuse a policy on the grounds that its customer already holds
  one.
- **FR-004**: The system MUST store, for each policy, a renewal probability
  which MAY be absent, and MUST distinguish an absent value from a zero one.
- **FR-005**: The system MUST NOT compute, derive, recompute, or interpret the
  renewal probability in this feature; it stores and returns only what was
  supplied.
- **FR-006**: The system MUST record when each policy was first created and when
  it was last changed.
- **FR-007**: The system MUST expose a stable identifier for each policy that
  later claim records can reference, independent of any value carried over from
  the source dataset.
- **FR-008**: The policy record MUST remain readable when the customer it
  belongs to has been archived, and MUST retain its link to that customer.

### Validation

- **FR-009**: The system MUST refuse a policy whose coverage type is not one of
  the recognized values, and MUST name the coverage type as the offending field.
- **FR-010**: The system MUST refuse a policy whose end date is on or before its
  start date, and MUST identify the dates as the problem.
- **FR-011**: The system MUST refuse a policy whose premium is zero or negative,
  and MUST name the premium as the offending field.
- **FR-012**: The system MUST refuse a policy whose renewal probability falls
  outside 0 to 1 inclusive.
- **FR-013**: The system MUST refuse a policy that names a customer which does
  not exist, and MUST name the customer as the offending field.
- **FR-014**: The system MUST refuse a policy that names a customer which has
  been archived, and MUST name the customer as the offending field.
- **FR-015**: Every refusal for invalid input MUST identify which field was
  invalid and MUST leave stored data unchanged.

### Operations

- **FR-016**: Users MUST be able to create a policy, retrieve a single policy,
  list policies, change a policy, and remove a policy, subject to the
  permissions in FR-026.
- **FR-017**: The system MUST support changing a subset of a policy's fields
  without requiring or altering the remainder.
- **FR-018**: The system MUST return policy lists in bounded pages with a
  stable, repeatable ordering, and MUST report the total number of matching
  policies.
- **FR-019**: Users MUST be able to retrieve all policies belonging to a
  specified customer.
- **FR-020**: Users MUST be able to filter the policy list by coverage type, and
  to filter to policies whose coverage has already ended as at the date of the
  request.
- **FR-021**: Removing a policy MUST be a reversible archival — the record
  ceases to appear in lists and single-record retrieval, but is retained so that
  claims added in later features can never be orphaned by a removal performed
  here.
- **FR-022**: Archiving a customer MUST NOT archive, hide, or unlink that
  customer's policies.
- **FR-023**: Requesting a policy that does not exist, or that the requester is
  not permitted to see, MUST NOT disclose whether that policy exists.

### Access control

- **FR-024**: The system MUST enforce every permission decision on the server for
  every policy operation, using the platform's existing role-checking mechanism,
  with no reliance on the interface hiding an action.
- **FR-025**: A permission decision MUST reflect the user's role as it stands at
  the moment of the request, not as it stood at any earlier point.
- **FR-026**: The system MUST apply the following permissions:

  | Role | View policies | Create / change / remove |
  |------|---------------|--------------------------|
  | Underwriter | Yes | Yes |
  | System Administrator | Yes | Yes |
  | Customer Service | Yes | No |
  | Claims Adjuster | Yes | No |
  | Fraud Analyst | Yes | No |
  | Risk Manager | Yes | No |
  | Compliance Officer | Yes | No |
  | Product Manager | Yes | No |
  | Executive Leadership | No | No |
  | No established identity | No | No |

- **FR-027**: Holding the System Administrator role MUST be the basis of that
  role's access; no separate superuser status may bypass the role check.

### Audit

- **FR-028**: The system MUST record an audit entry for every successful
  creation, change, and removal of a policy, capturing who acted, what action
  was taken, which policy it targeted, and when.
- **FR-029**: An audit entry for a change MUST capture the previous and new
  values of the fields that changed, and MUST NOT record fields that did not
  change.
- **FR-030**: An audit entry for a removal MUST capture the policy's values as at
  the moment of removal.
- **FR-031**: The system MUST record an audit entry when a policy operation is
  refused for lack of permission, marked as a refusal.
- **FR-032**: A refusal recorded under FR-031 MUST be distinguishable from an
  ordinary request for a policy that does not exist; a permitted user requesting
  a missing policy MUST NOT produce a refusal entry.
- **FR-033**: A policy change and its audit entry MUST both succeed or both fail;
  the system MUST NOT leave a change recorded without its audit entry or an audit
  entry without its change.
- **FR-034**: Audit entries for policy operations MUST be subject to the
  platform's existing append-only guarantee — no operation in this feature may
  alter or remove one.
- **FR-035**: Retrievals of policy data are NOT required to produce audit
  entries in this feature.

### Dataset load

- **FR-036**: An operator MUST be able to load customers and their policies from
  the source dataset file in a single command, with the file's location supplied
  at run time and no default that assumes a committed file.
- **FR-037**: Each loaded policy MUST be attached to the customer named on its
  source row.
- **FR-038**: The load MUST be idempotent for policies: running it repeatedly on
  unchanged input MUST leave exactly one policy per source row.
- **FR-039**: The load MUST match an existing policy on the combination of its
  customer and its coverage type, rather than on the customer alone, so that a
  customer holding several policies of different types reconciles correctly
  rather than having one policy repeatedly overwritten.
- **FR-040**: The load MUST update the stored details of a policy whose source
  row has changed since the previous run.
- **FR-041**: The load MUST reconcile a policy against an existing archived
  customer rather than creating a duplicate customer or an unattached policy.
- **FR-042**: The load MUST ignore source columns that neither the customer nor
  the policy record uses, so that the same file can later be used to load claims.
- **FR-043**: The load MUST apply the same validation rules as FR-009 through
  FR-014, and MUST report the identifying position and reason for any row it
  refuses.
- **FR-044**: The load MUST report, on completion, how many policies were
  created, how many were updated, and how many rows were refused, separately
  from the corresponding customer counts.
- **FR-045**: A source row whose policy details are refused MUST NOT leave a
  partially-created policy behind, and MUST NOT silently discard the customer
  created or matched from that same row.
- **FR-046**: The load MUST fail clearly, creating nothing, when the supplied
  file is missing, unreadable, or lacks the columns the policy record requires.
- **FR-047**: The source dataset file MUST NOT be committed to the repository.
- **FR-048**: The load MUST be usable without an interactive user session, and
  its audit entries MUST identify it as a system load rather than attributing
  the records to a person who did not enter them.

### Replacing the placeholder

- **FR-049**: The placeholder policy endpoint delivered in Phase 1 MUST be
  removed, along with the tests that assert its placeholder response, so that no
  route serves a fixed non-record response after this feature.

## Key Entities

- **Policy**: A contract of coverage held by one customer. Carries the coverage
  type, the period it runs for, the premium charged, and a stored renewal
  probability that later features will produce and this feature only holds.
  Identified by the platform's own record identifier. Belongs to exactly one
  Customer; a Customer may hold many. Will be referenced by Claim records in the
  next feature.

- **Customer** *(existing, from Phase 2a)*: The person holding the policy.
  Unchanged by this feature except that it gains policies referring to it.
  Its archival behavior interacts with this feature per FR-008 and FR-022.

- **Audit Entry** *(existing, from Phase 1)*: The append-only record of who did
  what to which record and when. This feature adds policy creations, changes,
  removals, and refusals to it; it does not change how audit entries work.

- **User and Role** *(existing, from Phase 1)*: The acting person and their
  single organizational role, which determines what policy operations they may
  perform. Unchanged by this feature.

## Success Criteria *(mandatory)*

- **SC-001**: An operator loads the complete source dataset in a single command,
  and the platform afterwards holds exactly 3,000 policies, each attached to a
  distinct customer.
- **SC-002**: Re-running the load on the unchanged file leaves the policy count
  at exactly 3,000, with no customer holding a duplicate policy of the same
  coverage type.
- **SC-003**: An Underwriter retrieves any single policy in under 1 second with
  the full dataset loaded.
- **SC-004**: A request for one customer's policies, or a filtered policy list,
  returns its first page in under 2 seconds with the full dataset loaded.
- **SC-005**: All 9 roles and the unidentified case are exercised against every
  policy operation, and 100% of the resulting outcomes match the permission
  matrix in FR-026.
- **SC-006**: 100% of successful policy creations, changes, and removals produce
  a corresponding audit entry; a sampled change entry shows the correct before
  and after values for exactly the fields that changed.
- **SC-007**: Every validation rule in FR-009 through FR-014 is demonstrated to
  refuse at least one invalid value and accept at least one valid boundary value.
- **SC-008**: A customer is archived while holding a live policy, and that policy
  remains retrievable with its customer link intact.
- **SC-009**: A policy is created for a customer who already holds one, and both
  policies are retrievable for that customer.
- **SC-010**: Automated tests covering the policy record's validation, identity,
  relationship, permission, and audit behavior are written before the
  corresponding implementation, and measured coverage of the policy module is at
  least 95%, consistent with the level established in Phases 1 and 2a.
- **SC-011**: No route in the platform returns the Phase 1 placeholder policy
  response after this feature is complete.
- **SC-012**: A removed policy is absent from every list and single-record
  retrieval, while remaining reconcilable on a subsequent load rather than
  producing a second record.

## Assumptions

- **Source dataset shape is settled**: Verified directly against the file rather
  than assumed. All 3,000 rows carry a coverage type of `Life`, `Auto`,
  `Property`, or `Health`; premiums span 100.68 to 4997.79; renewal probabilities
  span 0.0 to 1.0; start dates span 2022-06-18 to 2025-06-16 and end dates
  2025-06-17 to 2028-06-15. No row has an end date on or before its start date,
  and there are no blank cells in any policy column.
- **One policy per customer in this export, not in the model**: Every
  `Client_ID` appears exactly once, so the dataset seeds exactly one policy per
  customer. This is a property of this particular export, not of the business —
  a customer holding auto and home cover is the normal case — so the record
  permits many policies per customer (FR-003) even though the seed produces one
  each. The loader therefore matches on customer **and** coverage type (FR-039)
  rather than customer alone, so that a customer who later holds several
  policies reconciles correctly instead of having a single policy repeatedly
  overwritten.
- **Archiving a customer leaves policies untouched**: Chosen over cascading the
  archive, and over refusing to archive a customer who holds policies. Cascading
  is not symmetric — restoring the customer would leave policies archived unless
  a reverse cascade were also specified, and Claims would inherit the same
  problem. Refusing the archive was rejected on evidence: every one of the 3,000
  seeded customers holds a live policy, so that rule would make the entire
  customer base undeletable and would break the removal path Phase 2a already
  ships.
- **Premium must be positive**: The dataset's minimum is 100.68, so a zero or
  negative premium is not a case this data exercises. It is refused anyway,
  because a policy with no premium is a data error rather than a free policy,
  and the constraint is far cheaper to add now than after Claims depends on it.
- **Dates are stored as supplied**: Start and end dates are calendar dates, not
  timestamps; no timezone interpretation is applied to them.
- **Expiry is derived, not stored**: Whether coverage has ended is determined by
  comparing the end date to the date of the request, not by a stored status
  field that would need maintaining. This keeps FR-020's filter always correct
  without a scheduled job.
- **Product Manager may read policies but not write them**: Unlike the customer
  module, where Product Manager was excluded because the need is aggregate
  reporting over personal data, policy type and premium mix are ordinary product
  concerns. Executive Leadership remains excluded from record-level access,
  consistent with Phase 2a.
- **Existing mechanisms are reused, not rebuilt**: Role enforcement uses the
  existing role-checking mechanism; audit entries use the existing append-only
  record and its established write path. This feature adds neither a new
  permission mechanism nor a new audit mechanism. It does, however, require
  extending the existing refusal-recording behavior beyond the customer routes it
  currently covers — that is real work, not an automatic inherit.
- **The loader is one command, not two**: Extending the existing customer loader
  is preferred over adding a separate policy loader, because both record types
  come from the same row of the same file and a policy is meaningless without its
  customer. Whether the command keeps its current name is an implementation
  decision, not a requirement here.
- **No interface beyond the API**: This feature delivers policy data and its
  operations; screens are not in scope, consistent with the platform's API-first
  phasing.

## Dependencies

- **Phase 1 foundation (spec 001)**, complete: the user and role model, the
  role-checking mechanism, the append-only audit record and its write path, and
  the test and factory setup.
- **Phase 2a Customer (spec 002)**, complete: the customer record, its dual-manager
  archival behavior, the CSV loader this feature extends, and the refusal-recording
  mechanism this feature widens to cover policy routes.
- **Source dataset file**, present at a path supplied at run time; not committed.

## Out of Scope

- Computing, recomputing, or explaining renewal probability (Phase 5 Behavior).
- Claim records and their relationship to policies (the spec that follows this
  one).
- Premium calculation, quoting, rating, billing, payment, or collections.
- Underwriting decision workflows — approval, rejection, or referral of an
  application. A policy here is a record of an agreement, not a process that
  produces one.
- Policy renewal, lapse, cancellation, or reinstatement as state transitions.
- Coverage limits, deductibles, riders, endorsements, or beneficiaries.
- Any AI or language-model involvement in policy data.
- User-facing screens for policy management.
- Customer self-service access to their own policies.
- Bulk create, bulk update, or data export through the interface.
