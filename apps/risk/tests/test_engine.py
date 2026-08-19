"""
Engine tests: the sum invariant, five-factor completeness, the
not-evaluable path, and determinism (T024-T027, FR-021, FR-022, FR-023,
FR-002).

Written before engine.py exists -- must FAIL until T032-T033 land.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from .. import engine
from ..models import FactorStatus, RiskAssessment, RiskFactor, RiskFactorName
from ..rules import FACTORS

pytestmark = pytest.mark.django_db


def young_auto_customer():
    """Under-25, one live Auto policy, one non-zero claim -- every factor evaluable."""
    customer = CustomerFactory(age=22)
    policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
    ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
    return customer


class TestSumInvariant:
    """FR-021, SC-001: sum(factor.points) == assessment.score, always."""

    @pytest.mark.parametrize(
        "build",
        [
            young_auto_customer,
            lambda: CustomerFactory(age=40),  # no policy at all
            lambda: _mid_age_with_policy_no_claims(),
            lambda: _customer_with_denied_zero_claim(),
        ],
    )
    def test_sum_of_factor_points_equals_score(self, build):
        customer = build()
        result = engine.score_customer(customer)

        assert sum(f.points for f in result.factors) == result.score


def _mid_age_with_policy_no_claims():
    customer = CustomerFactory(age=45)
    PolicyFactory(customer=customer, policy_type="Life", premium_usd=Decimal("300.00"))
    return customer


def _customer_with_denied_zero_claim():
    customer = CustomerFactory(age=70)
    policy = PolicyFactory(customer=customer, policy_type="Health", premium_usd=Decimal("400.00"))
    ClaimFactory(policy=policy, claim_status=ClaimStatus.DENIED, claim_amount_usd=Decimal("0.00"))
    return customer


class TestExactlyFiveFactors:
    """FR-022: every factor row is written, including zero-contribution ones."""

    def test_evaluable_customer_yields_five_factors(self):
        customer = young_auto_customer()
        result = engine.score_customer(customer)

        assert len(result.factors) == 5
        assert {f.factor for f in result.factors} == set(FACTORS)

    def test_unevaluable_customer_still_yields_five_factors(self):
        customer = CustomerFactory(age=40)  # no policy
        result = engine.score_customer(customer)

        assert len(result.factors) == 5
        assert {f.factor for f in result.factors} == set(FACTORS)


class TestNotEvaluablePath:
    """FR-018, FR-023: distinct from an evaluated 0-point factor."""

    def test_customer_with_no_live_policy_gets_not_evaluable_factors(self):
        customer = CustomerFactory(age=40)
        result = engine.score_customer(customer)

        policy_type = next(f for f in result.factors if f.factor == "policy_type")
        ratio = next(f for f in result.factors if f.factor == "claims_ratio")

        assert policy_type.status == FactorStatus.NOT_EVALUABLE
        assert policy_type.unevaluable_reason
        assert ratio.status == FactorStatus.NOT_EVALUABLE
        assert ratio.unevaluable_reason

    def test_archived_policy_is_treated_as_no_live_policy(self):
        customer = CustomerFactory(age=40)
        PolicyFactory(customer=customer, archived=True)
        result = engine.score_customer(customer)

        policy_type = next(f for f in result.factors if f.factor == "policy_type")
        assert policy_type.status == FactorStatus.NOT_EVALUABLE

    def test_evaluated_zero_points_is_distinct_from_not_evaluable(self):
        """A mid-age customer with a Life policy: age contributes 0 but IS evaluated."""
        customer = _mid_age_with_policy_no_claims()
        result = engine.score_customer(customer)

        age = next(f for f in result.factors if f.factor == "age")
        assert age.status == FactorStatus.EVALUATED
        assert age.points == 0
        assert age.unevaluable_reason == ""


class TestDeterminism:
    """FR-002, SC-004: unchanged data scores identically on repeat evaluation."""

    def test_scoring_twice_yields_identical_score_and_factors(self):
        customer = young_auto_customer()

        first = engine.score_customer(customer)
        second = engine.score_customer(customer)

        assert first.score == second.score
        assert first.tier == second.tier
        first_shape = [(f.factor, f.status, f.points, f.band_label) for f in first.factors]
        second_shape = [(f.factor, f.status, f.points, f.band_label) for f in second.factors]
        assert first_shape == second_shape


class TestPersist:
    def test_persist_creates_assessment_and_five_factor_rows(self):
        customer = young_auto_customer()
        result = engine.score_customer(customer)

        assessment = engine.persist(customer, result, actor=None)

        assert assessment.customer_id == customer.id
        assert assessment.score == result.score
        assert RiskFactor.objects.filter(assessment=assessment).count() == 5

    def test_persist_is_idempotent_and_updates_in_place(self):
        customer = young_auto_customer()

        first = engine.persist(customer, engine.score_customer(customer), actor=None)
        second = engine.persist(customer, engine.score_customer(customer), actor=None)

        assert first.id == second.id
        assert RiskAssessment.objects.filter(customer=customer).count() == 1
        assert RiskFactor.objects.filter(assessment=second).count() == 5

    def test_persist_mirrors_score_onto_customer_risk_score(self):
        """FR-055: Customer.risk_score == round(assessment.score / 100, 2)."""
        customer = young_auto_customer()
        result = engine.score_customer(customer)

        assessment = engine.persist(customer, result, actor=None)
        customer.refresh_from_db()

        assert customer.risk_score == round(Decimal(assessment.score) / 100, 2)

    def test_persist_writes_audit_entry(self):
        from apps.audit.models import AuditLog

        customer = young_auto_customer()
        result = engine.score_customer(customer)
        engine.persist(customer, result, actor=None)

        entry = AuditLog.objects.filter(action="risk.computed", target_id=str(customer.risk_assessment.id)).first()
        assert entry is not None
        assert entry.after["score"] == result.score
        assert entry.after["rule_set_version"] == result.rule_set_version


class TestNoAutomaticRecomputation:
    """
    FR-036/SC-011 (T094): nothing recomputes a score as a side effect of
    a customer, policy, or claim write -- not on create, not on an
    ordinary update, and not on archival. Verified per entity because
    each is a plausible place a signal handler could have been wired in
    (a post_save on Customer, on Policy, on Claim) and each needs its own
    proof of absence.
    """

    def _persisted(self):
        customer = young_auto_customer()
        result = engine.score_customer(customer)
        assessment = engine.persist(customer, result, actor=None)
        return customer, assessment

    def test_changing_customer_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        customer.name = "Changed Name"
        customer.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_archiving_customer_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        customer.archived_at = timezone.now()
        customer.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_changing_a_policy_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        policy.premium_usd = Decimal("9999.00")
        policy.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_archiving_a_policy_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        policy.archived_at = timezone.now()
        policy.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_changing_a_claim_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()
        claim = policy.claims.first()

        claim.claim_amount_usd = Decimal("50000.00")
        claim.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_archiving_a_claim_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()
        claim = policy.claims.first()

        claim.archived_at = timezone.now()
        claim.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_creating_a_new_policy_for_an_assessed_customer_does_not_touch_stored_score(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        PolicyFactory(customer=customer, policy_type="Health", premium_usd=Decimal("400.00"))

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at


def test_no_signal_handler_or_scheduled_task_touches_risk_scoring():
    """
    FR-036/SC-011: the absence of a signal handler, post_save hook,
    Celery task or scheduler wired to recompute risk is itself a
    requirement, not an omission (tasks.md T094). This inspects the
    actual receivers Django has connected for post_save/pre_save/
    post_delete on Customer, Policy and Claim, rather than trusting that
    grepping the source for "risk" would have caught an indirect wiring
    (e.g. a receiver registered by name in a signals.py this repo does
    not have).
    """
    from django.db.models.signals import post_delete, post_save, pre_save

    from apps.claims.models import Claim
    from apps.customers.models import Customer
    from apps.policies.models import Policy

    for signal in (post_save, pre_save, post_delete):
        for sender in (Customer, Policy, Claim):
            receivers = signal._live_receivers(sender)
            for receiver in receivers:
                module = getattr(receiver, "__module__", "")
                qualname = getattr(receiver, "__qualname__", "")
                assert "risk" not in module.lower(), (
                    f"{module}.{qualname} is connected to {signal} for {sender} "
                    "-- this is exactly the kind of automatic recomputation "
                    "FR-036 forbids"
                )
