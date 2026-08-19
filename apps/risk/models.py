"""
RiskAssessment and RiskFactor (T018-T021; data-model.md).

RiskAssessment is one per customer -- the current computed risk and the
record of truth (FR-024). RiskFactor rows are its explanation: exactly
five per assessment, always (FR-022, FR-023), never fewer.

`on_delete=CASCADE` on RiskFactor.assessment is the one deliberate cascade
in this feature, against the platform's PROTECT habit: a factor row has no
meaning apart from its assessment (data-model.md). Everything else here
follows the PROTECT/SET_NULL conventions apps.claims and apps.policies
already established.
"""
from django.db import models

from apps.core.models import TimeStampedModel


class RiskTier(models.TextChoices):
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    ELEVATED = "elevated", "Elevated"
    HIGH = "high", "High"


class RiskFactorName(models.TextChoices):
    AGE = "age", "Customer age"
    POLICY_TYPE = "policy_type", "Policy coverage type"
    CLAIMS_HISTORY = "claims_history", "Claims history"
    CLAIMS_RATIO = "claims_ratio", "Claims-to-premium ratio"
    DENIED_CLAIM = "denied_claim", "Denied claim present"


class FactorStatus(models.TextChoices):
    """
    Mirrors rules.FactorStatus by value (see that module's docstring).
    `test_factor_status_values_match_the_rules_module` in test_models.py
    pins the two in step by string equality.
    """

    EVALUATED = "evaluated", "Evaluated"
    NOT_EVALUABLE = "not_evaluable", "Not evaluable"


class RiskAssessment(TimeStampedModel):
    # OneToOne, PROTECT: one current assessment per customer (basis of
    # FR-033's idempotency); a customer carrying an assessment cannot be
    # hard-deleted, matching Policy -> Customer.
    customer = models.OneToOneField(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="risk_assessment",
    )

    score = models.PositiveSmallIntegerField()
    tier = models.CharField(max_length=16, choices=RiskTier.choices, db_index=True)

    # FR-004, FR-026: the rule set in force when this row was computed.
    rule_set_version = models.CharField(max_length=16, db_index=True)

    # Explicitly set by the engine, NOT auto_now (FR-027) -- this means
    # "when this score was computed", not "when this row was last touched".
    computed_at = models.DateTimeField()

    # Null when the batch command runs unattended; SET_NULL so removing a
    # user never destroys the assessment.
    computed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="risk_assessments_computed",
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                name="risk_score_range",
                condition=models.Q(score__gte=0) & models.Q(score__lte=100),
            ),
            # Duplicates `choices` at the DB level deliberately, following
            # claim_status_valid -- choices is a serializer-layer
            # convention that raw ORM writes bypass.
            models.CheckConstraint(
                name="risk_tier_valid",
                condition=models.Q(
                    tier__in=[RiskTier.LOW, RiskTier.MODERATE, RiskTier.ELEVATED, RiskTier.HIGH]
                ),
            ),
        ]
        indexes = [
            # Serves "show me the high-risk book, worst first" (data-model.md).
            models.Index(fields=["tier", "score"]),
        ]

    def __str__(self):
        return f"{self.tier} ({self.score}) for customer {self.customer_id}"


class RiskFactor(TimeStampedModel):
    assessment = models.ForeignKey(
        RiskAssessment,
        on_delete=models.CASCADE,  # deliberate -- see module docstring
        related_name="factors",
    )

    factor = models.CharField(max_length=16, choices=RiskFactorName.choices, db_index=True)
    status = models.CharField(max_length=16, choices=FactorStatus.choices)

    # Text, not typed: the five factors have incompatible types and this
    # field exists to be shown (FR-020, FR-025), not computed on.
    observed_value = models.CharField(max_length=64, blank=True)
    band_label = models.CharField(max_length=64)

    # SmallIntegerField rather than positive: all bands in rule set 1.0.0
    # are non-negative, but a future version may express a risk-reducing
    # band without a migration. factor_points_non_negative keeps 1.0.0
    # honest at the DB layer.
    points = models.SmallIntegerField()

    # FR-023: non-empty iff status="not_evaluable" -- enforced below.
    unevaluable_reason = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            # A duplicated factor would double-count in FR-021's sum while
            # looking correct in the response.
            models.UniqueConstraint(
                fields=["assessment", "factor"],
                name="risk_factor_unique_per_assessment",
            ),
            models.CheckConstraint(
                name="factor_reason_matches_status",
                condition=(
                    models.Q(status=FactorStatus.NOT_EVALUABLE)
                    & ~models.Q(unevaluable_reason="")
                )
                | (
                    models.Q(status=FactorStatus.EVALUATED)
                    & models.Q(unevaluable_reason="")
                ),
            ),
            models.CheckConstraint(
                name="factor_points_non_negative",
                condition=models.Q(points__gte=0),
            ),
        ]
        indexes = [
            # Serves "which customers were penalised for a high claims
            # ratio" (data-model.md §3).
            models.Index(fields=["factor", "points"]),
        ]

    def __str__(self):
        return f"{self.factor}={self.points} on assessment {self.assessment_id}"
