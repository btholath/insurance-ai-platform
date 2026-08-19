"""
Staleness tests (T066-T069; FR-038, FR-039, FR-040, SC-012).

No stored flag -- derived on read by comparing computed_at against the
customer's and their live policies'/claims' updated_at (research §4).
Written before the derivation exists on the serializer -- must FAIL until
T070-T071 land.
"""
from decimal import Decimal

import pytest

from apps.claims.factories import ClaimFactory
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from .. import engine
from ..serializers import RiskAssessmentSerializer

pytestmark = pytest.mark.django_db


def scoreable_customer():
    customer = CustomerFactory(age=22)
    policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
    return customer, policy


class TestFreshAssessment:
    def test_freshly_computed_assessment_is_not_stale(self):
        customer, _ = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)

        data = RiskAssessmentSerializer(assessment).data

        assert data["is_stale"] is False
        assert data["computed_at"] is not None
        assert "stale_reason" not in data or not data.get("stale_reason")


class TestBecomesStale:
    def test_stale_when_customer_changes(self):
        customer, _ = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)

        customer.name = "Changed Name"
        customer.save()

        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is True
        assert data["stale_reason"]

    def test_stale_when_live_policy_changes(self):
        customer, policy = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)

        policy.premium_usd = Decimal("2000.00")
        policy.save()

        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is True

    def test_stale_when_live_claim_changes(self):
        customer, policy = scoreable_customer()
        claim = ClaimFactory(policy=policy)
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)

        claim.claim_amount_usd = Decimal("999.00")
        claim.save()

        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is True


class TestStaleStillReturnsStoredData:
    def test_stale_assessment_still_returns_score_and_factors_unrecomputed(self):
        customer, _ = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)
        original_score = assessment.score

        customer.name = "Changed Name"
        customer.save()

        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is True
        assert data["score"] == original_score
        assessment.refresh_from_db()
        assert assessment.score == original_score  # reading never recomputes


class TestOverReportingIsSafe:
    """
    research §4: a field no factor reads (e.g. phone) still marks the
    assessment stale. Documented over-reporting, not a bug.
    """

    def test_unrelated_field_change_still_marks_stale(self):
        customer, _ = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)

        customer.phone = "+1-555-0100"
        customer.save()

        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is True
