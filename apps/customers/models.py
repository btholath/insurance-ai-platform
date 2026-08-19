"""
The Customer entity (FR-001 through FR-008, FR-020, FR-021, FR-044).

Two design decisions are load-bearing and easy to regress, so both are
documented here and covered by dedicated tests in tests/test_models.py:

1. Dual managers. `objects` hides archived rows; `all_objects` does not.
   `all_objects` is not a convenience accessor -- FR-021 is unsatisfiable
   without it. The CSV loader matches on client_id to decide create-vs-
   update, and if that lookup ran through `objects` it would not see an
   archived row, would conclude the reference was free, and would hit the
   unique constraint on a record it cannot query. `objects` is declared
   first so it stays _default_manager, which is what related-object
   traversal uses -- that keeps archived customers from surfacing through
   a future `policy.customer` access without Policy knowing archival
   exists.

2. Reference generation orders on the numeric suffix, not the raw string.
   See generate_client_id().
"""
from django.db import IntegrityError, models, transaction
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr

from apps.core.models import TimeStampedModel


class Gender(models.TextChoices):
    MALE = "Male", "Male"
    FEMALE = "Female", "Female"
    OTHER = "Other", "Other"


class LeadSource(models.TextChoices):
    AGENT = "Agent", "Agent"
    REFERRAL = "Referral", "Referral"
    SOCIAL_MEDIA = "Social Media", "Social Media"
    WEB = "Web", "Web"


class FraudRiskFlag(models.TextChoices):
    """
    Three levels, not a boolean, despite the "flag" name. The name is
    carried over from the source column Fraud_Risk_Flag deliberately;
    renaming is a Phase 5 concern.
    """

    LOW = "Low", "Low"
    MEDIUM = "Medium", "Medium"
    HIGH = "High", "High"


CLIENT_ID_PREFIX = "CL-"
CLIENT_ID_DIGITS = 5


class CustomerManager(models.Manager):
    """Default manager: archived customers are invisible (FR-020)."""

    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)

    def create_with_reference(self, **fields):
        """
        Create a customer, generating client_id when absent (FR-005).

        Runs the generation and the insert in one transaction so the
        SELECT ... FOR UPDATE actually guards the read-modify-write.
        """
        if fields.get("client_id"):
            return self.create(**fields)

        with transaction.atomic():
            fields["client_id"] = generate_client_id()
            try:
                return self.create(**fields)
            except IntegrityError:
                pass

        # One retry. The lock cannot cover the empty-table case (there is
        # no row to lock), so two concurrent first-creates can both compute
        # CL-00001; the unique constraint rejects the loser and this retry
        # resolves it.
        with transaction.atomic():
            fields["client_id"] = generate_client_id()
            return self.create(**fields)


def generate_client_id():
    """
    Next reference in the CL-##### sequence, continuing from the highest
    existing one including archived records (FR-021).

    Ordering is on the extracted numeric suffix rather than the raw string.
    `order_by("-client_id")` is a lexicographic sort on a CharField and is
    correct only while every reference is exactly five digits -- at
    CL-100000, "CL-99999" still sorts higher and the generator begins
    reissuing live references, each rejected by the unique constraint until
    the retry is exhausted. The failure is data-dependent and would not
    appear in any test built on the 3,000-row dataset.
    """
    highest = (
        Customer.all_objects.select_for_update()
        .annotate(numeric_ref=Cast(Substr("client_id", len(CLIENT_ID_PREFIX) + 1), IntegerField()))
        .order_by("-numeric_ref")
        .values_list("numeric_ref", flat=True)
        .first()
    )
    return f"{CLIENT_ID_PREFIX}{(highest or 0) + 1:0{CLIENT_ID_DIGITS}d}"


class Customer(TimeStampedModel):
    client_id = models.CharField(max_length=16, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    email = models.EmailField(max_length=254, db_index=True)  # deliberately NOT unique (FR-004)
    phone = models.CharField(max_length=64)  # stored as supplied, never normalized
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=16, choices=Gender.choices)
    location = models.CharField(max_length=255)
    lead_source = models.CharField(max_length=32, choices=LeadSource.choices)

    # Denormalised mirror of RiskAssessment.score (score / 100), written
    # only by the risk engine (apps/risk/engine.py persist()) -- Phase 3
    # has arrived, and RiskAssessment is now the record of truth, not this
    # field. Read-only at the API layer (CustomerSerializer) and no
    # longer populated by the CSV loader (FR-055, FR-056, FR-057). Kept
    # here for query convenience (e.g. filtering customers by score
    # without a join), not as a second source of truth.
    #
    # null=True with no blank-driven empty-string path, so a customer with
    # no assessment yet is None and never 0 (FR-006).
    risk_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    # Stored only. Nothing in this feature computes, derives, or interprets
    # these -- that is Phase 5 (Fraud) work (FR-007).
    fraud_risk_flag = models.CharField(max_length=16, choices=FraudRiskFlag.choices, null=True, blank=True)
    cross_sell_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = CustomerManager()  # declared FIRST -> stays _default_manager
    all_objects = models.Manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                name="customer_age_valid",
                condition=models.Q(age__gte=18) & models.Q(age__lte=120),
            ),
            # The isnull disjunction is required: without it a NULL score
            # makes the comparison SQL-NULL rather than true, and Postgres
            # would reject every customer created without a score.
            models.CheckConstraint(
                name="customer_risk_score_range",
                condition=models.Q(risk_score__isnull=True)
                | (models.Q(risk_score__gte=0) & models.Q(risk_score__lte=1)),
            ),
            models.CheckConstraint(
                name="customer_cross_sell_score_range",
                condition=models.Q(cross_sell_score__isnull=True)
                | (models.Q(cross_sell_score__gte=0) & models.Q(cross_sell_score__lte=1)),
            ),
        ]
        indexes = [
            models.Index(fields=["lead_source"]),
            models.Index(fields=["fraud_risk_flag"]),
        ]

    def __str__(self):
        return f"{self.client_id} {self.name}"

    @property
    def is_archived(self):
        return self.archived_at is not None
