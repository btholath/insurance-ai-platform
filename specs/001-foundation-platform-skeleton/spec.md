# Feature Specification: Phase 1 Foundation — Platform Skeleton & Role-Based Access

**Feature Branch**: `001-foundation-platform-skeleton`

**Created**: 2026-07-30

**Status**: Draft

**Input**: User description: "Phase 1 - Foundation. Build the local dev environment: Django 5.x project skeleton (apps/ structure: customers, policies, claims per README-Business-Requirements-Document.md's suggested layout), Docker Compose with PostgreSQL 16+ and Redis, a custom User model implementing the 9 roles from the BRD's Primary Users list (Fraud Analyst, Claims Adjuster, Customer Service, Underwriter, Compliance Officer, Risk Manager, Product Manager, Executive Leadership, System Administrator), and a health-check endpoint. Per the constitution: RBAC must be enforced server-side (Principle III), an AuditLog model must exist even if minimally used in this phase (Principle II), and pytest + Factory Boy must be set up from the start (Principle V). No AI/LLM/prompt features in this phase - that's Module 7/8, informed by the Phase 0 findings, but not part of this spec."

## Overview

This feature establishes the foundation on which every later module (Customer,
Policy, Claims, Risk, Fraud, Behavior, Prompt Library, LLM Services, CRM,
Dashboards, Reporting, Administration) will be built. It delivers no
business-facing insurance functionality of its own. Its value is that it makes
the next phases possible, and it makes the platform's two non-negotiable
guarantees — server-side role enforcement and audit logging — structurally
available from day one rather than retrofitted later.

Scope is deliberately narrow: an identity and access foundation, a running
local service environment, an operational health signal, an append-only audit
record, and a working automated-test capability.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Runs the Whole System Locally (Priority: P1)

A developer or System Administrator clones the repository onto a clean machine
and brings the entire platform up locally with a single documented command
sequence. The application, its database, and its cache all start and become
reachable, with no external cloud service required and no manual per-service
configuration beyond copying an example environment file.

**Why this priority**: Nothing else in this feature — or any later phase — can
be developed, demonstrated, or tested until the environment reliably starts.
This is the single hard dependency for all subsequent work.

**Independent Test**: On a machine with only the container runtime installed,
follow the documented setup steps from a fresh clone and confirm all services
reach a running state and the application responds to requests. Delivers value
on its own: a reproducible local environment.

**Acceptance Scenarios**:

1. **Given** a clean checkout with no prior local state, **When** the operator
   follows the documented startup sequence, **Then** the application, database,
   and cache services all reach a running state without manual intervention
   beyond copying the example environment file.
2. **Given** the platform is running, **When** the operator stops and restarts
   the services, **Then** previously stored data is still present.
3. **Given** the platform is running, **When** outbound access to external
   networks is blocked, **Then** all services continue to operate normally.
4. **Given** a first-time operator, **When** they follow only the written setup
   documentation, **Then** they reach a running system without needing to read
   source code or ask for undocumented steps.

---

### User Story 2 - Administrator Assigns Roles and the System Enforces Them (Priority: P1)

A System Administrator creates user accounts and assigns each one exactly one
of the nine organizational roles. When any user attempts an action, the system
decides server-side whether their role permits it, and refuses the action if it
does not — regardless of what the user's interface shows them or how the
request was constructed.

**Why this priority**: Role enforcement is constitutionally non-negotiable
(Principle III). If the identity model arrives later, every endpoint built in
the meantime becomes a security-review liability that must be revisited. It
must exist before any business data exists.

**Independent Test**: Create one account per role, then attempt a restricted
action as each. Confirm permitted roles succeed and all others are refused.
Delivers value on its own: a working, auditable access-control foundation.

**Acceptance Scenarios**:

1. **Given** a System Administrator, **When** they create a user account and
   assign it one of the nine roles, **Then** the account is created with that
   role recorded and the role is visible on the account thereafter.
2. **Given** a user holding a role that is not permitted to perform a
   restricted action, **When** they attempt that action through any means
   including a directly constructed request, **Then** the system refuses the
   action and the target data is unchanged.
3. **Given** a user who is not signed in, **When** they attempt any restricted
   action, **Then** the system refuses the action and does not disclose whether
   the target record exists.
4. **Given** a user holding a role permitted to perform an action, **When** they
   perform it, **Then** the action succeeds.
5. **Given** an attempt to assign a role outside the nine defined roles, **When**
   the account is saved, **Then** the system rejects the assignment.
6. **Given** an account whose role is changed by an administrator, **When** the
   affected user next attempts an action, **Then** the decision reflects their
   new role rather than their previous one.

---

### User Story 3 - Compliance Officer Sees an Unalterable Record of Sensitive Actions (Priority: P2)

A Compliance Officer needs assurance that when the platform later handles
customer, policy, claim, risk, fraud, and CRM data, every action against that
data leaves a permanent record of who did what and when. In this phase the
record-keeping capability itself is established and proven against the actions
that exist today — account and role administration — so later modules only have
to write to it rather than invent it.

**Why this priority**: Principle II requires audit logging by default rather
than retrofitted; retroactive logging cannot reconstruct history. It is P2
rather than P1 only because there is little sensitive activity to record until
Phase 2 introduces business data.

**Independent Test**: Perform an administrative action that changes a user
account, then confirm a corresponding audit record exists with actor, action,
target, timestamp, and before/after state. Attempt to alter or remove that
record and confirm the attempt fails. Delivers value on its own: a proven
append-only audit capability.

**Acceptance Scenarios**:

1. **Given** an administrator creates or modifies a user account, **When** the
   change is saved, **Then** an audit record is created capturing who performed
   it, what action occurred, which record was affected, when it happened, and
   the before and after state of the changed values.
2. **Given** an existing audit record, **When** any part of the platform
   attempts to modify or delete it, **Then** the attempt is refused and the
   record remains unchanged.
3. **Given** an action that is attempted and refused, **When** the outcome is
   recorded, **Then** the audit record distinguishes it from a successful
   action.
4. **Given** a Compliance Officer, **When** they request the audit history for a
   specific affected record, **Then** they receive its entries in chronological
   order.

---

### User Story 4 - Operator Confirms System Health at a Glance (Priority: P2)

An operator, an automated restart supervisor, or a future monitoring system
queries a single endpoint to learn whether the platform and its dependencies
are healthy, without signing in and without exposing internal details to an
unauthenticated caller.

**Why this priority**: Required for reliable container orchestration and for
the monitoring layer named in later phases, and it is the cheapest way to make
User Story 1 verifiable automatically. Not P1 because the environment can be
brought up and inspected manually without it.

**Independent Test**: Query the health endpoint while all services are up, then
again with the database stopped, and confirm the reported status differs
appropriately. Delivers value on its own: an automatable liveness signal.

**Acceptance Scenarios**:

1. **Given** all services are running, **When** the health endpoint is queried
   without credentials, **Then** it reports a healthy status and indicates that
   the database and cache dependencies are reachable.
2. **Given** the database is unreachable, **When** the health endpoint is
   queried, **Then** it reports an unhealthy status identifying the database as
   the failing dependency, as a distinct machine-detectable outcome rather than
   an unhandled error.
3. **Given** the cache is unreachable, **When** the health endpoint is queried,
   **Then** it reports an unhealthy status identifying the cache as the failing
   dependency.
4. **Given** an unauthenticated caller, **When** they query the health endpoint,
   **Then** the response reveals no configuration secrets, credentials,
   connection strings, internal host addresses, or software version details.

---

### User Story 5 - Developer Writes and Runs Automated Tests From Day One (Priority: P2)

A developer joining the project runs the full automated test suite with a
single command, and can construct realistic test data — including users in any
of the nine roles — without hand-writing setup boilerplate for each test.

**Why this priority**: Principle V makes test infrastructure mandatory from the
start. Establishing it now means Phase 2's business rules can be written
test-first as required, instead of the team retrofitting a test harness under
pressure.

**Independent Test**: Run the test command on a fresh checkout and confirm the
suite executes and reports results, including tests that build users in several
different roles from reusable test-data builders. Delivers value on its own: a
working quality gate.

**Acceptance Scenarios**:

1. **Given** a fresh checkout with dependencies installed, **When** the developer
   runs the documented test command, **Then** the suite runs to completion and
   reports pass/fail results.
2. **Given** a developer writing a new test, **When** they need a user in a
   specific role, **Then** they can create one through a reusable test-data
   builder in a single call without specifying unrelated fields.
3. **Given** the test suite runs, **When** it completes, **Then** a coverage
   measurement for the codebase is produced.
4. **Given** the test suite runs, **When** it interacts with stored data, **Then**
   it does so against isolated test data that leaves the operator's local
   working data unchanged.

---

### Edge Cases

- **Account left without a valid role**: The system MUST refuse restricted
  actions for that account rather than defaulting to permissive access.
- **Administrator vs. unrestricted superuser**: The System Administrator role
  MUST NOT be silently treated as an unrestricted bypass. Actions restricted to
  other roles are still evaluated on their own terms.
- **Audit write fails while the action succeeds**: The action MUST NOT be
  silently committed without its audit entry.
- **Actor account later removed**: The audit record MUST remain readable and
  still identify who acted.
- **Single dependency down**: The health endpoint MUST report unhealthy and
  identify which dependency, not return a blanket failure or hang.
- **Health queried during startup**: The endpoint MUST return a definite status
  within a bounded time rather than hanging.
- **Required configuration missing**: Startup MUST fail with a message naming
  the missing setting, not start in a partially configured state.
- **Role changed during an active session**: Subsequent actions MUST be
  evaluated against the current role, not the role held at sign-in.

## Requirements *(mandatory)*

### Functional Requirements

**Environment & Runtime**

- **FR-001**: The platform MUST start all required services — application,
  relational database, and cache — from a single declarative local
  orchestration definition.
- **FR-002**: The platform MUST run entirely on local infrastructure with no
  required call to an external cloud service, per Principle I.
- **FR-003**: Stored data MUST survive a stop and restart of the platform's
  services.
- **FR-004**: Configuration values that vary by environment, including all
  credentials, MUST be supplied externally rather than committed to the
  repository, and an example configuration file listing every required setting
  MUST be provided.
- **FR-005**: The platform MUST refuse to start, with a message naming the
  missing item, when a required configuration value is absent.
- **FR-006**: The codebase MUST be organised into separate modules for
  customers, policies, and claims, matching the layout the business
  requirements document prescribes, so later phases add functionality inside an
  established structure rather than reorganising it.
- **FR-007**: Setup, startup, and test-execution steps MUST be documented such
  that a new operator can reach a running, tested system by following them
  alone.

**Identity & Role-Based Access Control**

- **FR-008**: The system MUST support user accounts that can be authenticated.
- **FR-009**: Each user account MUST carry exactly one role drawn from the nine
  defined roles: Fraud Analyst, Claims Adjuster, Customer Service, Underwriter,
  Compliance Officer, Risk Manager, Product Manager, Executive Leadership, and
  System Administrator.
- **FR-010**: The system MUST reject any attempt to assign a role outside the
  nine defined roles.
- **FR-011**: The system MUST evaluate every access decision on the server, per
  Principle III. Hiding an option in the interface MUST NOT be the only barrier
  to performing a restricted action.
- **FR-012**: The system MUST refuse a restricted action requested by an
  unauthenticated caller, without disclosing whether the target record exists.
- **FR-013**: The system MUST refuse a restricted action requested by an
  authenticated user whose role does not permit it, leaving the target data
  unchanged.
- **FR-014**: The system MUST treat an account with no valid role as permitted
  to perform nothing restricted, rather than defaulting to permissive access.
- **FR-015**: The system MUST provide a single reusable mechanism for declaring
  which roles may perform a given action, so later modules enforce access
  consistently rather than each inventing its own check.
- **FR-016**: A role change MUST take effect for the affected user's subsequent
  actions without requiring a platform restart.
- **FR-017**: Only the System Administrator role MUST be able to create user
  accounts and assign or change roles.

**Audit Logging**

- **FR-018**: The system MUST maintain an audit record capable of capturing, for
  each recorded action: the acting user, the action performed, the affected
  record, the time it occurred, whether it succeeded or was refused, and the
  before and after state of changed values where applicable.
- **FR-019**: Audit records MUST be append-only. No part of the platform may
  modify or delete an existing audit record, per Principle II.
- **FR-020**: The system MUST write an audit record for user-account creation
  and for role assignment or change.
- **FR-021**: An audit record MUST remain readable and MUST still identify its
  originating actor after that user account is removed.
- **FR-022**: When an audit record cannot be written, the action it describes
  MUST NOT be silently committed as if it had been logged.
- **FR-023**: The audit record structure MUST be usable by later modules for
  Customer, Policy, Claim, Risk, Fraud, and CRM activity without redefining it.
- **FR-024**: Audit history for a given affected record MUST be retrievable in
  chronological order.

**Health Check**

- **FR-025**: The system MUST expose a health endpoint reachable without
  authentication.
- **FR-026**: The health endpoint MUST report whether the database and the cache
  are each reachable, identifying any failing dependency individually.
- **FR-027**: The health endpoint MUST return a definite healthy or unhealthy
  result within a bounded time even when a dependency is unresponsive, and MUST
  signal the unhealthy case in a way an automated supervisor can detect without
  parsing prose.
- **FR-028**: The health endpoint MUST NOT disclose credentials, connection
  details, internal addresses, configuration values, or software version
  information.

**Testing**

- **FR-029**: The project MUST provide an automated test suite runnable with a
  single documented command, per Principle V.
- **FR-030**: The project MUST provide reusable test-data builders that can
  produce a user in any of the nine roles in a single call.
- **FR-031**: The test suite MUST produce a coverage measurement.
- **FR-032**: Tests MUST run against isolated data that leaves the operator's
  local working data unchanged.
- **FR-033**: The test suite MUST include tests proving that a restricted action
  is refused for unauthenticated callers and for each role not permitted to
  perform it, and permitted for roles that are.
- **FR-034**: The test suite MUST include tests proving that audit records are
  written for account and role changes, and that attempts to modify or delete an
  existing audit record fail.

### Key Entities

- **User**: A person who signs in to the platform. Carries identifying and
  contact details, credentials, an active/inactive state, and exactly one Role.
  Referenced by audit records as the actor.
- **Role**: One of the nine fixed organizational roles from the business
  requirements document. Determines what actions its holder may perform.
  Constrained to the defined set; not extensible without a spec change.
- **AuditLog**: An append-only record of a single action taken against the
  platform. Holds the acting user, the action, the affected record's identity
  and type, the timestamp, the outcome (succeeded or refused), and the before
  and after state of changed values. Never modified or deleted once written;
  survives removal of the acting user account.
- **HealthStatus**: A transient, non-persisted summary of whether the platform
  and each of its dependencies are currently reachable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new operator, starting from a clean machine with only the
  container runtime installed and following only the written documentation,
  reaches a fully running platform in under 30 minutes with no undocumented
  steps.
- **SC-002**: All nine defined roles can be assigned to an account and are
  enforced server-side, verified by automated tests covering every role.
- **SC-003**: 100% of attempts to perform a restricted action without
  authentication, or with a role that does not permit it, are refused — with
  zero cases where the action succeeds or the target data changes.
- **SC-004**: 100% of user-account creations and role changes produce a
  corresponding audit record.
- **SC-005**: 100% of attempts to modify or delete an existing audit record
  fail, verified by automated tests.
- **SC-006**: The health endpoint returns a definite status within 5 seconds in
  all tested conditions, including when a dependency is unreachable.
- **SC-007**: The health endpoint correctly identifies the failing dependency in
  100% of tested single-dependency-failure scenarios.
- **SC-008**: The full automated test suite runs to completion with a single
  command and finishes in under 2 minutes on a typical development machine.
- **SC-009**: A developer can create a test user in any role with a single call
  to a reusable builder, requiring no additional field-by-field setup.
- **SC-010**: Stored data survives a full stop and restart of all services in
  100% of attempts.
- **SC-011**: The platform operates with zero required calls to external
  services, verified by running it with outbound external network access
  blocked.

## Out of Scope

The following are explicitly **not** part of this feature and belong to later
phases:

- Any AI, LLM, prompt-template, prompt-execution, or model-integration
  functionality (business requirements Modules 7 and 8, informed by the Phase 0
  spike but specified separately).
- Business data models and record management for Customer, Policy, and Claim
  records — those modules are created here as structural placeholders only
  (Phase 2).
- Risk scoring, fraud detection, behavior analysis, and renewal probability
  (Phases 3 and 5).
- Dashboards, charts, reporting, and analytics (Phase 6).
- Background job processing and scheduled work. The cache service is stood up
  here as required infrastructure, but no queued or asynchronous work is
  defined in this phase.
- Vector search and embedding storage.
- A full administration interface for users, permissions, feature flags, and
  settings (Module 12) beyond the account and role management required here.
- Production deployment, external-facing hosting, CI/CD pipelines, and
  monitoring dashboards (Phase 8).
- Fine-grained per-record or per-field permissions beyond role-level access
  decisions.
- Self-service registration, password reset, multi-factor authentication, and
  session management features beyond basic authenticated sign-in.

## Assumptions

- **Single role per user**: Each account holds exactly one of the nine roles.
  The business requirements document lists the nine as distinct primary user
  types rather than combinable attributes, so multi-role accounts are out of
  scope until a later spec establishes a need.
- **Roles are a fixed set**: The nine roles are a closed set defined by the
  business requirements document. Adding a tenth role is a spec change, not a
  runtime configuration action.
- **Permissions are per action, at the role level**: Access decisions in this
  phase depend on the acting user's role and the action requested, not on which
  specific record is being touched. Record-scoped rules (for example, "an
  adjuster may only view claims assigned to them") are deferred.
- **Demonstration surface for access control**: Because no business data exists
  yet, role enforcement is proven against the account and role administration
  actions this phase introduces, plus at least one deliberately role-restricted
  placeholder action in each of the customers, policies, and claims modules, so
  the enforcement mechanism is exercised where later modules will use it.
- **Audit coverage in this phase**: Audit logging is exercised against the only
  sensitive activity that exists — account and role administration. Its
  structure is designed for the Customer, Policy, Claim, Risk, Fraud, and CRM
  activity of later phases, per Principle II.
- **Health endpoint is public**: Kept unauthenticated so container
  orchestration and future monitoring can reach it without credentials, and
  therefore constrained to disclose nothing sensitive.
- **Target environment**: WSL Ubuntu on Windows 11 with a container runtime
  available, consistent with the constitution's target environment.
- **Performance targets deferred**: This phase carries no production data; the
  response-time and concurrency targets in the business requirements document
  apply from Phase 2 onward and are not measured here.
- **No seed business data**: Any sample data created in this phase exists for
  testing and manual verification of accounts and roles only.
- **Stack is pre-decided, not chosen here**: The technologies named in the
  feature description are binding constraints from the constitution's
  Technology Stack Constraints section, not decisions this specification makes.
  The requirements above are written so they can be verified without reference
  to those specific technologies.

## Dependencies

- The constitution (`.specify/memory/constitution.md`) v1.0.1 — Principles I,
  II, III, and V directly constrain this feature, and its Technology Stack
  Constraints section fixes the platform stack.
- The business requirements document
  (`README-Business-Requirements-Document.md`) — defines the nine primary user
  roles, the module layout, and the phase roadmap.
- A container runtime available on the operator's machine. This is the only
  external prerequisite; it is not installed or managed by this feature.
- No dependency on the Phase 0 Streamlit spike. Per Principle VI, that code is
  disposable and is not a starting point for anything specified here.
