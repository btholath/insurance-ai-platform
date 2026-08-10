# Phase 1 Data Model: Policy Management

**Feature**: `003-policy-management` | **Date**: 2026-08-09

The Policy entity, and the existing entities this feature touches.

---

## Policy (new) — `apps/policies/models.py`

Inherits `apps.core.models.TimeStampedModel` for `created_at` / `updated_at`
(FR-006), exactly as Customer does.

### Fields

| Field | Type | Null | Constraints / notes | Requirement |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | The stable identifier Claims will reference. No external reference field — the dataset has no policy ID column | FR-007 |
| `customer` | `FK(Customer)` | **no** | `on_delete=PROTECT`, `related_name="policies"`, `db_index` | FR-002, FR-003 |
| `policy_type` | `CharField(16)` | no | choices: `Life`, `Auto`, `Property`, `Health`; `db_index` | FR-001, FR-009 |
| `start_date` | `DateField` | no | calendar date, no timezone interpretation | FR-001 |
| `end_date` | `DateField` | no | must be `> start_date`; `db_index` for the expiry filter | FR-001, FR-010 |
| `premium_usd` | `DecimalField(10,2)` | no | must be `> 0` | FR-001, FR-011 |
| `renewal_probability` | `DecimalField(3,2)` | **yes** | 0.00–1.00; stored only, never computed | FR-004, FR-005, FR-012 |
| `archived_at` | `DateTimeField` | **yes** | null = live; set = archived | FR-021 |
| `created_at` / `updated_at` | `DateTimeField` | no | from `TimeStampedModel` | FR-006 |

**On `premium_usd` width**: `max_digits=10` allows up to 99,999,999.99. The
dataset spans 100.68–4997.79, but a commercial premium is not bounded by this
consumer sample, and widening a numeric column later is a table rewrite.

**On `renewal_probability` nullability**: `null=True`, and asserted with
`is None` rather than truthiness. Verified against the source file: **13 rows
carry a renewal probability of exactly `0.0`**. Those are real, loaded,
non-null zeros. Any code testing this field for truthiness silently reclassifies
all 13 as "no renewal probability recorded" — the same trap as Customer's score
fields, but here with a concrete count behind it.

**No external reference**: unlike Customer's `client_id`, there is no
`policy_id`. The source file carries no policy identifier, the loader's
idempotency key is `(customer, policy_type)`, and inventing a `POL-#####`
would add generation-under-lock machinery serving no requirement.

### Managers

```python
class PolicyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)

class Policy(TimeStampedModel):
    ...
    objects = PolicyManager()      # declared FIRST -> _default_manager
    all_objects = models.Manager()
```

Same dual-manager pattern as Customer, same ordering requirement: `objects`
first so it remains `_default_manager`, which is what `customer.policies`
traversal uses — so an archived policy does not surface through its customer.

### Constraints and indexes

```python
class Meta:
    ordering = ["id"]
    constraints = [
        CheckConstraint(
            name="policy_end_after_start",
            condition=Q(end_date__gt=F("start_date")),
        ),
        CheckConstraint(
            name="policy_premium_positive",
            condition=Q(premium_usd__gt=0),
        ),
        CheckConstraint(
            name="policy_renewal_probability_range",
            condition=Q(renewal_probability__isnull=True)
                      | (Q(renewal_probability__gte=0)
                         & Q(renewal_probability__lte=1)),
        ),
        UniqueConstraint(
            fields=["customer", "policy_type"],
            condition=Q(archived_at__isnull=True),
            name="policy_unique_live_type_per_customer",
        ),
    ]
    indexes = [
        models.Index(fields=["policy_type"]),
        models.Index(fields=["end_date"]),
        models.Index(fields=["customer", "policy_type"]),
    ]
```

**The `isnull` disjunction on `renewal_probability` is required** — without it
a NULL makes the comparison SQL-NULL rather than true, and Postgres rejects
every policy created without a renewal probability, which is every policy
created through the API. This is the same trap Phase 2a hit; it is spelled out
because it is invisible until the first API create fails.

**The unique constraint is deliberately scoped to live rows.** This is the
opposite of Customer, where `client_id` uniqueness spans archived rows because
FR-021 requires the reference to stay *reserved*. Here, archival must **not**
permanently consume a coverage slot: archive a customer's auto policy and they
must be able to hold auto cover again. Same mechanism, opposite requirement —
stated plainly so it is not later "fixed" into matching Customer.

### Relationship to Customer

```
Customer  1 ──────< N  Policy
   │                     │
   │ archived_at         │ archived_at
   │ (independent)       │ (independent)
   └─────────────────────┘
     archiving the customer does NOT touch policies (FR-022)
```

Two directions, which fail independently and are therefore tested separately:

| Direction | Behavior | Requirement |
|---|---|---|
| Archived customer → its live policy | Policy stays readable, link intact | FR-008, FR-022 |
| Live customer → its archived policy | Policy hidden from `customer.policies` | FR-021 |

**FK resolution in the write path goes through `Customer.all_objects`.** If the
serializer resolved the FK through `Customer.objects` (which hides archived
rows), reading or updating a policy whose customer was archived would fail —
exactly the orphaning FR-022 forbids.

**Creating a policy for an archived customer is refused** (FR-014), naming
`customer`. Resolution finds the customer via `all_objects`, then explicitly
checks `archived_at is None`. Resolving through `objects` instead would produce
"customer does not exist" — a misleading refusal that sends an underwriter
hunting for a missing record rather than a removed one.

**`on_delete=PROTECT`**: customer removal through the API is archival and never
reaches this, but `PROTECT` is the backstop against a hard
`Customer.objects.delete()` destroying policy history.

### State transitions

```
             create
   (absent) --------> LIVE  (archived_at IS NULL)
                       │           ↑
                       │           └── occupies the (customer, policy_type)
                       │               live-uniqueness slot
                       │ DELETE -> archived_at = now()
                       ▼
                   ARCHIVED  (slot released; a new live policy of the
                              same type may now be created)
```

Archived is terminal through the API: an archived policy 404s on GET, PATCH,
and DELETE, because the viewset's queryset is built from `objects`. There is
no un-archive endpoint.

**The loader does not resurrect archived policies.** Matching filters to live
rows, so a load after an archival creates a *fresh* live policy rather than
un-archiving. FR-038 requires one **live** policy per source row, and silently
undoing a deliberate removal would be worse than creating a new record.

---

## Serializers — `apps/policies/serializers.py`

| Serializer | Use | Notes |
|---|---|---|
| `PolicySerializer` | read + create + loader | Single definition of validity shared with the loader (FR-043) |
| `PolicyUpdateSerializer` | PATCH | All fields optional; same rules |

`id`, `created_at`, `updated_at`, `archived_at` are read-only.
`customer` is a `PrimaryKeyRelatedField` whose queryset is `Customer.all_objects`,
with an explicit archived check layered on top (FR-014).

Cross-field date coherence lives in `validate()`, not a field validator — that
is what lets the FR-010 error name both dates rather than one.

Read responses embed a minimal customer summary (`id`, `client_id`, `name`) so
US1's "review a customer's coverage" does not require a second request per row.
`select_related("customer")` on the list route keeps that from becoming N+1
across a 50-record page.

---

## Customer (existing, modified only by association)

Gains `related_name="policies"`. No field changes, no migration to
`apps/customers/`.

The Phase 2a archival semantics are unchanged and now carry a second guarantee:
archiving a customer leaves their policies readable (FR-022). Phase 2a's
Customer tests must continue to pass untouched.

---

## AuditLog (existing, unmodified)

| Column | Value written by this feature |
|---|---|
| `action` | `policy.created`, `policy.updated`, `policy.deleted`, `policy.viewed` (refusals) |
| `target_type` | `"policies.Policy"` |
| `target_id` | `str(policy.id)` |
| `outcome` | `succeeded`, or `refused` (FR-031) |
| `before` / `after` | Changed fields only on update (FR-029); full values on delete (FR-030) |
| `actor` | The requesting user; **`None`** for the dataset load (FR-048) |
| `context` | `{"source": "loaddataset", "file": <path>}` for loader rows |

Immutability (FR-034) is already guaranteed by `AuditLog.save()`/`delete()`
raising and by the Phase 1 database trigger. No new work.

---

## Audited route registry (new) — `apps/core/audit_routes.py`

Not a database entity — the configuration that generalizes refusal recording.

```python
AuditedRoute = namedtuple(
    "AuditedRoute",
    "prefix target_type action_prefix view_roles write_roles",
)
```

| Field | Customers entry | Policies entry |
|---|---|---|
| `prefix` | `/api/customers/` | `/api/policies/` |
| `target_type` | `customers.Customer` | `policies.Policy` |
| `action_prefix` | `customer` | `policy` |
| `view_roles` | 7 roles | **8 roles** (adds Product Manager) |
| `write_roles` | Customer Service, Sys Admin | **Underwriter**, Sys Admin |

The role sets differ per module, and that difference is load-bearing: a Product
Manager hitting a missing *policy* is an ordinary miss (they may read policies),
while the same user hitting a missing *customer* is a refusal (they may not).
A single platform-wide role set would record one of these wrongly.

---

## PolicyFactory — `apps/policies/factories.py`

```python
class PolicyFactory(DjangoModelFactory):
    class Meta:
        model = Policy
        skip_postgeneration_save = True

    customer = factory.SubFactory(CustomerFactory)
    policy_type = "Auto"
    start_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    end_date = factory.LazyFunction(lambda: date.today() + timedelta(days=365))
    premium_usd = Decimal("750.23")
    renewal_probability = None
    archived_at = None

    class Params:
        archived = factory.Trait(archived_at=factory.LazyFunction(timezone.now))
        expired = factory.Trait(
            start_date=date.today() - timedelta(days=730),
            end_date=date.today() - timedelta(days=1),
        )
        scored = factory.Trait(renewal_probability=Decimal("0.06"))
```

Defaults produce a **live, currently-in-force** policy: start in the past, end
in the future. The `expired` trait is what FR-020's filter is tested against;
without an explicit trait, every factory-made policy would be in force and the
expiry filter would pass vacuously.

`renewal_probability` defaults to `None`, matching an API-created policy and
keeping the FR-004 absent-vs-zero distinction visible by default.

`customer` uses `SubFactory`, so a test needing several policies for one
customer must pass `customer=` explicitly — otherwise each policy gets its own
customer and the FR-003 multi-policy case is never actually exercised.
