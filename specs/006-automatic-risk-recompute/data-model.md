# Phase 1 Data Model: Automatic Risk Recompute

**Feature**: 006-automatic-risk-recompute | **Date**: 2026-08-21

No new Django model, no new migration. This is the load-bearing fact about
this feature's data shape: everything it touches already exists from Phase
3a, and this phase's job is orchestration around that existing shape, not
new storage. Decisions are grounded in [research.md](./research.md).

---

## What does NOT change

- **`RiskAssessment`** (`apps/risk/models.py`) — unchanged. Same fields,
  same constraints, same `computed_by` nullable FK. An automatic recompute
  writes `computed_by=None`, using the field's existing nullable contract
  exactly as `computerisk`'s unattended runs already do (data-model.md of
  005: "`computed_by`... Null when the batch command runs unattended").
- **`RiskFactor`** — unchanged. Automatic recompute produces the same five
  rows, fully replaced, via the same `engine.persist()` call every other
  write path uses.
- **`Customer.risk_score`** — unchanged. Still the denormalised mirror
  `persist()` already maintains; automatic recompute updates it through the
  same code path, not a new one.
- **`AuditLog`** (`apps/audit/models.py`) — unchanged schema. This feature
  writes more rows to it (via the existing `record_action()`), using two
  action names that are new *values*, not new *columns*:
  - `risk.computed` — already exists (Phase 3a); automatic recompute writes
    the same action name manual recompute and `computerisk` already write,
    with `actor=None`. Nothing distinguishes an automatic `risk.computed`
    entry from a `computerisk` batch entry at the schema level, which is
    correct: both are "the risk engine ran, unattended." A reader who needs
    to tell them apart uses `context` (see below) or accepts that the
    platform does not distinguish "automatic-triggered" from
    "batch-triggered" unattended computation, since neither has a human
    actor to name and FR-014 does not require the distinction.
  - `risk.recompute_failed` — **new value**, not a new table. Written once
    per customer per exhausted-retry event (FR-010), `outcome="refused"`,
    `context={"customer_id": ..., "exception": "<str(exc)>", "attempts": N}`.
    This is the "Recompute Failure Record" the spec's Key Entities section
    names — realized entirely as an `AuditLog` row with this action value,
    per research.md §3's decision against a dedicated model.

## What exists only in the message broker (not the database)

- **Recompute Task** (per spec.md's Key Entities) — a Celery task message
  in Redis: `customer_id` as its sole argument, plus Celery's own
  bookkeeping (task id, retry count, ETA for the next backoff attempt).
  This is infrastructure state, not business data — it is never queried by
  the application, never joined against a model, and does not survive a
  successful (or exhausted) task completion. No schema is defined for it
  here because none is owned by this feature; it is entirely Celery's
  internal representation.

## Field-level mapping: signal → task → write

For traceability, since no new model exists to anchor this feature's data
flow, this table stands in for the usual entity-relationship description:

| Trigger | Resolved to | Task argument | Existing write path invoked |
|---|---|---|---|
| `Customer` saved (create/update/archive) | itself | `customer.id` | `engine.score_customer()` + `engine.persist()` |
| `Policy` saved (create/update/archive) | `policy.customer_id` | `policy.customer_id` | same |
| `Claim` saved (create/update/archive) | `claim.policy.customer_id` | `claim.policy.customer_id` | same |

No new field is added to `Customer`, `Policy`, or `Claim` to support this —
the FK traversal (`claim.policy.customer_id`) already exists and is a single
indexed lookup, not a new query pattern.

## Relationships

```text
Customer ──1:1── RiskAssessment ──1:N── RiskFactor      (unchanged, Phase 3a)
   │
   ├──post_save──▶ enqueue_recompute(customer.id)
   │
Policy ──FK──▶ Customer
   │
   └──post_save──▶ enqueue_recompute(policy.customer_id)

Claim ──FK──▶ Policy ──FK──▶ Customer
   │
   └──post_save──▶ enqueue_recompute(claim.policy.customer_id)

recompute_customer_risk(customer_id)   [Celery task, apps/risk/tasks.py]
   │
   ├─ RiskAssessment.objects.filter(customer_id=customer_id).exists()?
   │     NO  → return (FR-005; no-op, no write of any kind)
   │     YES → engine.score_customer() + engine.persist(actor=None)
   │
   └─ on final failure (retries exhausted) → record_action(
         action="risk.recompute_failed", outcome="refused", ...)
```

## Volumes (informational, not a new capacity requirement)

No new row-volume estimate is meaningful here in the way Phase 3a's
data-model.md gave one (3,000 assessments, 15,000 factors) — this feature
adds zero new rows of its own shape. The only volume note worth recording is
the one the spec names explicitly as an accepted tradeoff: a full
`loaddataset` run against the seeded 3,000-customer population enqueues on
the order of 3,000 Celery tasks (one per `Customer`/`Policy` write the
loader performs), the large majority of which resolve as fast, correct,
same-answer recomputes (FR-016/FR-017). This is Celery/Redis queue traffic,
not database row growth — it does not add rows to `RiskAssessment` or
`RiskFactor` (idempotent update-in-place, per Phase 3a's existing
`update_or_create` in `engine.persist()`), and it adds exactly one
`AuditLog` row per successful automatic recompute, the same as any other
`risk.computed` write already does today.
