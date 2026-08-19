"""
View tests for the assessment read routes (T029-T031, FR-019, FR-024,
FR-029) and the recompute action (T060-T063, FR-034, FR-018).

Written before views.py exists -- must FAIL until T036-T039 (US1) and
T064-T065 (US3) land. Role-sweep permission tests live in
test_permissions.py; these use Risk Manager throughout as a role known to
be permitted for every route under test.
"""
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from ..factories import RiskAssessmentFactory, RiskFactorFactory
from ..models import RiskAssessment, RiskFactor, RiskTier

pytestmark = pytest.mark.django_db

URL = "/api/risk/assessments/"
READER = Role.RISK_MANAGER
WRITER = Role.RISK_MANAGER


def full_assessment(**overrides):
    assessment = RiskAssessmentFactory(**overrides)
    for factor in ("age", "policy_type", "claims_history", "claims_ratio", "denied_claim"):
        RiskFactorFactory(assessment=assessment, factor=factor)
    return assessment


class TestRetrieveByIdAndByCustomer:
    def test_retrieve_by_id_returns_score_tier_and_factors(self, authenticated_client):
        client, _ = authenticated_client(READER)
        assessment = full_assessment(score=65, tier=RiskTier.HIGH)

        response = client.get(f"{URL}{assessment.id}/")

        assert response.status_code == 200
        assert response.data["score"] == 65
        assert response.data["tier"] == "high"
        assert len(response.data["factors"]) == 5

    def test_retrieve_by_customer(self, authenticated_client):
        client, _ = authenticated_client(READER)
        assessment = full_assessment()

        response = client.get(f"{URL}by-customer/{assessment.customer_id}/")

        assert response.status_code == 200
        assert response.data["id"] == assessment.id
        assert len(response.data["factors"]) == 5

    def test_by_customer_for_unassessed_customer_is_404_with_distinguishing_body(
        self, authenticated_client
    ):
        client, _ = authenticated_client(READER)
        customer = CustomerFactory()

        response = client.get(f"{URL}by-customer/{customer.id}/")

        assert response.status_code == 404
        assert response.data["detail"] == "This customer has not been assessed."


class TestNoRouteOmitsFactors:
    def test_list_route_carries_factors(self, authenticated_client):
        client, _ = authenticated_client(READER)
        full_assessment()
        full_assessment()

        response = client.get(URL)

        assert response.status_code == 200
        for row in response.data["results"]:
            assert len(row["factors"]) == 5


class TestFilters:
    def test_filter_by_tier(self, authenticated_client):
        client, _ = authenticated_client(READER)
        full_assessment(tier=RiskTier.LOW, score=5)
        full_assessment(tier=RiskTier.HIGH, score=80)

        response = client.get(URL, {"tier": "high"})

        assert response.data["count"] == 1
        assert response.data["results"][0]["tier"] == "high"

    def test_filter_by_customer(self, authenticated_client):
        client, _ = authenticated_client(READER)
        assessment = full_assessment()
        full_assessment()

        response = client.get(URL, {"customer": assessment.customer_id})

        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == assessment.id

    def test_filter_by_min_and_max_score(self, authenticated_client):
        client, _ = authenticated_client(READER)
        full_assessment(score=10)
        full_assessment(score=50)
        full_assessment(score=90)

        response = client.get(URL, {"min_score": 20, "max_score": 80})

        assert response.data["count"] == 1
        assert response.data["results"][0]["score"] == 50


class TestRecompute:
    def _customer_with_data(self):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
        ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
        return customer

    def test_recompute_scores_current_data(self, authenticated_client):
        client, _ = authenticated_client(WRITER)
        customer = self._customer_with_data()

        response = client.post(f"{URL}recompute/", {"customer": customer.id}, format="json")

        assert response.status_code == 200
        assert response.data["score"] >= 0
        assert len(response.data["factors"]) == 5

    def test_recompute_touches_only_the_named_customer(self, authenticated_client):
        client, _ = authenticated_client(WRITER)
        target = self._customer_with_data()
        other = full_assessment()
        other_score = other.score
        other_computed_at = other.computed_at

        client.post(f"{URL}recompute/", {"customer": target.id}, format="json")

        other.refresh_from_db()
        assert other.score == other_score
        assert other.computed_at == other_computed_at

    def test_recompute_creates_assessment_when_none_existed(self, authenticated_client):
        client, _ = authenticated_client(WRITER)
        customer = self._customer_with_data()
        assert not RiskAssessment.objects.filter(customer=customer).exists()

        response = client.post(f"{URL}recompute/", {"customer": customer.id}, format="json")

        assert response.status_code == 200
        assert RiskAssessment.objects.filter(customer=customer).exists()

    def test_recompute_for_unscoreable_customer_returns_422(self, authenticated_client):
        client, _ = authenticated_client(WRITER)
        customer = CustomerFactory()  # no live policy

        response = client.post(f"{URL}recompute/", {"customer": customer.id}, format="json")

        assert response.status_code == 422
        assert "detail" in response.data
