"""
The Claim entity and the ClaimLoadAnomaly record (FR-001 through FR-011,
FR-021, FR-041 through FR-044).

Three decisions here diverge deliberately from Policy, each covered by a
dedicated test so none is later "corrected" into consistency:

1. NO uniqueness constraint at all (FR-007). Policy needed a
   live-scoped-versus-reserved decision because (customer, policy_type) is
   a real business constraint. Claims have no natural key: two identical
   claims against one policy are legitimately distinct events, so the
   correct constraint is none, and the live-versus-reserved question is
   MOOT rather than answered either way.

2. `No Claim` is absent from ClaimStatus. The source dataset has four
   status values, but the fourth describes the ABSENCE of a claim, so it
   can never be a stored claim's status (FR-004). This is the single most
   consequential modelling decision in the feature: including it would
   make FR-004 a runtime convention any future code path could violate
   silently.

3. The amount constraint is `gte=0`, not `gt=0` -- the deliberate
   divergence from policy_premium_positive. 1,507 of 3,000 source rows
   carry exactly 0.00, so a positive-only constraint would refuse half the
   dataset. Zero is data; the column is therefore also NOT nullable, so
   zero stays distinguishable from absent (FR-011).
"""
from django.db import models

from apps.core.models import TimeStampedModel


class ClaimStatus(models.TextChoices):
    """
    Three values, not four.

    The source dataset also carries `No Claim`, which is NOT here by
    design -- see FR-004 and the module docstring. A `No Claim` submission
    fails the serializer's ChoiceField before any hand-written validator
    runs, and the claim_status_valid DB constraint catches anything that
    bypasses the serializer entirely.
    """

    APPROVED = "Approved", "Approved"
    DENIED = "Denied", "Denied"
    FILED = "Filed", "Filed"


class AnomalyStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLEARED = "cleared", "Cleared"


class ClearedReason(models.TextChoices):
    """
    The two reasons an anomaly stops holding (FR-044), stored distinctly.

    Collapsing these would let a later phase count unexplained
    disappearances as verified corrections -- the precise direction an
    anomaly signal must not err in, because it understates source
    inconsistency invisibly.
    """

    CORRECTED = "corrected", "Corrected"
    ABSENT = "absent", "Absent from latest load"


class ClaimManager(models.Manager):
    """Default manager: archived claims are invisible (FR-021)."""

    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)


class Claim(TimeStampedModel):
    policy = models.ForeignKey(
        "policies.Policy",
        on_delete=models.PROTECT,  # FR-009: a policy carrying claims cannot be destroyed
        related_name="claims",
        db_index=True,
    )

    claim_status = models.CharField(
        max_length=16, choices=ClaimStatus.choices, db_index=True
    )

    # Decimal, never float: currency needs exact representation. NOT
    # nullable, so a 0.00 amount stays distinguishable from an absent one
    # (FR-011).
    claim_amount_usd = models.DecimalField(max_digits=10, decimal_places=2)

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ClaimManager()  # declared FIRST -> stays _default_manager
    all_objects = models.Manager()

    class Meta:
        ordering = ["id"]  # FR-017: stable paging
        constraints = [
            # gte, NOT gt -- see the module docstring. This is the
            # deliberate divergence from policy_premium_positive.
            models.CheckConstraint(
                name="claim_amount_non_negative",
                condition=models.Q(claim_amount_usd__gte=0),
            ),
            # Duplicates the `choices` enforcement at the DB level on
            # purpose: choices is a serializer-layer convention that raw
            # ORM writes bypass, and FR-004's integrity is worth a
            # constraint the database itself holds.
            models.CheckConstraint(
                name="claim_status_valid",
                condition=models.Q(claim_status__in=["Approved", "Denied", "Filed"]),
            ),
        ]
        indexes = [
            models.Index(fields=["policy", "claim_status"]),
        ]
        # No UniqueConstraint and no unique_together, deliberately (FR-007).

    def __str__(self):
        return f"{self.claim_status} claim of {self.claim_amount_usd} on policy {self.policy_id}"

    @property
    def is_archived(self):
        return self.archived_at is not None


class ClaimLoadAnomaly(models.Model):
    """
    A retained observation that a source row contradicted itself -- a status
    denying a claim alongside a non-zero amount (FR-041, FR-042).

    NOT a claim, and never evidence that one occurred. This record exists so
    the signal outlives the load without any claim being fabricated: the
    source file is supplied at run time and not committed, so a mismatch
    that lives only in the file is unavailable to the later Fraud and
    Behavior phases that are its actual consumers.

    Deliberately NOT an AuditLog entry: that table is append-only by design,
    so 390 fresh rows per load would make a Phase 4 count wrong by the
    number of times the loader had been run. This table is current,
    reconciled state; AuditLog remains the immutable history alongside it.
    """

    # FK with unique=True rather than OneToOneField: the DB constraint is
    # identical, but the plural related_name keeps the reverse accessor a
    # queryset. data-model.md specifies it this way so that if a future
    # export carries two anomalous claims per policy, relaxing the
    # constraint is a migration rather than an API change for every caller.
    policy = models.ForeignKey(
        "policies.Policy",
        on_delete=models.PROTECT,
        related_name="claim_load_anomalies",
        unique=True,  # the idempotency key (FR-043)
    )

    # Free text, NOT constrained to ClaimStatus: this is a QUOTATION of the
    # source, and what the source said is `No Claim` -- a value the Claim
    # model refuses to represent at all. Constraining it would make this
    # record unable to hold its own subject.
    source_status = models.CharField(max_length=16)
    source_amount_usd = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=8,
        choices=AnomalyStatus.choices,
        default=AnomalyStatus.OPEN,
        db_index=True,
    )

    # Null while open. There is no reasonless clearing (FR-044a): a
    # consumer counting confirmed corrections filters cleared_reason=
    # "corrected", and an `absent` row can never be mistaken for one.
    cleared_reason = models.CharField(
        max_length=16, choices=ClearedReason.choices, null=True, blank=True
    )
    cleared_at = models.DateTimeField(null=True, blank=True)

    first_observed_at = models.DateTimeField()
    last_observed_at = models.DateTimeField()
    source_file = models.CharField(max_length=512)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "claim load anomalies"
        indexes = [
            # Serves the query FR-044a exists for: "every confirmed
            # correction" and "every current anomaly" are both single-index
            # lookups.
            models.Index(fields=["status", "cleared_reason"]),
        ]
        # No cleared_count, no history JSON -- see data-model.md, "A
        # deliberate non-field". History belongs in the append-only table
        # built for it, not in a second mutable copy that would drift.

    def __str__(self):
        return f"{self.status} anomaly on policy {self.policy_id} ({self.source_status})"
