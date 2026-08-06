# Phase 1 Data Model: Customer Management

**Feature**: `002-customer-management` | **Date**: 2026-08-06

Entities introduced by this feature, and the two existing entities it touches
without modifying.

---

## Customer (new) — `apps/customers/models.py`

Inherits `apps.core.models.TimeStampedModel`, which supplies `created_at`
(`auto_now_add`) and `updated_at` (`auto_now`) — FR-008 needs no new fields.

### Fields

| Field | Type | Null | Constraints / notes | Requirement |
|---|---|---|---|---|
| `id` | `BigAutoField` | no | Platform-internal PK; the stable identifier Policy will reference | FR-044 |
| `client_id` | `CharField(16)` | no | `unique=True`, validated against `^CL-\d{5,}$`; auto-generated when absent | FR-002, FR-003, FR-005 |
| `name` | `CharField(255)` | no | non-blank; `db_index=True` for search | FR-001, FR-009 |
| `email` | `EmailField(254)` | no | **explicitly NOT unique**; `db_index=True` | FR-001, FR-004, FR-010 |
| `phone` | `CharField(64)` | no | free text, stored as supplied — no normalization | FR-001 |
| `age` | `PositiveSmallIntegerField` | no | 18–120 inclusive | FR-001, FR-011 |
| `gender` | `CharField(16)` | no | choices: `Male`, `Female`, `Other` | FR-001, FR-012 |
| `location` | `CharField(255)` | no | free text | FR-001 |
| `lead_source` | `CharField(32)` | no | choices: `Agent`, `Referral`, `Social Media`, `Web` | FR-001, FR-012 |
| `risk_score` | `DecimalField(3,2)` | **yes** | 0.00–1.00; stored only, never computed | FR-006, FR-007, FR-013 |
| `fraud_risk_flag` | `CharField(16)` | **yes** | choices: `Low`, `Medium`, `High`; stored only | FR-006, FR-007, FR-012 |
| `cross_sell_score` | `DecimalField(3,2)` | **yes** | 0.00–1.00; stored only | FR-006, FR-007, FR-013 |
| `archived_at` | `DateTimeField` | **yes** | null = live; set = archived. The soft-delete marker | FR-020, FR-021 |
| `created_at` | `DateTimeField` | no | from `TimeStampedModel` | FR-008 |
| `updated_at` | `DateTimeField` | no | from `TimeStampedModel` | FR-008 |

**On the three nullable scores**: `null=True` and **no** `blank=True`-driven
empty-string path. An absent score is `None`, never `0` and never `""`.
FR-006 requires absent to be distinguishable from zero, and this is the field
definition that makes it true — a test asserts `risk_score is None` (not
falsy) on an API-created customer.

This is not a hypothetical distinction. Verified against the source file,
`Cross_Sell_Score` has an observed minimum of **exactly `0.0`**, so the loaded
dataset contains genuine zero scores alongside the nulls that API-created
customers carry. Any code that tests a score for truthiness rather than for
`None` will silently conflate a real 0.00 score with an absent one. The
assertion is therefore `is None`, never `if not score`.

`max_digits=3, decimal_places=2` accommodates the observed range for both
score columns (`Risk_Score` 0.10–1.00, `Cross_Sell_Score` 0.00–1.00),
including the boundary value `1.00`.

**On `fraud_risk_flag`'s name**: it holds three levels, not a boolean, despite
the "flag" suffix. The name is carried over from the source column
`Fraud_Risk_Flag` deliberately; renaming is a Phase 5 concern per the spec's
Assumptions.

**On `phone` as free text**: the source uses `588-240-1527`, `405.085.5427`,
`(529)223-6740`, `076.947.4706x46406`, and `3799757647` interchangeably.
Normalizing would lose the extension syntax and no requirement needs it.

### Managers

```python
class CustomerManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)

class Customer(TimeStampedModel):
    ...
    objects = CustomerManager()      # declared FIRST -> _default_manager
    all_objects = models.Manager()   # sees archived rows too
```

`objects` must be declared first so it remains `_default_manager`, which is
what related-object traversal uses — this is what keeps an archived customer
from surfacing through a future `policy.customer` access without Policy
needing to know archival exists.

**`all_objects` is load-bearing, not a convenience.** FR-021 requires an
archived customer's `client_id` to stay reserved so a re-load reconciles
against it. The loader's create-vs-update lookup therefore **must** go through
`all_objects`. If it went through `objects`, the loader would not see the
archived row, would conclude the reference was free, would attempt an insert,
and would hit the unique constraint on a row it cannot see — an
`IntegrityError` on an apparently-unused reference. This is asserted directly
by a test (archive a customer, re-run the load, expect reconciliation and no
duplicate), because the property is invisible in ordinary use and easy to
regress.

### Database constraints

```python
class Meta:
    ordering = ["id"]
    constraints = [
        CheckConstraint(name="customer_age_valid",
                        check=Q(age__gte=18) & Q(age__lte=120)),
        CheckConstraint(name="customer_risk_score_range",
                        check=Q(risk_score__isnull=True)
                              | (Q(risk_score__gte=0) & Q(risk_score__lte=1))),
        CheckConstraint(name="customer_cross_sell_score_range",
                        check=Q(cross_sell_score__isnull=True)
                              | (Q(cross_sell_score__gte=0)
                                 & Q(cross_sell_score__lte=1))),
    ]
    indexes = [
        models.Index(fields=["lead_source"]),
        models.Index(fields=["fraud_risk_flag"]),
        models.Index(fields=["archived_at"]),
    ]
```

The `isnull` disjunction in the score constraints matters: without it, a null
score makes the comparison SQL-NULL rather than true, and Postgres would
reject every customer created without a score — which is every customer
created through the API.

These constraints are a **backstop**, not the primary enforcement. The
serializer is the single definition of validity (FR-038 requires the loader to
apply identical rules, and it does so by using the same serializer). The
constraints exist to catch a future code path that bypasses the serializer.

`unique=True` on `client_id` is the real guarantee behind FR-003 and the race
backstop for reference generation — it holds across archived rows too, since
archival does not remove the row.

### Reference generation (FR-005)

Runs inside the creating transaction when `client_id` is absent:

```python
with transaction.atomic():
    last = (Customer.all_objects
            .select_for_update()
            .annotate(num=Cast(Substr("client_id", 4), IntegerField()))
            .order_by("-num")
            .first())
    client_id = f"CL-{(last.num + 1) if last else 1:05d}"
```

Ordering is on the **extracted numeric suffix**, not the raw string.
`order_by("-client_id")` is a lexicographic sort on a `CharField` and is
correct only while every reference is exactly five digits — at `CL-100000`,
`"CL-99999"` still sorts higher and the generator begins reissuing existing
references. Sorting numerically is correct at any width.

The scan uses `all_objects` so archived references are never reissued (FR-021).
On an empty table there is no row to lock, so two concurrent first-creates can
both compute `CL-00001`; the unique constraint rejects the loser and a single
retry resolves it.

### State transitions

```
             create
   (absent) --------> LIVE  (archived_at IS NULL)
                       |
                       | DELETE  -> sets archived_at = now()
                       v
                    ARCHIVED (archived_at IS NOT NULL)
                       |
                       | loader match on client_id via all_objects
                       v
              reconciled in place (FR-021) — never duplicated
```

Archived is terminal through the API: an archived customer 404s on GET, PATCH,
and DELETE, because the viewset's queryset is built from `objects`. There is
no un-archive endpoint — FR-020 requires the record be *retained*, not that it
be restorable through the API. Re-deleting an archived customer is a 404, not
a double-archive.

---

## Serializers — `apps/customers/serializers.py`

| Serializer | Use | Notes |
|---|---|---|
| `CustomerSerializer` | read + create + loader | Single definition of validity, shared by API and CSV loader per FR-038 |
| `CustomerUpdateSerializer` | PATCH | All fields optional; `client_id` writable so FR-003's conflict case is reachable and returns 409-equivalent |

`id`, `created_at`, `updated_at`, `archived_at` are read-only everywhere.
`client_id` is writable but validated for uniqueness and format.

DRF's `ChoiceField` and `EmailField` name the offending field in their errors,
which is what FR-012 and FR-014 require. FR-016's partial-update requirement is
DRF's `partial=True` behavior; a test asserts that patching only `phone` leaves
every other field byte-identical.

---

## AuditLog (existing, unmodified) — `apps/audit/models.py`

This feature writes to it and changes nothing about it.

| Column | Value written by this feature |
|---|---|
| `action` | `customer.created`, `customer.updated`, `customer.deleted` |
| `target_type` | `"customers.Customer"` |
| `target_id` | `str(customer.id)` — the internal PK, not `client_id` |
| `outcome` | `succeeded`, or `refused` for FR-030 permission denials |
| `before` / `after` | Changed fields only on update (FR-028); full values on delete (FR-029) |
| `actor` | The requesting user; **`None`** for the CSV loader (FR-042) |
| `context` | `{"source": "loadcustomers", "file": <path>}` for loader rows |

`target_id` uses the internal PK rather than `client_id` so the audit trail
survives a `client_id` correction, consistent with FR-044 treating the internal
id as the stable identifier.

Immutability (FR-032) is already guaranteed by `AuditLog.save()`/`delete()`
raising and by the database trigger in migrations `0002`/`0003`. Migration
`0003` relaxed that trigger to allow a null actor — which is precisely what
FR-042's system-load attribution needs, already in place from Phase 1.

---

## User and Role (existing, unmodified) — `apps/accounts/models.py`

Used only as the subject of permission checks and as `AuditLog.actor`. The
FR-024 matrix maps onto the existing `Role` choices:

| Constant | View | Write |
|---|---|---|
| `CUSTOMER_SERVICE` | yes | **yes** |
| `SYSTEM_ADMINISTRATOR` | yes | **yes** |
| `UNDERWRITER` | yes | no |
| `CLAIMS_ADJUSTER` | yes | no |
| `FRAUD_ANALYST` | yes | no |
| `RISK_MANAGER` | yes | no |
| `COMPLIANCE_OFFICER` | yes | no |
| `PRODUCT_MANAGER` | no | no |
| `EXECUTIVE_LEADERSHIP` | no | no |
| *(unauthenticated)* | no | no |

Enforced by the existing `HasRole` factory from `apps/core/permissions.py`,
which already refuses superuser bypass (FR-026) and reads `user.role` fresh per
request (FR-025). No new permission mechanism is introduced.

---

## CustomerFactory — `apps/customers/factories.py`

Factory Boy is constitutionally required for test data (Principle V).

```python
class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer
        django_get_or_create = ("client_id",)

    client_id = factory.Sequence(lambda n: f"CL-{n + 90000:05d}")
    name    = factory.Faker("name")
    email   = factory.Sequence(lambda n: f"customer{n}@example.com")
    phone   = factory.Faker("phone_number")
    age     = factory.Faker("random_int", min=18, max=75)
    gender  = "Other"
    location = factory.Faker("city")
    lead_source = "Agent"
    risk_score = None
    fraud_risk_flag = None
    cross_sell_score = None
    archived_at = None

    class Params:
        archived = factory.Trait(archived_at=factory.LazyFunction(timezone.now))
        scored = factory.Trait(risk_score=Decimal("0.42"),
                               fraud_risk_flag="Low",
                               cross_sell_score=Decimal("0.75"))
```

The sequence starts at `CL-90000` so factory-made references never collide
with loaded dataset rows (`CL-00001`–`CL-03000`) in a test that uses both.
Scores default to `None`, matching an API-created customer and keeping the
FR-006 absent-vs-zero distinction visible by default rather than papered over
by a fixture.
