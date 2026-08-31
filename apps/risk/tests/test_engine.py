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


class TestNoSynchronousRecomputation:
    """
    FR-036/SC-011 (T094), narrowed by Phase 3b (research.md §1, tasks.md
    T042): a customer, policy, or claim write no longer leaves the score
    untouched forever -- Phase 3b's whole point is that it eventually
    recomputes, via `apps/risk/signals.py`'s post_save receivers enqueuing
    `recompute_customer_risk` through `transaction.on_commit()`. What
    still holds, and is what this class now proves, is the NARROWER claim
    plan.md's Constitution Check calls for: no code path recomputes
    *synchronously inside the request or the triggering model's own
    save()* -- the stored score is provably unchanged the instant
    `.save()` returns, before any commit hook has had a chance to run.

    Each test pairs that immediate-unchanged assertion with the opposite
    case -- the same write, but with `django_capture_on_commit_callbacks`
    driving the deferred task to completion -- as a canary against a
    silently broken trigger. Without this pairing, a test asserting only
    "score didn't change" cannot distinguish "correctly deferred" from
    "the on_commit wiring quietly stopped enqueueing anything", which is
    exactly the failure mode a differently-broken introspection test
    elsewhere in this file (see test_no_signal_handler_or_scheduled_task_
    touches_risk_scoring's revision) suffered from for unrelated reasons.
    """

    def _persisted(self):
        customer = young_auto_customer()
        result = engine.score_customer(customer)
        assessment = engine.persist(customer, result, actor=None)
        return customer, assessment

    def test_changing_customer_does_not_touch_stored_score_synchronously(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        customer.name = "Changed Name"
        customer.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_changing_customer_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            customer.name = "Changed Name"
            customer.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at

    def test_archiving_customer_does_not_touch_stored_score_synchronously(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        customer.archived_at = timezone.now()
        customer.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_archiving_customer_enqueues_a_task_that_correctly_no_ops(
        self, django_capture_on_commit_callbacks
    ):
        """
        Unlike the other paired tests in this class, archiving a customer
        is NOT expected to change computed_at even once the deferred task
        runs: `recompute_customer_risk` looks the customer up through
        `Customer.objects` (apps/risk/tasks.py), the default manager that
        `apps/customers/models.py`'s CustomerManager filters to
        `archived_at__isnull=True` -- so the just-archived row is
        invisible to that lookup, `Customer.DoesNotExist` is raised inside
        the task, and it returns having done nothing. This asserts that
        specific no-op, not merely "unchanged", so a future change to
        either the manager filter or the task's lookup would fail this
        test rather than pass it by accident.
        """
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            customer.archived_at = timezone.now()
            customer.save()

        assessment.refresh_from_db()
        assert assessment.computed_at == original_computed_at

    def test_changing_a_policy_does_not_touch_stored_score_synchronously(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        policy.premium_usd = Decimal("9999.00")
        policy.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_changing_a_policy_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        with django_capture_on_commit_callbacks(execute=True):
            policy.premium_usd = Decimal("9999.00")
            policy.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at

    def test_archiving_a_policy_does_not_touch_stored_score_synchronously(self):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        policy.archived_at = timezone.now()
        policy.save()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_archiving_a_policy_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()

        with django_capture_on_commit_callbacks(execute=True):
            policy.archived_at = timezone.now()
            policy.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at

    def test_changing_a_claim_does_not_touch_stored_score_synchronously(self):
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

    def test_changing_a_claim_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()
        claim = policy.claims.first()

        with django_capture_on_commit_callbacks(execute=True):
            claim.claim_amount_usd = Decimal("50000.00")
            claim.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at

    def test_archiving_a_claim_does_not_touch_stored_score_synchronously(self):
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

    def test_archiving_a_claim_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at
        policy = customer.policies.first()
        claim = policy.claims.first()

        with django_capture_on_commit_callbacks(execute=True):
            claim.archived_at = timezone.now()
            claim.save()

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at

    def test_creating_a_new_policy_for_an_assessed_customer_does_not_touch_stored_score_synchronously(
        self,
    ):
        customer, assessment = self._persisted()
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        PolicyFactory(customer=customer, policy_type="Health", premium_usd=Decimal("400.00"))

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at

    def test_creating_a_new_policy_for_an_assessed_customer_does_recompute_once_committed(
        self, django_capture_on_commit_callbacks
    ):
        customer, assessment = self._persisted()
        original_computed_at = assessment.computed_at

        with django_capture_on_commit_callbacks(execute=True):
            PolicyFactory(customer=customer, policy_type="Health", premium_usd=Decimal("400.00"))

        assessment.refresh_from_db()
        assert assessment.computed_at > original_computed_at


def test_no_signal_handler_or_scheduled_task_touches_risk_scoring_synchronously():
    """
    FR-036/SC-011, narrowed by Phase 3b (tasks.md T042, plan.md's
    Constitution Check post-Phase-1 note): the ORIGINAL claim here --
    "the codebase contains no signal handler at all" connected to
    Customer/Policy/Claim -- is now false by design (apps/risk/signals.py
    exists precisely to enqueue automatic recompute). What must still
    hold, and is what this test now proves, is the narrower claim: no
    receiver connected to these signals calls into the scoring engine
    (`engine.score_customer`/`engine.persist`) SYNCHRONOUSLY, inside the
    signal dispatch itself. `apps.risk.signals`'s receivers are fine
    precisely because all they do is schedule `recompute_customer_risk`
    through `transaction.on_commit()` -- the actual scoring call happens
    later, inside the deferred task, never on this call stack.

    This inspects the actual receivers Django has connected, rather than
    trusting that grepping the source for "risk" would have caught an
    indirect wiring -- but unlike the pre-Phase-3b version of this test,
    it does so correctly: `Signal._live_receivers()` in the Django version
    this project pins returns a `(sync_receivers, async_receivers)`
    2-TUPLE OF LISTS, not a flat list of receiver callables. The original
    version's `for receiver in receivers:` iterated over that 2-tuple
    itself -- binding `receiver` to each of the two inner lists, never to
    an actual function -- so every `getattr(receiver, "__module__", "")`
    silently fell through to the "" default and the assertion passed
    vacuously regardless of what was actually connected, on both sides of
    Phase 3b. Confirmed interactively: Customer/Policy/Claim's post_save
    receivers report `__module__ is None` when misindexed this way, which
    is what let this test pass throughout Phase 3b's signal wiring going
    in without ever exercising the check it claims to perform.
    """
    from django.db.models.signals import post_delete, post_save, pre_save

    from apps.claims.models import Claim
    from apps.customers.models import Customer
    from apps.policies.models import Policy

    for signal in (post_save, pre_save, post_delete):
        for sender in (Customer, Policy, Claim):
            sync_receivers, async_receivers = signal._live_receivers(sender)
            for receiver in (*sync_receivers, *async_receivers):
                module = getattr(receiver, "__module__", "") or ""
                qualname = getattr(receiver, "__qualname__", "") or ""
                assert module != "apps.risk.engine", (
                    f"{module}.{qualname} is connected to {signal} for {sender} "
                    "-- a signal receiver must never call into the scoring "
                    "engine synchronously; it must only enqueue the async "
                    "recompute task via transaction.on_commit(), per "
                    "apps/risk/signals.py"
                )
                assert qualname != "recompute_customer_risk", (
                    f"{module}.{qualname} is connected directly to {signal} for "
                    f"{sender} -- the Celery task itself must never be the "
                    "receiver; only a signals.py wrapper calling .delay() "
                    "inside transaction.on_commit() may be connected, so a "
                    "rolled-back transaction can never enqueue a recompute "
                    "for data that was never persisted"
                )
