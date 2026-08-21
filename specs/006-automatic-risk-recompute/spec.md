# Feature Specification: Automatic Risk Recompute

**Feature Branch**: `006-automatic-risk-recompute`

**Created**: 2026-08-20

**Status**: Draft

**Input**: User description: "Phase 3b - Automatic Risk Recompute. Introduce Celery for the first time in this project - Redis has been provisioned but unused since Phase 1's Foundational plan explicitly deferred it. A Celery task calls the existing engine.persist() (same function 3a's on-demand path already uses, so this is additive, not a rewrite) whenever a Customer, Policy, or Claim record changes in a way that could affect that customer's risk assessment - trigger broadly (any save on any of the three models, matching 3a's existing staleness philosophy of over-reporting rather than fine-grained field tracking), not narrowly. Only customers who already have a RiskAssessment get automatically recomputed - this does not auto-score customers who have never been scored; initial scoring remains the computerisk batch command's job. Failed tasks retry with exponential backoff; alert only once retries are exhausted (no alert channel exists yet - define what "alert" means concretely for a local-first, no-cloud-dependency project, likely a structured log entry or an AuditLog entry, not an external service). The on-demand recompute endpoint from 3a remains available unchanged - automatic recompute is additive, not a replacement. Explicitly document as an accepted, known tradeoff: loaddataset touches ~3,000 customers/policies per run and will enqueue a proportional number of Celery tasks every time it runs - correctness holds because persist() is already idempotent, but this is a real, acknowledged inefficiency, not an oversight, and task-coalescing is named as a legitimate future optimization outside this spec's scope. RBAC and audit logging reuse existing mechanisms unchanged. Tests first per constitution Principle V, including tests proving the retry/backoff behavior and the loaddataset-triggers-redundant-but-correct-tasks behavior explicitly, not just the happy path."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Risk Manager Trusts an Assessment Without Manually Recomputing (Priority: P1)

A Risk Manager updates a customer's policy (e.g., a premium change) or a claim
gets filed against that customer. Later, without anyone triggering a manual
recompute, the Risk Manager opens that customer's risk assessment and finds
it already reflects the new data — current score, current tier, current
factors, computed automatically shortly after the underlying data changed.

**Why this priority**: This is the entire point of Phase 3b. Phase 3a made a
stale assessment *visible* (`is_stale: true`) but left closing that gap to a
human remembering to click recompute. Automatic recompute is what makes a
displayed score trustworthy without that manual step — it is the feature's
sole reason to exist.

**Independent Test**: Compute an assessment for a customer, change a live
policy's premium, wait for the automatic recompute to run, and confirm the
stored assessment's score, tier, and `computed_at` reflect the new data and
`is_stale` is now `false` — with no API call or management command run in
between.

**Acceptance Scenarios**:

1. **Given** a customer with an existing risk assessment, **When** one of
   their live policies is updated, **Then** within a bounded time the stored
   assessment is recomputed automatically and its `computed_at` reflects the
   new computation.
2. **Given** a customer with an existing risk assessment, **When** a new
   claim is filed against one of their live policies, **Then** the
   assessment is recomputed automatically to reflect it.
3. **Given** a customer with an existing risk assessment, **When** the
   customer's own record is updated (e.g., a change to `age`), **Then** the
   assessment is recomputed automatically.
4. **Given** a customer with an existing risk assessment, **When** an
   unrelated field with no bearing on any scoring factor is changed (e.g.
   `phone`), **Then** the assessment is still recomputed automatically —
   over-reporting/over-triggering is the accepted, deliberate behavior
   (matching Phase 3a's staleness philosophy), not a bug to later "optimize
   away" inside this feature.

---

### User Story 2 - The Platform Recovers From a Transient Recompute Failure (Priority: P1)

A recompute attempt fails because of a transient condition (e.g., a database
contention error). The platform retries the recompute automatically, spacing
retries further apart each time, and eventually succeeds without anyone
having to notice the first failure or intervene.

**Why this priority**: Automatic background work that silently fails and
never retries would recreate exactly the trust gap this feature exists to
close — a displayed score that looks current but silently stopped being
maintained. Retry-with-backoff is not a resilience nicety here; it is what
makes "automatic" mean something.

**Independent Test**: Force a single recompute attempt to fail, then confirm
the platform retries it after a delay, with each subsequent retry (if also
forced to fail) waiting longer than the last, and the assessment ends up
correctly recomputed once a retry succeeds.

**Acceptance Scenarios**:

1. **Given** a recompute attempt that fails on its first try, **When** the
   platform retries it, **Then** the retry happens after a delay rather than
   immediately, and a second failure's next retry waits longer still.
2. **Given** a recompute attempt that fails and then succeeds on retry,
   **When** the retry succeeds, **Then** the assessment is correctly
   recomputed and no trace of the earlier failed attempt is left in a
   position to confuse a later reader about what the current score is.

---

### User Story 3 - An Operator Learns a Recompute Permanently Failed (Priority: P2)

A recompute attempt keeps failing across every retry attempt and the
platform gives up. An operator (or a future monitoring process) can discover
that this happened — which customer, when, and why — without needing an
external alerting service that doesn't exist in this local-first
environment.

**Why this priority**: Retry-with-backoff (User Story 2) handles the common
transient case; this story handles the case where retries are exhausted and
a human genuinely needs to know, so a customer's assessment doesn't silently
drift stale forever with no signal anywhere that it happened.

**Independent Test**: Force every retry attempt for one recompute to fail,
let retries exhaust, and confirm a durable, discoverable record exists
identifying the customer, the failure, and that retries were exhausted —
findable by querying the platform's existing audit trail or logs, not by
receiving an external notification.

**Acceptance Scenarios**:

1. **Given** a recompute task that fails on every retry attempt, **When**
   the final retry is exhausted, **Then** a durable record is created
   identifying the affected customer and that automatic recompute has given
   up, without raising an unhandled error that could crash the worker
   process.
2. **Given** an exhausted-retry record has been created for a customer,
   **When** that customer's data changes again later, **Then** a fresh
   automatic recompute attempt is made — an earlier permanent failure does
   not permanently disable future automatic recompute for that customer.

---

### User Story 4 - Loading the Source Dataset Never Corrupts a Score (Priority: P2)

An operator re-runs the dataset loader against the full ~3,000-customer
source file, as already happens periodically per Phase 2's design. Every
customer touched by that load who already has a risk assessment gets
enqueued for automatic recompute — once per record the loader writes, even
though most of those writes leave the customer's scoring-relevant data
unchanged. The system handles this correctly: no duplicate assessments, no
score corruption, no crash from the volume — even though it is understood
and accepted that this generates a large number of same-answer, wasted
recompute attempts every time the loader runs.

**Why this priority**: This is the specific, named tradeoff the feature
accepts rather than solves. It is priority P2 rather than P1 because
correctness (not efficiency) is what must be proven — the inefficiency
itself is explicitly out of scope to fix in this phase — but proving
correctness under this real, everyday load pattern is still load-bearing:
Phase 2's loader is already a routine operation, and this feature must not
make routine operation break the risk book.

**Independent Test**: Run the dataset loader against a seeded population
where every customer already has a risk assessment, and confirm the
resulting number of enqueued recompute attempts is proportional to the
number of records the loader wrote, every assessment afterward is exactly
as correct as if each customer had been recomputed exactly once, and no
duplicate assessment rows exist.

**Acceptance Scenarios**:

1. **Given** a customer with an existing assessment and unchanged
   scoring-relevant data, **When** the dataset loader reconciles that
   customer's record on a re-run, **Then** a recompute is still enqueued
   (broad, save-triggered detection, not diffed against prior values) and
   its result is identical to the customer's existing assessment — same
   score, same tier, same factors.
2. **Given** a full dataset load touching every customer who already has an
   assessment, **When** the load completes and every enqueued recompute has
   run, **Then** exactly one assessment row still exists per customer (no
   duplicates) and every assessment's factors still sum to its score.

---

### User Story 5 - Manual Recompute Still Works Exactly As Before (Priority: P1)

A Risk Manager or System Administrator uses the on-demand recompute
capability introduced in Phase 3a — unchanged, still available, still
producing the same response shape and still subject to the same role
checks — regardless of whether automatic recompute exists or is currently
running for other customers.

**Why this priority**: The user description is explicit that automatic
recompute is additive, not a replacement. If the manual path regressed,
every Phase 3a guarantee about deliberate, attributable, on-demand
recomputation would be at risk alongside the new automatic path. This must
hold from day one of the new feature, not be treated as a nice-to-have
regression check.

**Independent Test**: Trigger a manual recompute for a customer through the
existing Phase 3a route while automatic recompute is enabled platform-wide,
and confirm the response, the audit trail, and the role enforcement are
identical to Phase 3a's behavior.

**Acceptance Scenarios**:

1. **Given** automatic recompute is active platform-wide, **When** a
   permitted user triggers the existing manual recompute route for a
   customer, **Then** the request succeeds exactly as it did before this
   feature existed, with the same response shape and the same role
   restrictions.
2. **Given** a manual recompute and an automatic recompute for the same
   customer could plausibly overlap, **When** both occur close together,
   **Then** the customer ends up with exactly one current assessment
   reflecting the most recently computed result — never a corrupted or
   partially-written state.

---

### Edge Cases

- What happens when a customer's data changes but that customer has never
  been scored at all (no existing `RiskAssessment`)? No automatic recompute
  is enqueued for them — initial scoring remains exclusively the batch
  command's responsibility, per the user description's explicit boundary.
- What happens when the message broker is temporarily unreachable when a
  change occurs? The record's own change is not lost or rolled back;
  the platform's behavior in this case (queue at the next opportunity vs.
  drop) MUST be a deliberate decision recorded during planning, not left
  implicit.
- What happens if a customer is archived (soft-deleted) between the change
  that triggered a recompute and the recompute actually running? The
  recompute must not create or resurrect state for a customer whose data is
  no longer live in a way that contradicts existing archival semantics.
- What happens when two changes to the same customer happen in rapid
  succession (e.g., a policy update immediately followed by a claim)? Both
  independently enqueue a recompute; the system must tolerate two recomputes
  for the same customer running in close succession without producing two
  conflicting assessments or a race that corrupts the stored score.
- What happens to the audit trail when an automatic recompute runs
  unattended (no human triggered it)? It must be attributable as "no user
  triggered this" the same honest way the existing batch command's entries
  already are — not silently blank in a way that looks like a data gap.
- What happens if a recompute task is still retrying when the underlying
  data changes again? The eventual recompute must reflect the customer's
  current data at the time it actually runs, not stale data captured when
  the task was first enqueued, so a customer's finally-computed score is
  never provably wrong at the moment it lands.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide a background task mechanism capable
  of running risk recompute work asynchronously, outside the request/response
  cycle of the API or the batch command.
- **FR-002**: The background task mechanism MUST use the platform's existing,
  already-provisioned message broker rather than introducing a new one.
- **FR-003**: Whenever a live Customer, Policy, or Claim record is created,
  updated, or archived, the platform MUST enqueue a background recompute
  attempt for the customer that record belongs to (directly, for a Customer
  record; via the owning customer, for a Policy or Claim record).
- **FR-004**: The enqueue trigger in FR-003 MUST be broad — any save on any
  of the three record types — rather than limited to only the specific
  fields that feed a scoring factor. This matches Phase 3a's existing
  staleness philosophy of over-reporting rather than fine-grained field
  tracking, and is a deliberate scope decision, not an oversight to later
  narrow.
- **FR-005**: A background recompute attempt for a customer who has no
  existing risk assessment MUST NOT create one. Automatic recompute only
  ever updates a customer who has already been scored at least once;
  initial scoring for a never-scored customer remains exclusively the
  responsibility of the existing batch scoring command.
- **FR-006**: A background recompute attempt that does proceed (because the
  customer already has an assessment) MUST produce a result using exactly
  the same computation and persistence logic the platform's existing
  on-demand recompute capability already uses, so the two paths cannot
  disagree about how a score is computed.
- **FR-007**: A background recompute attempt MUST leave the customer's
  assessment in a fully valid, fully explained state on success — the same
  invariants Phase 3a already requires (the assessment's factors sum to its
  score; every factor is present) apply identically whether the recompute
  was triggered manually or automatically.
- **FR-008**: A failed background recompute attempt MUST be retried
  automatically, with each successive retry delay longer than the one
  before it (exponential backoff), rather than retried immediately or not
  at all.
- **FR-009**: The number of retry attempts before a background recompute is
  considered permanently failed MUST be bounded — retries do not continue
  indefinitely.
- **FR-010**: When a background recompute exhausts its retry attempts
  without succeeding, the platform MUST create a durable, discoverable
  record of that failure identifying the affected customer, distinguishable
  from a successful recompute record. This record MUST NOT depend on any
  external alerting or notification service — it is satisfied by the
  platform's own existing structured logging and/or audit trail mechanisms.
- **FR-011**: A permanently failed recompute for a customer MUST NOT prevent
  a future data change for that same customer from enqueuing a fresh
  automatic recompute attempt.
- **FR-012**: The existing on-demand (manual) recompute capability from
  Phase 3a MUST remain available, unmodified in its request/response
  behavior, role enforcement, and audit behavior, regardless of whether
  automatic recompute is active.
- **FR-013**: When an automatic recompute and any other write to the same
  customer's assessment (manual recompute, another automatic recompute)
  occur close together, the platform MUST guarantee the customer ends up
  with exactly one current, internally consistent assessment — never a
  torn or partially-written state, and never more than one current
  assessment row for that customer.
- **FR-014**: Every automatic recompute — successful, retried, or
  permanently failed — MUST be recorded in the platform's existing audit
  trail, using the same append-only mechanism and attribution conventions
  (including the honest "no human triggered this" attribution) already
  established for the batch scoring command's unattended runs.
- **FR-015**: Every role and permission check that currently governs who
  may view or manually trigger a risk recompute MUST be unaffected by this
  feature. Automatic recompute does not introduce, remove, or alter any
  role's access to risk data.
- **FR-016**: Re-running the platform's existing dataset loader (which
  touches on the order of 3,000 customer/policy records per run) MUST
  enqueue a proportional number of automatic recompute attempts and MUST
  NOT corrupt, duplicate, or lose any customer's risk assessment as a
  result — every assessment must remain exactly as correct after the load
  as it was before, for every customer whose underlying data did not
  actually change.
- **FR-017**: The volume of redundant (same-answer) automatic recompute
  attempts generated by a full dataset load (per FR-016) is an accepted,
  documented tradeoff of this feature, not a defect. This specification
  does not require any mechanism to detect, suppress, batch, or coalesce
  redundant recompute attempts; the specification only requires that they
  remain correct, not that they be efficient.
- **FR-018**: The platform MUST behave predictably and safely (per FR-011
  and the edge cases above) when the message broker used by automatic
  recompute is temporarily unavailable — the customer record change itself
  must still succeed and be stored, independent of whether the recompute
  enqueue succeeds.

### Key Entities

- **Recompute Task**: One background unit of work representing "recompute
  this customer's risk assessment." Carries the identity of the customer to
  recompute and, implicitly through retries, its own attempt count and
  backoff state. Not a new persisted business entity — it exists in the
  message broker/task-runner's own bookkeeping, not as a new database
  table this feature introduces.
- **Recompute Failure Record**: A durable, discoverable record created when
  a Recompute Task exhausts its retries, identifying the affected customer
  and the fact that automatic recompute gave up. Realized through the
  platform's existing audit trail and/or logging — not a new alerting
  channel or external service.
- **RiskAssessment** *(existing, from Phase 3a, unchanged shape)*: The
  record automatic recompute updates in place when it succeeds — the same
  entity Phase 3a's engine and on-demand recompute route already produce
  and update. This feature does not add fields to it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A customer's risk assessment reflects a change to their
  policy, claim, or own record without any person manually triggering a
  recompute, within a short, bounded time of that change being saved.
- **SC-002**: 100% of automatic recompute attempts for a customer who
  already has an assessment leave that assessment in a fully explained,
  internally consistent state (factors sum to score, all factors present) —
  identical to the guarantee Phase 3a already provides for manual
  recomputes.
- **SC-003**: 0% of automatic recompute attempts create a new assessment
  for a customer who did not already have one.
- **SC-004**: A transient recompute failure that would succeed on a later
  attempt resolves itself automatically — without any person noticing or
  intervening — in the overwhelming majority of cases (a genuinely
  unrecoverable failure is expected to still surface via SC-005).
- **SC-005**: Every recompute that exhausts its retries produces a
  discoverable record within the platform's own audit/logging surface —
  100% of permanent failures are traceable to a specific customer after
  the fact, with zero reliance on an external alerting service.
- **SC-006**: A full dataset load touching every previously-scored customer
  in the seeded population completes with every one of those customers'
  assessments unchanged in content (same score, tier, factors) and
  unduplicated (exactly one assessment row per customer), even though the
  load enqueues a recompute attempt for each of them.
- **SC-007**: 100% of existing on-demand recompute requests continue to
  succeed with the same response shape, role enforcement, and audit
  behavior as before this feature existed.
- **SC-008**: Two recompute attempts for the same customer occurring close
  together never leave that customer with zero or more than one current
  assessment row.

## Assumptions

- Redis, already provisioned as platform infrastructure since Phase 1 but
  unused until now, is available as the message broker for the background
  task mechanism this feature introduces (per the constitution's Technology
  Stack Constraints, which name both Redis and Celery as the binding
  cache/queue-broker and background-jobs stack).
- "Short, bounded time" for automatic recompute (SC-001) means seconds to
  low tens of seconds under normal operation, not real-time/sub-second —
  consistent with this being a background, eventually-consistent process
  rather than a synchronous part of the request that changed the data.
- A background worker process capable of consuming these tasks is expected
  to be running as part of the platform's normal operation (analogous to
  how the web process is expected to be running); a scenario where no
  worker is running at all is an operational/deployment concern, not a
  behavior this feature's functional requirements need to specify.
- "Alert" for a permanently-failed recompute (FR-010, SC-005) means a
  record inside the platform's own boundaries — the existing audit log
  and/or structured application logs — discoverable by a human or a future
  monitoring process that queries those surfaces. It explicitly does not
  mean an email, SMS, push notification, or third-party incident-management
  integration; no such channel exists in this local-first, no-cloud-
  dependency platform, and introducing one is out of scope.
- Task-coalescing, deduplication, or debouncing of redundant recompute
  attempts (e.g., collapsing many rapid changes to one customer into a
  single recompute, or suppressing enqueues during a known bulk load) is
  explicitly out of scope for this feature. FR-016/FR-017 name the
  resulting inefficiency as accepted rather than solved; a future
  optimization spec may address it without changing this feature's
  correctness guarantees.
- This feature only recomputes customers who already have a `RiskAssessment`
  as of the moment a task actually runs (not as of when it was enqueued);
  the initial-scoring population (customers with no assessment yet) remains
  exclusively covered by the existing batch scoring command, unchanged.
- Archived (soft-deleted) records follow the same archival visibility rules
  already established in Phases 2 and 3a — this feature does not change what
  counts as "live" data for scoring purposes, it only changes when a
  recompute using that existing live-data definition is triggered.
