"""
Signal-wiring tests for automatic risk recompute (T011, T018-T022;
data-model.md's trigger table).

All tests here run under eager mode (config/settings/test.py), so
`.delay()` executes synchronously once its `transaction.on_commit()`
callback actually fires. It does NOT fire on its own inside a normal
`pytest.mark.django_db` test: pytest-django wraps each test in an outer
transaction that is rolled back, never committed, so on_commit callbacks
registered inside it are simply discarded, not deferred. The
`django_capture_on_commit_callbacks` fixture (pytest-django >=4.4) exists
for exactly this -- it runs any callbacks registered inside its `with`
block as if that block's transaction had committed, without requiring a
real (slower) `TransactionTestCase`/`transactional_db`. This is the
project's first signals-based feature, so this pattern has no earlier
precedent in the codebase to follow.
"""
from decimal import Decimal

import pytest

from apps.claims.factories import ClaimFactory
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from .. import engine
from ..factories import RiskAssessmentFactory
from ..models import RiskAssessment
from ..serializers import RiskAssessmentSerializer

pytestmark = pytest.mark.django_db


class TestCustomerSaveEnqueuesRecompute:
    """FR-003: saving a Customer with an existing assessment recomputes it."""

    def test_customer_save_triggers_recompute_for_that_customer(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            customer.age = 60
            customer.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at


class TestPolicySaveEnqueuesRecompute:
    """FR-003: saving a Policy recomputes its owning customer."""

    def test_policy_save_triggers_recompute_for_its_customer(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer)
        original_computed_at = assessment.computed_at
        policy = PolicyFactory(customer=customer, premium_usd=Decimal("500.00"))
        assessment.refresh_from_db()
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            policy.premium_usd = Decimal("9000.00")
            policy.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at


class TestClaimSaveEnqueuesRecompute:
    """FR-003: saving a Claim recomputes the customer via claim.policy.customer_id."""

    def test_claim_save_triggers_recompute_for_the_policys_customer(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, premium_usd=Decimal("500.00"))
        assessment = RiskAssessmentFactory(customer=customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            ClaimFactory(policy=policy, claim_amount_usd=Decimal("100.00"))

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at


class TestPolicyUpdateReflectsInScore:
    """Acceptance Scenario 1: a premium change is reflected in the recomputed score."""

    def test_policy_premium_change_updates_score_and_tier(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("100.00"))
        RiskAssessmentFactory(customer=customer)

        with django_capture_on_commit_callbacks(execute=True):
            policy.premium_usd = Decimal("50000.00")
            policy.save()

        assessment = RiskAssessment.objects.get(customer=customer)
        expected = engine.score_customer(customer)
        assert assessment.score == expected.score
        assert assessment.tier == expected.tier


class TestNewClaimTriggersRecompute:
    """Acceptance Scenario 2: a new claim against a live policy recomputes."""

    def test_new_claim_on_live_policy_recomputes_already_assessed_customer(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, premium_usd=Decimal("1000.00"))
        assessment = RiskAssessmentFactory(customer=customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            ClaimFactory(policy=policy, claim_amount_usd=Decimal("2000.00"))

        assessment.refresh_from_db()
        expected = engine.score_customer(customer)
        assert assessment.computed_at > original_computed_at
        assert assessment.score == expected.score
        assert assessment.tier == expected.tier


class TestCustomerFieldChangeTriggersRecompute:
    """Acceptance Scenario 3: a Customer field change (age) recomputes."""

    def test_customer_age_change_triggers_recompute(self, django_capture_on_commit_callbacks):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            customer.age = 70
            customer.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at


class TestIrrelevantFieldChangeStillTriggers:
    """
    FR-004, Acceptance Scenario 4: over-triggering is deliberate -- a field
    change no scoring factor reads still advances computed_at even though
    score/tier are unchanged.
    """

    def test_customer_phone_change_still_advances_computed_at(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer)
        expected = engine.score_customer(customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            customer.phone = "555-000-0000"
            customer.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at
        assert assessment.score == expected.score
        assert assessment.tier == expected.tier

    def test_policy_renewal_probability_change_still_advances_computed_at(
        self, django_capture_on_commit_callbacks
    ):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, premium_usd=Decimal("500.00"))
        assessment = RiskAssessmentFactory(customer=customer)
        expected = engine.score_customer(customer)
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            policy.renewal_probability = Decimal("0.42")
            policy.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at
        assert assessment.score == expected.score


class TestIsStaleFalseAfterAutomaticRecompute:
    """Independent Test criterion: is_stale reads false immediately after recompute."""

    def test_is_stale_false_after_automatic_recompute(self, django_capture_on_commit_callbacks):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer)

        with django_capture_on_commit_callbacks(execute=True):
            customer.age = 55
            customer.save()

        assessment.refresh_from_db()
        data = RiskAssessmentSerializer(assessment).data
        assert data["is_stale"] is False
