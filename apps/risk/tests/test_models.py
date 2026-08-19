"""
Model tests for RiskAssessment and RiskFactor (T015-T017).

Written before models.py exists -- these must FAIL until T018-T021 land.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.customers.factories import CustomerFactory

from ..models import FactorStatus, RiskAssessment, RiskFactor, RiskFactorName, RiskTier
from ..rules import FactorStatus as RulesFactorStatus

pytestmark = pytest.mark.django_db


def make_assessment(**overrides):
    fields = dict(
        customer=CustomerFactory(),
        score=42,
        tier=RiskTier.ELEVATED,
        rule_set_version="1.0.0",
        computed_at=timezone.now(),
        computed_by=None,
    )
    fields.update(overrides)
    return RiskAssessment.objects.create(**fields)


def make_factor(assessment, **overrides):
    fields = dict(
        assessment=assessment,
        factor=RiskFactorName.AGE,
        status=FactorStatus.EVALUATED,
        observed_value="23",
        band_label="under 25",
        points=15,
        unevaluable_reason="",
    )
    fields.update(overrides)
    return RiskFactor.objects.create(**fields)


class TestRiskAssessmentShape:
    def test_field_shape_round_trips(self):
        assessment = make_assessment(score=65, tier=RiskTier.HIGH)
        assessment.refresh_from_db()

        assert assessment.score == 65
        assert assessment.tier == RiskTier.HIGH
        assert assessment.rule_set_version == "1.0.0"
        assert assessment.computed_at is not None
        assert assessment.computed_by is None

    def test_ordering_is_by_id(self):
        assert RiskAssessment._meta.ordering == ["id"]

    def test_computed_at_is_not_auto_now(self):
        """FR-027: computed_at means 'when scored', not 'when last touched'."""
        field = RiskAssessment._meta.get_field("computed_at")
        assert field.auto_now is False
        assert field.auto_now_add is False

    def test_score_below_zero_is_rejected(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_assessment(score=-1)

    def test_score_above_100_is_rejected(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_assessment(score=101)

    def test_score_at_boundaries_is_accepted(self):
        make_assessment(score=0, customer=CustomerFactory())
        make_assessment(score=100, customer=CustomerFactory())

    def test_invalid_tier_is_rejected(self):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_assessment(tier="not_a_tier")


class TestRiskFactorShape:
    def test_field_shape_round_trips(self):
        assessment = make_assessment()
        factor = make_factor(assessment, points=15)
        factor.refresh_from_db()

        assert factor.assessment_id == assessment.id
        assert factor.factor == RiskFactorName.AGE
        assert factor.status == FactorStatus.EVALUATED
        assert factor.points == 15

    def test_ordering_is_by_id(self):
        assert RiskFactor._meta.ordering == ["id"]

    def test_str_representation(self):
        assessment = make_assessment()
        factor = make_factor(assessment, factor=RiskFactorName.AGE, points=15)
        assert str(factor) == f"age=15 on assessment {assessment.id}"

    def test_unique_constraint_on_assessment_and_factor(self):
        assessment = make_assessment()
        make_factor(assessment, factor=RiskFactorName.AGE)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_factor(assessment, factor=RiskFactorName.AGE)

    def test_same_factor_allowed_across_different_assessments(self):
        a1 = make_assessment()
        a2 = make_assessment(customer=CustomerFactory())

        make_factor(a1, factor=RiskFactorName.AGE)
        make_factor(a2, factor=RiskFactorName.AGE)  # must not raise

    def test_not_evaluable_without_reason_is_rejected(self):
        """FR-023: a not_evaluable row must carry its reason -- DB enforced."""
        assessment = make_assessment()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_factor(
                    assessment,
                    status=FactorStatus.NOT_EVALUABLE,
                    unevaluable_reason="",
                )

    def test_evaluated_with_reason_is_rejected(self):
        """An evaluated row must NOT carry a spurious reason -- DB enforced."""
        assessment = make_assessment()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_factor(
                    assessment,
                    status=FactorStatus.EVALUATED,
                    unevaluable_reason="should not be here",
                )

    def test_not_evaluable_with_reason_is_accepted(self):
        assessment = make_assessment()
        factor = make_factor(
            assessment,
            status=FactorStatus.NOT_EVALUABLE,
            unevaluable_reason="Customer holds no live policy",
            points=0,
            observed_value="",
            band_label="not evaluable",
        )
        assert factor.status == FactorStatus.NOT_EVALUABLE

    def test_negative_points_rejected(self):
        assessment = make_assessment()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_factor(assessment, points=-1)


class TestRiskAssessmentCustomerIsOneToOne:
    def test_second_assessment_for_same_customer_is_rejected(self):
        """The basis of FR-033's idempotency: one assessment per customer."""
        customer = CustomerFactory()
        make_assessment(customer=customer)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make_assessment(customer=customer)


def test_factor_status_values_match_the_rules_module():
    """
    rules.FactorStatus is a deliberate Django-free duplicate of this
    model's FactorStatus (see rules.py docstring) -- string equality keeps
    them in step without an import that would drag the ORM into rules.py.
    """
    assert FactorStatus.EVALUATED == RulesFactorStatus.EVALUATED
    assert FactorStatus.NOT_EVALUABLE == RulesFactorStatus.NOT_EVALUABLE
