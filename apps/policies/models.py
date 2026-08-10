"""
The Policy entity (FR-001 through FR-008, FR-021).

Two decisions here diverge deliberately from the Customer model. Both are
covered by dedicated tests so neither is later "corrected" into
consistency:

1. Uniqueness on (customer, policy_type) is scoped to LIVE rows only.
   Customer reserves an archived client_id forever, because FR-021 there
   requires the reference stay reserved. Here the opposite is required:
   archiving a customer's auto policy must not make auto cover permanently
   impossible for them. Same mechanism, opposite requirement.

2. There is no external reference field. Customer stores the source
   dataset's client_id because it is the idempotency key; the dataset
   carries no policy identifier at all, so the loader matches on
   (customer, policy_type) instead and the internal PK is the stable
   identifier Claims will reference (FR-007).
"""
from django.db import models

from apps.core.models import TimeStampedModel


class PolicyType(models.TextChoices):
    LIFE = "Life", "Life"
    AUTO = "Auto", "Auto"
    PROPERTY = "Property", "Property"
    HEALTH = "Health", "Health"


class PolicyManager(models.Manager):
    """Default manager: archived policies are invisible (FR-021)."""

    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)


class Policy(TimeStampedModel):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,  # never let a hard delete destroy policy history
        related_name="policies",
    )

    policy_type = models.CharField(max_length=16, choices=PolicyType.choices, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField(db_index=True)

    # Decimal, never float: currency needs exact representation, and the
    # source carries two decimal places. Width allows 99,999,999.99 -- far
    # above this consumer sample, because widening later is a table rewrite.
    premium_usd = models.DecimalField(max_digits=10, decimal_places=2)

    # Stored only. Nothing here computes or interprets it (FR-005) -- that
    # is Phase 5 work. null=True so an absent value stays distinguishable
    # from a genuine 0.00, of which the source dataset has 13.
    renewal_probability = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = PolicyManager()  # declared FIRST -> stays _default_manager
    all_objects = models.Manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                name="policy_end_after_start",
                condition=models.Q(end_date__gt=models.F("start_date")),
            ),
            models.CheckConstraint(
                name="policy_premium_positive",
                condition=models.Q(premium_usd__gt=0),
            ),
            # The isnull disjunction is required: without it a NULL makes
            # the comparison SQL-NULL rather than true, and Postgres would
            # reject every policy created without a renewal probability --
            # which is every policy created through the API.
            models.CheckConstraint(
                name="policy_renewal_probability_range",
                condition=models.Q(renewal_probability__isnull=True)
                | (
                    models.Q(renewal_probability__gte=0)
                    & models.Q(renewal_probability__lte=1)
                ),
            ),
            # Scoped to live rows: archival releases the coverage slot.
            models.UniqueConstraint(
                fields=["customer", "policy_type"],
                condition=models.Q(archived_at__isnull=True),
                name="policy_unique_live_type_per_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "policy_type"]),
        ]

    def __str__(self):
        return f"{self.policy_type} policy for {self.customer.client_id}"

    @property
    def is_archived(self):
        return self.archived_at is not None

    # No has_expired property: expiry is a queryset-level filter (FR-020,
    # PolicyViewSet.get_queryset) comparing end_date to today in SQL, so a
    # Python-side mirror of the same rule would be a second definition
    # nothing calls. Expiry is derived per request and never stored -- a
    # stored flag would be wrong the day after it was written unless
    # something maintained it, and that job's failure mode is silently
    # stale data.
