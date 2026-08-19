"""
Serializer tests for the assessment read shape (T028, FR-020, FR-025, FR-026).

Written before serializers.py exists -- must FAIL until T034-T035 land.
"""
import pytest

from apps.accounts.factories import UserFactory

from ..factories import RiskAssessmentFactory, RiskFactorFactory
from ..models import RiskFactorName, RiskTier
from ..serializers import RiskAssessmentSerializer, RiskFactorSerializer

pytestmark = pytest.mark.django_db


class TestRiskFactorSerializer:
    def test_evaluated_factor_shape(self):
        factor = RiskFactorFactory(
            factor=RiskFactorName.AGE, band_label="under 25", points=15, observed_value="23"
        )

        data = RiskFactorSerializer(factor).data

        assert data["factor"] == "age"
        assert data["factor_label"] == "Customer age"
        assert data["status"] == "evaluated"
        assert data["observed_value"] == "23"
        assert data["band_label"] == "under 25"
        assert data["points"] == 15

    def test_not_evaluable_factor_carries_reason(self):
        factor = RiskFactorFactory(not_evaluable=True)

        data = RiskFactorSerializer(factor).data

        assert data["status"] == "not_evaluable"
        assert data["unevaluable_reason"]


class TestRiskAssessmentSerializer:
    def test_nested_factors_present(self):
        assessment = RiskAssessmentFactory(score=30, tier=RiskTier.MODERATE)
        RiskFactorFactory(assessment=assessment, factor=RiskFactorName.AGE)
        RiskFactorFactory(assessment=assessment, factor=RiskFactorName.POLICY_TYPE)

        data = RiskAssessmentSerializer(assessment).data

        assert len(data["factors"]) == 2
        assert data["tier_label"] == "Moderate"
        assert data["rule_set_version"] == "1.0.0"

    def test_client_id_is_the_customers_reference(self):
        assessment = RiskAssessmentFactory()

        data = RiskAssessmentSerializer(assessment).data

        assert data["client_id"] == assessment.customer.client_id

    def test_computed_by_serializes_as_email(self):
        user = UserFactory(email="risk.manager@example.com")
        assessment = RiskAssessmentFactory(computed_by=user)

        data = RiskAssessmentSerializer(assessment).data

        assert data["computed_by"] == "risk.manager@example.com"

    def test_computed_by_null_when_unattended(self):
        assessment = RiskAssessmentFactory(computed_by=None)

        data = RiskAssessmentSerializer(assessment).data

        assert data["computed_by"] is None

    def test_explanation_readable_without_reference_to_code(self):
        """FR-025: labels, not raw codes, describe every factor."""
        assessment = RiskAssessmentFactory()
        RiskFactorFactory(assessment=assessment, factor=RiskFactorName.CLAIMS_RATIO)

        data = RiskAssessmentSerializer(assessment).data
        factor_row = data["factors"][0]

        assert factor_row["factor_label"] == "Claims-to-premium ratio"
