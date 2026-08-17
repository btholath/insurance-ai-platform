# Contract: `computerisk` Management Command

**Feature**: 005-risk-scoring-engine

The batch path (FR-030). A new command in `apps/risk/management/commands/`,
following the shape of `loaddataset` — same reporting discipline, same
per-record atomicity, same "continue past a failure and report it" posture.

```bash
python manage.py computerisk [--customer CLIENT_ID] [--tier TIER] [--dry-run] [--limit N]
```

## Arguments

| Argument | Effect |
|---|---|
| *(none)* | Score every live customer |
| `--customer CLIENT_ID` | Score one customer, by client reference (`CL-00042`) |
| `--tier TIER` | Rescore only customers currently in a given tier |
| `--dry-run` | Compute and report, write nothing (FR-040-adjacent: a read-only preview) |
| `--limit N` | Stop after N customers; for smoke-testing on a large book |

`--dry-run` writes **no assessment, no factor row, no mirror, and no audit
entry**. It is the safe way to preview a rule change before it touches stored
decisions.

## Output

```text
Computing risk scores (rule set 1.0.0)...

  scored:   3000
  skipped:     0
  failed:      0

Tier distribution:
  low         1003  (33.4%)
  moderate     959  (32.0%)
  elevated     507  (16.9%)
  high         531  (17.7%)

Completed in 41.2s
```

With skips:

```text
  scored:   2998
  skipped:     2
  failed:      0

Skipped:
  CL-00997  no live policy, so premium and coverage type are unknown
  CL-01455  no live policy, so premium and coverage type are unknown
```

**Counts must account for every customer considered** (FR-031, SC-006):
`scored + skipped + failed == total considered`. Asserted in
`test_computerisk.py`, not merely printed.

## Behaviour

**Per-customer atomicity** (FR-032, FR-035). Each customer is its own
transaction: assessment, five factor rows, the `Customer.risk_score` mirror, and
the audit entry commit together or not at all. A failure on one customer is
reported and the run continues — it never aborts the batch, and never leaves a
customer with a score whose factors are missing (User Story 2, scenario 6).

**Skips are not failures** (FR-018). A customer with no live policy cannot be
scored, and that is a legitimate outcome reported with its reason — not an error,
and not a zero score. The seeded data produces no skips (every customer has
exactly one policy), so this path is covered by constructed fixtures.

**Idempotency** (FR-033). Re-running over unchanged data produces identical
scores, tiers, and factor rows, and does not accumulate duplicate assessments —
`RiskAssessment` is one-per-customer and updated in place. Verified empirically
by a real double-run in [quickstart.md](../quickstart.md) step 6, not merely
asserted.

**Archived records excluded** (FR-016). The command iterates `Customer.objects`
(archived customers invisible) and the engine reads policies and claims through
their default managers, so archival exclusion falls out of the existing
dual-manager design rather than needing a filter here.

**Determinism** (FR-002, SC-004). No randomness, no clock-dependent factor, no
ordering dependence. `computed_at` differs between runs; the score, tier, and
factor rows do not.

**Performance**. Chunked iteration with `select_related`/`prefetch_related` over
policies and claims, `bulk_create` for factor rows. Target < 60s for 3,000
customers — a naive per-customer implementation would issue ~12,000 queries.

## Audit (FR-048, FR-050, FR-054)

Two kinds of entry:

| Action | Per | Payload |
|---|---|---|
| `risk.computed` | Each customer scored | `before={"score": <prev or null>}`, `after={"score": <new>, "tier": ..., "rule_set_version": ...}` |
| `risk.batch_computed` | The run | `context={"scored": n, "skipped": n, "failed": n, "rule_set_version": ..., "dry_run": false}` |

The run entry makes a batch distinguishable from the individual computations
within it (FR-050). Every entry carries the rule-set version (FR-054).

`computed_by` and the audit `actor` are **null** for an unattended command run —
`record_action` already handles a null actor, writing an empty actor identifier.
That is honest: no user triggered it. A `--customer` run from an operator's shell
is still null-actored, because the command has no authenticated user; per-user
attribution is what the API recompute route is for.

**A recompute that changes nothing is still recorded** (FR-049).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Completed; skips are not failures |
| `1` | Aborted before scoring (bad argument, unknown `--customer`, unknown `--tier`) |
| `2` | Completed but one or more customers failed |

## Relationship to Phase 3b

This command and the API trigger are the **only** ways a score changes in this
phase (FR-036). Phase 3b will call the same `engine.persist()` from a Celery
task; nothing here is scaffolding for that, and nothing here should be
generalised in anticipation of it. The split between pure evaluation and
persistence (§6 of research.md) is what makes 3b additive rather than a rewrite.
