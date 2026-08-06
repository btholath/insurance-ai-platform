# Feature Specification: Phase 2a — Customer Management

**Feature Branch**: `002-customer-management`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Phase 2a - Customer Management. Real Customer model and CRUD API (apps/customers/), replacing Phase 1's placeholder endpoint. Fields per the Phase 0 CSV dataset (verified: 3,000 rows, 20 columns, zero nulls, Client_ID unique and formatted CL-00001 style, 3 duplicate emails exist in the source data): name, email (NOT unique - the source data has legitimate duplicates), phone, age, gender, location, lead_source, plus nullable risk_score/fraud_risk_flag/cross_sell_score columns (storage only - scoring logic is out of scope, deferred to Phase 3/5). Also store the source client_id (e.g. CL-00001) as a unique external reference field, distinct from the Django primary key, so a seed import is idempotent on re-run. RBAC per the existing HasRole mechanism from apps/core/permissions.py, audit logging per the existing AuditLog on create/update/delete, tests first per constitution Principle V. A management command imports the CSV for seed data (path configurable, file itself gitignored, not committed). This is the first of three planned specs (Customer, then Policy, then Claims) - Policy will depend on Customer, Claims will depend on Policy, so keep this spec's Customer model genuinely complete and stable."

## Overview

This feature delivers the platform's first real business entity: the Customer.
Phase 1 established identity, role enforcement, and audit recording but stored
no insurance data — the customer endpoint returned a fixed placeholder
response. This feature replaces that placeholder with a persistent customer
record and the full set of operations to create, read, update, delete, list,
and search it.

It also delivers a repeatable way to load the existing 3,000-record source
dataset into the platform, so that later work — and any demonstration of this
platform — starts from realistic data volume rather than a handful of
hand-made records.

Two boundaries are deliberate. First, the customer record carries fields for
risk score, fraud risk level, and cross-sell score, but this feature only
**stores and displays** those values as supplied by the source data; nothing
here computes, recomputes, or interprets them. The logic that produces those
values is Phase 3 (Risk) and Phase 5 (Fraud/Behavior) work. Second, this is
the first of three sequential specs — Customer, then Policy, then Claims.
Policy records will reference customers and Claims will reference policies, so
the customer record defined here is treated as a stable foundation rather than
a first draft: the fields, the identity rules, and the deletion behavior are
settled now precisely so the two dependent features do not have to revisit
them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Customer Service Representative Looks Up a Customer (Priority: P1)

A Customer Service representative receives an inbound contact from a
policyholder. They search the platform by the customer's name, email, or
customer reference, find the matching record, and open it to see that
person's contact details, demographics, and how they were acquired — enough
to confirm they are speaking to the right person and to answer questions
about the account.

**Why this priority**: Retrieval is the single most frequent interaction with
customer data and the reason the record exists at all. It is also the
capability that the rest of the platform depends on: Policy and Claims work
is meaningless without a customer to attach to. A working read path over
imported data is a demonstrable product on its own, even before any customer
can be created through the interface.

**Independent Test**: Load the source dataset, then search for a known
customer by name fragment, by email, and by customer reference, and open the
returned record. Delivers value on its own: a searchable customer directory
over real data.

**Acceptance Scenarios**:

1. **Given** customer records exist, **When** a Customer Service
   representative requests the customer list, **Then** they receive customers
   in a stable, repeatable order, delivered in pages rather than all at once.
2. **Given** customer records exist, **When** the representative searches by a
   partial name, **Then** all customers whose name contains that text are
   returned, regardless of letter casing.
3. **Given** customer records exist, **When** the representative searches by a
   full email address that two different customers share, **Then** both
   matching customers are returned.
4. **Given** a known customer reference, **When** the representative requests
   that single customer, **Then** the full record is returned including
   contact details, demographics, acquisition source, and any stored risk,
   fraud-risk, and cross-sell values.
5. **Given** a customer reference that does not exist, **When** the
   representative requests it, **Then** the system reports that no such
   customer was found and reveals nothing further.
6. **Given** customers with differing acquisition sources, **When** the
   representative filters the list by one acquisition source, **Then** only
   customers with that source are returned.

---

### User Story 2 - Administrator Seeds the Platform From the Source Dataset (Priority: P1)

An operator loads the organization's existing 3,000-record customer dataset
into the platform in one step. Running the load a second time — after a crash,
a partial run, or a refreshed export — updates the records that already exist
and adds only the genuinely new ones, rather than creating 3,000 duplicates.
The source file itself is never committed to the repository, and its location
is supplied at run time rather than hard-coded.

**Why this priority**: Without data, none of the other stories can be
demonstrated at realistic volume, and the search, pagination, and filtering
behavior in User Story 1 cannot be meaningfully verified against 3,000
records. The idempotency requirement is P1 rather than a refinement because a
non-idempotent loader is actively dangerous: the natural operator reaction to
a failed run is to run it again.

**Independent Test**: Run the load against the source file, confirm the
expected record count, then run it a second time unchanged and confirm the
count is identical and no duplicate customer references exist. Delivers value
on its own: a populated, reproducible platform dataset.

**Acceptance Scenarios**:

1. **Given** an empty customer set and a valid source file, **When** the
   operator runs the load pointing at that file, **Then** one customer is
   created per source row and the operator is told how many were created.
2. **Given** the load has already been run once, **When** it is run again on
   the same unchanged file, **Then** the total number of customers is
   unchanged, no duplicate customer references exist, and the operator is told
   that records were matched and updated rather than created.
3. **Given** the load has already been run and a source row's details have
   since changed, **When** the load is run again, **Then** the existing
   customer with that reference reflects the new details rather than a second
   record being created.
4. **Given** a source file path that does not exist or cannot be read, **When**
   the operator runs the load, **Then** the system reports the problem clearly
   and creates no customers.
5. **Given** a source file containing a row that fails validation, **When** the
   operator runs the load, **Then** the operator is told which row failed and
   why, and no partially-valid subset is left behind from that run.
6. **Given** a source file with columns beyond those the customer record uses,
   **When** the load runs, **Then** the extra columns are ignored without
   error, so that policy and claim columns in the same file cause no failure
   here.

---

### User Story 3 - Customer Service Representative Creates and Corrects Customer Records (Priority: P2)

A Customer Service representative onboards a new customer by entering their
details, and later corrects a record when a customer reports a changed phone
number, a new address, or a misspelled name. The system rejects entries that
are not plausible — an impossible age, a malformed email, a missing name —
before they become part of the record.

**Why this priority**: Create and update are essential to a complete customer
module, but the platform is usable and demonstrable without them once the
dataset is loaded and searchable. They rank below the read and load paths that
everything else depends on.

**Independent Test**: Create a customer with valid details and confirm it is
retrievable; attempt several invalid entries and confirm each is refused with
a clear reason. Delivers value on its own: maintainable customer data.

**Acceptance Scenarios**:

1. **Given** a Customer Service representative, **When** they create a customer
   with valid details, **Then** the customer is stored, assigned a unique
   customer reference, and immediately retrievable.
2. **Given** an existing customer, **When** the representative changes only the
   phone number, **Then** that field is updated and every other field retains
   its previous value.
3. **Given** an entry with a malformed email address, **When** it is submitted,
   **Then** the system refuses it, identifies the email field as the problem,
   and stores nothing.
4. **Given** an entry with an age outside the plausible range for a
   policyholder, **When** it is submitted, **Then** the system refuses it and
   identifies the age field as the problem.
5. **Given** an entry with no name, **When** it is submitted, **Then** the
   system refuses it and identifies the name field as the problem.
6. **Given** an existing customer, **When** a representative submits a customer
   reference that already belongs to a different customer, **Then** the system
   refuses the change and reports the conflict.
7. **Given** two customers who genuinely share an email address, **When** both
   are created, **Then** both are stored successfully, because a shared email
   address is legitimate in this dataset.

---

### User Story 4 - Compliance Officer Traces Who Changed a Customer Record (Priority: P2)

A Compliance Officer investigating a data-handling question examines the
history of a specific customer record and sees every creation, modification,
and removal — who performed it, when, and what the values were before and
after. The record of those actions cannot be altered or erased, including by
the person who performed them.

**Why this priority**: Auditability is constitutionally non-negotiable
(Principle II) and cannot be reconstructed after the fact, so it must ship
with the write operations it describes rather than after them. It is P2
because it has no meaning until the write operations of User Story 3 exist.

**Independent Test**: Create, update, and delete a customer, then retrieve
that customer's history and confirm three corresponding entries with actor,
timestamp, and before/after values. Delivers value on its own: a provable
chain of custody over customer data.

**Acceptance Scenarios**:

1. **Given** a representative creates a customer, **When** the Compliance
   Officer examines that customer's history, **Then** an entry records who
   created it, when, and the values it was created with.
2. **Given** a representative changes a customer's details, **When** the
   Compliance Officer examines the history, **Then** an entry records the
   changed fields with both their previous and their new values.
3. **Given** a customer is removed, **When** the Compliance Officer examines
   the history, **Then** an entry records who removed it, when, and the values
   it held at the time of removal.
4. **Given** an attempt to create or change a customer that the system refuses
   for lack of permission, **When** the Compliance Officer examines the
   history, **Then** the refused attempt is recorded as a refusal, with the
   customer record itself unchanged.
5. **Given** a change to a customer fails partway through, **When** the outcome
   is examined, **Then** either both the customer change and its history entry
   are present, or neither is — never one without the other.

---

### User Story 5 - Roles Are Enforced on Every Customer Operation (Priority: P1)

Each role in the organization can do only what its job requires with customer
data. Roles whose work depends on customer context can look customers up.
Only the roles responsible for customer records may create, change, or remove
them. Every other role is refused, and the refusal happens on the server
regardless of how the request was constructed.

**Why this priority**: Principle III is non-negotiable and applies at the
moment business data first exists. This is the first feature where a
permission failure would expose real personal information rather than a
placeholder response, so enforcement cannot lag behind the data by even one
release.

**Independent Test**: Attempt every customer operation once as each of the
nine roles and once with no identity, and confirm the outcome matches the
permission matrix in FR-024. Delivers value on its own: verified access
control over personal data.

**Acceptance Scenarios**:

1. **Given** a user holding a role permitted to view customers, **When** they
   list or open a customer, **Then** the request succeeds.
2. **Given** a user holding a role not permitted to view customers, **When**
   they request the customer list, **Then** the request is refused.
3. **Given** a user holding a role permitted to view but not to modify
   customers, **When** they attempt to create, change, or remove a customer,
   **Then** the request is refused and the data is unchanged.
4. **Given** a user with no established identity, **When** they request a
   specific existing customer, **Then** the request is refused without
   revealing whether that customer exists.
5. **Given** a user whose role is changed by an administrator, **When** they
   next attempt a customer operation, **Then** the decision reflects their new
   role rather than their previous one.

---

### Edge Cases

- **Shared email addresses**: Three email addresses in the source dataset are
  each held by two different customers. Email must never be treated as an
  identifier or a uniqueness constraint; searching by a shared email returns
  every customer holding it.
- **Customer reference collisions**: Two customers may never hold the same
  customer reference. An attempt to create or change one into a collision is
  refused and reported as a conflict, not silently merged.
- **Removal of a customer with dependents**: Policy and Claim records do not
  yet exist, but they will reference customers. Removing a customer must not
  become a mechanism for silently orphaning or destroying future policy and
  claim history, so the removal behavior defined in FR-020 is chosen now, in
  this feature, rather than being revisited when Policy arrives.
- **Missing scoring values**: Risk score, fraud risk level, and cross-sell
  score are absent for any customer created through the interface rather than
  loaded from the dataset. An absent value must be distinguishable from a
  value of zero, and must not be displayed or treated as a computed score.
- **Interrupted load**: A load that stops partway — killed process, unreadable
  file mid-stream, a row that fails validation — must leave the customer set
  in a state the operator can reason about, and re-running the load must
  reconcile rather than duplicate.
- **Boundary ages**: The dataset spans ages 18 through 75. Values at the
  accepted boundaries are stored; values outside the accepted range are
  refused.
- **Unrecognized category values**: A source row or submission carrying a
  gender, acquisition source, or fraud risk level outside the recognized sets
  is refused with the offending field named, rather than being stored as an
  unrecognized value that later filters would silently miss.
- **Search with no matches**: A search matching no customers returns an empty
  result set, not an error.
- **Very large result sets**: A list request over the full 3,000-record dataset
  returns a bounded page rather than every record at once.

## Requirements *(mandatory)*

### Functional Requirements

#### Customer record and identity

- **FR-001**: The system MUST store a customer record carrying the customer's
  name, email address, phone number, age, gender, location, and acquisition
  source.
- **FR-002**: The system MUST store, for each customer, a customer reference
  that originates from the source dataset (formatted as in `CL-00001`), held
  separately from the platform's own internal record identifier.
- **FR-003**: The system MUST guarantee that no two customers share the same
  customer reference, and MUST refuse any create or change that would violate
  this.
- **FR-004**: The system MUST allow two or more customers to share an email
  address, because the source dataset contains legitimate duplicates.
- **FR-005**: The system MUST assign a customer reference to every customer
  created through the interface without one being supplied, in the same format
  as the source dataset, without colliding with any existing reference.
- **FR-006**: The system MUST store, for each customer, a risk score, a fraud
  risk level, and a cross-sell score, each of which MAY be absent, and MUST
  distinguish an absent value from a zero or empty one.
- **FR-007**: The system MUST NOT compute, derive, recompute, or interpret the
  risk score, fraud risk level, or cross-sell score in this feature; it stores
  and returns only what was supplied.
- **FR-008**: The system MUST record when each customer record was first
  created and when it was last changed.

#### Validation

- **FR-009**: The system MUST refuse a customer whose name is absent or empty.
- **FR-010**: The system MUST refuse a customer whose email address is not a
  well-formed email address.
- **FR-011**: The system MUST refuse a customer whose age falls outside 18 to
  120 inclusive.
- **FR-012**: The system MUST refuse a customer whose gender, acquisition
  source, or fraud risk level is not one of the recognized values for that
  field, and MUST name the offending field in the refusal.
- **FR-013**: The system MUST refuse a customer whose risk score or cross-sell
  score falls outside 0 to 1 inclusive.
- **FR-014**: Every refusal for invalid input MUST identify which field was
  invalid and MUST leave stored data unchanged.

#### Operations

- **FR-015**: Users MUST be able to create a customer, retrieve a single
  customer, list customers, change a customer, and remove a customer, subject
  to the permissions in FR-024.
- **FR-016**: The system MUST support changing a subset of a customer's fields
  without requiring or altering the remainder.
- **FR-017**: The system MUST return customer lists in bounded pages with a
  stable, repeatable ordering, and MUST report the total number of matching
  customers.
- **FR-018**: Users MUST be able to search customers by partial name, by email
  address, and by customer reference, with matching insensitive to letter
  casing.
- **FR-019**: Users MUST be able to filter the customer list by acquisition
  source, by gender, and by fraud risk level.
- **FR-020**: Removing a customer MUST be a reversible archival — the record
  ceases to appear in lists, searches, and single-record retrieval, but is
  retained so that policies and claims added in later features can never be
  orphaned by a removal performed here.
- **FR-021**: A removed customer's customer reference MUST remain reserved,
  so that re-loading the source dataset reconciles with the archived record
  rather than creating a duplicate.
- **FR-022**: Requesting a customer that does not exist, or that the requester
  is not permitted to see, MUST NOT disclose whether that customer exists.

#### Access control

- **FR-023**: The system MUST enforce every permission decision on the server
  for every customer operation, using the platform's existing role-checking
  mechanism, with no reliance on the interface hiding an action.
- **FR-024**: The system MUST apply the following permissions:

  | Role | View customers | Create / change / remove |
  |------|----------------|--------------------------|
  | Customer Service | Yes | Yes |
  | Underwriter | Yes | No |
  | System Administrator | Yes | Yes |
  | Claims Adjuster | Yes | No |
  | Fraud Analyst | Yes | No |
  | Risk Manager | Yes | No |
  | Compliance Officer | Yes | No |
  | Product Manager | No | No |
  | Executive Leadership | No | No |
  | No established identity | No | No |

- **FR-025**: A permission decision MUST reflect the user's role as it stands
  at the moment of the request, not as it stood at any earlier point.
- **FR-026**: Holding the System Administrator role MUST be the basis of that
  role's access; no separate superuser status may bypass the role check.

#### Audit

- **FR-027**: The system MUST record an audit entry for every successful
  creation, change, and removal of a customer, capturing who acted, what
  action was taken, which customer it targeted, and when.
- **FR-028**: An audit entry for a change MUST capture the previous and new
  values of the fields that changed, and MUST NOT record fields that did not
  change.
- **FR-029**: An audit entry for a removal MUST capture the customer's values
  as at the moment of removal.
- **FR-030**: The system MUST record an audit entry when a customer operation
  is refused for lack of permission, marked as a refusal.
- **FR-031**: A customer change and its audit entry MUST both succeed or both
  fail; the system MUST NOT leave a change recorded without its audit entry or
  an audit entry without its change.
- **FR-032**: Audit entries for customer operations MUST be subject to the
  platform's existing append-only guarantee — no operation in this feature may
  alter or remove one.
- **FR-033**: Retrievals of customer data (list, search, single record) are
  NOT required to produce audit entries in this feature.

#### Dataset load

- **FR-034**: An operator MUST be able to load customers from the source
  dataset file in a single command, with the file's location supplied at run
  time and no default that assumes a committed file.
- **FR-035**: The load MUST be idempotent: running it repeatedly on unchanged
  input MUST leave exactly one customer per source row, matched on customer
  reference.
- **FR-036**: The load MUST update the stored details of a customer whose
  source row has changed since the previous run.
- **FR-037**: The load MUST ignore source columns that the customer record does
  not use, so that the same file can later be used to load policies and claims.
- **FR-038**: The load MUST apply the same validation rules as FR-009 through
  FR-013, and MUST report the identifying position and reason for any row it
  refuses.
- **FR-039**: The load MUST report, on completion, how many customers were
  created, how many were updated, and how many rows were refused.
- **FR-040**: The load MUST fail clearly, creating no customers, when the
  supplied file is missing, unreadable, or lacks the columns the customer
  record requires.
- **FR-041**: The source dataset file MUST NOT be committed to the repository,
  and the repository MUST be configured to keep it out.
- **FR-042**: The load MUST be usable without an interactive user session, and
  its audit entries MUST identify it as a system load rather than attributing
  the records to a person who did not enter them.

#### Replacing the placeholder

- **FR-043**: The placeholder customer endpoint delivered in Phase 1 MUST be
  removed, along with the tests that assert its placeholder response, so that
  no route serves a fixed non-record response after this feature.

#### Forward stability

- **FR-044**: The customer record MUST expose a stable identifier that later
  policy records can reference without depending on the source dataset's
  customer reference remaining present or unchanged.

### Key Entities

- **Customer**: A person insured by or marketed to the organization. Carries
  identity and contact attributes (name, email, phone), demographics (age,
  gender, location), an acquisition source describing how they came to the
  organization, and three stored analytical values (risk score, fraud risk
  level, cross-sell score) that later features will produce and this feature
  only holds. Identified internally by the platform's own record identifier
  and externally by a customer reference carried over from the source dataset.
  Will be referenced by Policy records in the next feature.

- **Audit Entry** *(existing, from Phase 1)*: The append-only record of who did
  what to which record and when, including before and after values. This
  feature adds customer creations, changes, removals, and refusals to it; it
  does not change how audit entries work.

- **User and Role** *(existing, from Phase 1)*: The acting person and their
  single organizational role, which determines what customer operations they
  may perform. Unchanged by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator loads the complete 3,000-record source dataset in a
  single command, and the platform afterwards holds exactly 3,000 customers.
- **SC-002**: Re-running the load on the unchanged file leaves the customer
  count at exactly 3,000, with zero duplicate customer references.
- **SC-003**: A representative retrieves any single customer by reference in
  under 1 second with the full 3,000-record dataset loaded.
- **SC-004**: A name, email, or reference search over the full 3,000-record
  dataset returns its first page of results in under 2 seconds.
- **SC-005**: All 9 roles and the unidentified case are exercised against every
  customer operation, and 100% of the resulting outcomes match the permission
  matrix in FR-024.
- **SC-006**: 100% of successful customer creations, changes, and removals
  produce a corresponding audit entry; a sampled change entry shows the correct
  before and after values for exactly the fields that changed.
- **SC-007**: Every validation rule in FR-009 through FR-013 is demonstrated to
  refuse at least one invalid value and accept at least one valid boundary
  value.
- **SC-008**: The three known shared email addresses in the source dataset load
  successfully, producing 6 customers across those 3 addresses, and a search by
  one of them returns both holders.
- **SC-009**: Automated tests covering the customer record's validation,
  identity, permission, and audit behavior are written before the
  corresponding implementation, and measured coverage of the customer module
  is at least 95%, consistent with the level established in Phase 1.
- **SC-010**: No route in the platform returns the Phase 1 placeholder customer
  response after this feature is complete.
- **SC-011**: A removed customer is absent from every list, search, and
  single-record retrieval, while its customer reference still reconciles on a
  subsequent load rather than producing a second record.

## Assumptions

- **Source dataset shape is settled**: The dataset at hand has 3,000 rows and
  20 columns with no blank cells, unique `Client_ID` values in `CL-00001`
  format, and exactly 3 email addresses shared by two customers each. This was
  verified directly against the file rather than assumed. Ages span 18–75;
  risk and cross-sell scores span 0.0–1.0 with two decimal places.
- **Fraud risk is a level, not a boolean**: The source column named
  `Fraud_Risk_Flag` holds one of `Low`, `Medium`, or `High` — three levels,
  not a true/false flag. This feature stores it as a three-value category
  despite the "flag" name, and treats renaming it as a Phase 5 concern.
- **Recognized category values** come from the source data: gender is one of
  `Male`, `Female`, `Other`; acquisition source is one of `Agent`, `Referral`,
  `Social Media`, `Web`; fraud risk level is one of `Low`, `Medium`, `High`.
- **Age range**: The record accepts 18–120 rather than the dataset's observed
  18–75, so that a future real policyholder outside the sample's range is not
  refused by an artifact of this particular export.
- **Phone numbers are stored as supplied**: The source data uses inconsistent
  formats (`588-240-1527`, `405.085.5427`, `(529)223-6740`,
  `076.947.4706x46406`, `3799757647`). This feature preserves them as text
  rather than normalizing, since normalization would lose the extension
  syntax and is not needed by any requirement here.
- **Unused source columns are out of scope**: Policy type, policy dates,
  premium, claim status, claim amount, last interaction, renewal probability,
  and client feedback all exist in the same file and are deliberately not part
  of the customer record. They belong to the Policy and Claims features that
  follow, and to Phase 5 behavior scoring.
- **Existing mechanisms are reused, not rebuilt**: Role enforcement uses the
  platform's existing role-checking mechanism from Phase 1, and audit entries
  use the existing append-only audit record and its established write path.
  This feature adds neither a new permission mechanism nor a new audit
  mechanism.
- **Authentication is unchanged**: Users are identified by the session-based
  mechanism established in Phase 1; this feature introduces no new sign-in
  path.
- **Roles that may view customers** are set to the seven whose work involves
  customer context, while Product Manager and Executive Leadership are
  excluded because their needs are aggregate reporting rather than individual
  personal data — a distinction the Dashboards and Reporting modules will
  serve. Write access stays with Customer Service and System Administrator
  only.
- **The source file is currently untracked but not ignored**: The file sits at
  `data/Insurance_Dataset.csv` and is not committed, but nothing yet prevents
  committing it. FR-041 closes that gap.
- **No interface beyond the API**: This feature delivers the customer data and
  its operations; screens are not in scope, consistent with the platform's
  API-first phasing.
- **No bulk operations through the interface**: Bulk create, bulk update, and
  export are not required by any story here; the dataset load covers the one
  bulk need that exists.

## Dependencies

- **Phase 1 foundation (spec 001)**, complete: the user and role model, the
  role-checking mechanism, the append-only audit record and its write path,
  the test and factory setup, and the running local environment.
- **Source dataset file**, present at a path supplied at run time; not
  committed to the repository.

## Out of Scope

- Computing, recomputing, or explaining risk scores, fraud risk levels, or
  cross-sell scores (Phase 3 Risk, Phase 5 Fraud and Behavior).
- Policy and Claim records and their relationships to customers (the two specs
  that follow this one).
- Any AI or language-model involvement in customer data (Modules 7 and 8).
- User-facing screens for customer management.
- Customer self-service access to their own record.
- Merging or de-duplicating customers who share an email address.
- Bulk create, bulk update, or data export through the interface.
- Normalizing phone numbers or addresses into structured components.
