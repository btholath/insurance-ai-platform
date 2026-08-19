import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.customers.factories import CustomerFactory

from .models import FactorStatus, RiskAssessment, RiskFactor, RiskFactorName, RiskTier


class RiskAssessmentFactory(DjangoModelFactory):
    class Meta:
        model = RiskAssessment
        skip_postgeneration_save = True

    # SubFactory: a test needing several assessments must pass customer=
    # explicitly, since RiskAssessment.customer is one-to-one and a second
    # factory call against the same customer would violate that constraint.
    customer = factory.SubFactory(CustomerFactory)

    score = 42
    tier = RiskTier.ELEVATED
    rule_set_version = "1.0.0"
    computed_at = factory.LazyFunction(timezone.now)
    computed_by = None


class RiskFactorFactory(DjangoModelFactory):
    class Meta:
        model = RiskFactor
        skip_postgeneration_save = True

    assessment = factory.SubFactory(RiskAssessmentFactory)

    factor = RiskFactorName.AGE
    status = FactorStatus.EVALUATED
    observed_value = "23"
    band_label = "under 25"
    points = 15
    unevaluable_reason = ""

    class Params:
        not_evaluable = factory.Trait(
            status=FactorStatus.NOT_EVALUABLE,
            observed_value="",
            band_label="not evaluable",
            points=0,
            unevaluable_reason="Customer holds no live policy",
        )
