# Contract: `recompute_customer_risk` Celery Task

**Feature**: 006-automatic-risk-recompute | **Module**: `apps/risk/tasks.py`

This feature adds no new HTTP endpoint — the on-demand recompute route from
Phase 3a is unchanged (FR-012; see
[risk-assessment-api.md](../../005-risk-scoring-engine/contracts/risk-assessment-api.md),
still authoritative). The contract this phase introduces is internal: the
signature and guaranteed behavior of the background task, and the trigger
conditions that enqueue it. Documented here with the same precision as an
API contract because it is the boundary other future work (e.g. a Phase 5
Fraud recompute following the same pattern) would integrate against.

## Task signature

```python
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def recompute_customer_risk(self, customer_id: int) -> None:
    ...
```

**Arguments**: `customer_id` — the primary key of a `customers.Customer` row.
Never a `Customer` instance, a `client_id`, or any other identifier — tasks
are serialized to the broker as JSON, so the argument must be a plain,
serializable value, and re-fetching the row inside the task (rather than
passing a snapshot) is also what guarantees the task always acts on the
customer's *current* data at execution time, not stale data captured when
the task was enqueued (per the spec's edge case: "a recompute task ... must
reflect the customer's current data at the time it actually runs").

**Return value**: `None` in every case (no-op, success, or an exception that
Celery's own retry/exhaustion machinery handles). Nothing in this feature
calls `.get()` on the task's `AsyncResult` or otherwise depends on a return
value — this is a fire-and-forget task by design (research.md §4: no result
backend is configured for durability, since nothing reads one).

## Behavior contract

| Precondition | Behavior |
|---|---|
| `customer_id` does not resolve to a live `Customer` (deleted, or archived — `Customer.objects` default manager) | No-op. Returns without calling `engine.score_customer()` or writing anything. Not an error, not retried. |
| Customer exists but has no `RiskAssessment` | No-op (FR-005). This is the ONLY branch that distinguishes automatic recompute from Phase 3a's manual recompute, which *does* create an assessment for a never-scored customer. Automatic recompute never does. |
| Customer exists and already has a `RiskAssessment` | `engine.score_customer(customer)` then `engine.persist(customer, result, actor=None)` — identical to Phase 3a's manual recompute action and to `computerisk`'s per-customer call, byte-for-byte the same two function calls (FR-006). |
| `engine.persist()` (or anything it calls) raises | Celery's `autoretry_for` catches it, schedules a retry with exponential backoff (FR-008), up to `max_retries` (FR-009). |
| The `max_retries`th retry also fails | Celery marks the task permanently failed; the task's `on_failure` handler writes one `AuditLog` entry via `record_action(action="risk.recompute_failed", outcome="refused", actor=None, ...)` (FR-010) and logs a structured error. The exception is not re-raised beyond that point — the worker process does not crash (spec edge case). |

**Idempotency**: Calling this task twice in immediate succession for the
same `customer_id` — which is exactly what happens when, e.g., a Policy
update and a Claim creation both fire moments apart for the same customer
(spec edge case: "two changes... in rapid succession") — must never corrupt
the assessment or produce two assessment rows. This holds without any new
locking logic in this feature: `engine.persist()`'s existing
`select_for_update()` on the customer row (Phase 3a, unchanged) already
serializes concurrent persists for the same customer, so the two task
executions simply run one after the other, each producing a fully valid
assessment, with the later one's result being what's stored — exactly the
same guarantee two near-simultaneous manual recomputes already have today.

## Trigger contract (what enqueues this task)

| Event | Where connected | Resolution to `customer_id` |
|---|---|---|
| `Customer` row saved (`post_save`, any `created` value, including an archival save) | `apps/customers/apps.py` `ready()` | `instance.id` |
| `Policy` row saved (`post_save`, any `created` value, including an archival save) | `apps/policies/apps.py` `ready()` | `instance.customer_id` |
| `Claim` row saved (`post_save`, any `created` value, including an archival save) | `apps/claims/apps.py` `ready()` | `instance.policy.customer_id` |

Each receiver enqueues via `transaction.on_commit(lambda: recompute_customer_risk.delay(customer_id))`
— never a bare `.delay()` inside the receiver — so a save that is later
rolled back (e.g. inside a larger failed transaction) never enqueues a task
for data that was never actually persisted. This is the one `on_commit`
usage in this feature and is deliberately narrower than the audit-write
`on_commit` pattern the platform's own conventions reject (see
research.md §1) — it exists here because the requirement is the opposite
one: don't act on data that might not be real, rather than don't decouple
an audit write from the change it describes.

**Trigger is unconditional on field-level relevance** (FR-004): every save
enqueues, regardless of which fields changed, including saves that touch no
scoring-relevant field at all (e.g. `Customer.phone`, `Policy.renewal_probability`).
This is deliberate over-triggering, matching Phase 3a's staleness philosophy,
and is not something a future caller should "fix" by adding field-level
diffing without a new spec deciding to do so (FR-017 names the resulting
redundant-task volume as an accepted tradeoff, not a defect).

## What this contract explicitly does NOT cover

- **No new HTTP route.** `POST /api/risk/assessments/recompute/` from Phase
  3a is the only HTTP surface for triggering a recompute; this task is never
  invoked directly from a view.
- **No task-coalescing or deduplication.** Two enqueues for the same
  customer in the same second remain two separate task executions (FR-017).
- **No cross-customer batching.** Unlike `computerisk`, which iterates the
  whole book in one command invocation, this task always processes exactly
  one customer per execution — that is what makes it composable with
  per-record signals in the first place.
