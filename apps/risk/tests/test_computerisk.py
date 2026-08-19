"""
Tests for the `computerisk` management command (T049-T054;
contracts/computerisk-command.md).

Written before the command exists -- must FAIL until T055-T059 land.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from ..models import RiskAssessment, RiskFactor

pytestmark = pytest.mark.django_db


def run(*args, **kwargs):
    out = StringIO()
    try:
        call_command("computerisk", *args, stdout=out, stderr=out, **kwargs)
        code = 0
    except SystemExit as exc:
        code = exc.code
    return out.getvalue(), code


def scoreable_customer(**overrides):
    customer = CustomerFactory(age=overrides.pop("age", 22))
    policy = PolicyFactory(
        customer=customer,
        policy_type=overrides.pop("policy_type", "Auto"),
        premium_usd=overrides.pop("premium_usd", Decimal("1000.00")),
    )
    ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
    return customer


class TestCountsAccountForEveryCustomer:
    """FR-031, SC-006: scored + skipped + failed == total considered."""

    def test_scores_every_eligible_customer(self):
        scoreable_customer()
        scoreable_customer()
        scoreable_customer()

        call_command("computerisk")

        assert RiskAssessment.objects.count() == 3


class TestSkipNoLivePolicy:
    def test_customer_with_no_live_policy_is_skipped_with_reason(self):
        no_policy = CustomerFactory(age=40)
        scoreable_customer()

        out, code = run()

        assert not RiskAssessment.objects.filter(customer=no_policy).exists()
        assert no_policy.client_id in out
        assert code == 0

    def test_only_archived_policy_is_treated_as_no_live_policy(self):
        customer = CustomerFactory(age=40)
        PolicyFactory(customer=customer, archived=True)

        call_command("computerisk")

        assert not RiskAssessment.objects.filter(customer=customer).exists()


class TestIdempotency:
    """FR-033, SC-004: a second run over unchanged data is a no-op on outcome."""

    def test_second_run_produces_identical_scores_no_duplicates(self):
        scoreable_customer()

        call_command("computerisk")
        first = list(
            RiskAssessment.objects.values_list("customer_id", "score", "tier").order_by("id")
        )

        call_command("computerisk")
        second = list(
            RiskAssessment.objects.values_list("customer_id", "score", "tier").order_by("id")
        )

        assert first == second
        assert RiskAssessment.objects.count() == 1


class TestPartialFailureIsolation:
    def test_failure_on_one_customer_leaves_others_complete(self, monkeypatch):
        good = scoreable_customer()
        bad = scoreable_customer()

        from .. import engine as engine_module

        original = engine_module.score_customer

        def flaky(customer):
            if customer.id == bad.id:
                raise RuntimeError("synthetic failure")
            return original(customer)

        monkeypatch.setattr(engine_module, "score_customer", flaky)

        out, code = run()

        assert RiskAssessment.objects.filter(customer=good).exists()
        good_assessment = RiskAssessment.objects.get(customer=good)
        assert RiskFactor.objects.filter(assessment=good_assessment).count() == 5
        assert not RiskAssessment.objects.filter(customer=bad).exists()
        assert code == 2


class TestArchivedExclusion:
    """FR-016."""

    def test_archived_customer_is_excluded(self):
        customer = scoreable_customer()
        customer.archived_at = timezone.now()
        customer.save()

        call_command("computerisk")

        assert not RiskAssessment.objects.filter(customer=customer).exists()

    def test_archived_claim_is_excluded_from_ratio(self):
        customer = CustomerFactory(age=22)
        policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
        ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
        archived_claim = ClaimFactory(
            policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("99999.00")
        )
        archived_claim.archived_at = timezone.now()
        archived_claim.save()

        call_command("computerisk", customer=customer.client_id)

        assessment = RiskAssessment.objects.get(customer=customer)
        ratio_factor = assessment.factors.get(factor="claims_ratio")
        # Only the 500.00 claim should count; the 99999.00 archived one must not.
        assert float(ratio_factor.observed_value) < 10


class TestDryRun:
    def test_dry_run_writes_nothing(self):
        customer = scoreable_customer()

        call_command("computerisk", dry_run=True)

        assert not RiskAssessment.objects.filter(customer=customer).exists()
        customer.refresh_from_db()
        assert customer.risk_score is None

        from apps.audit.models import AuditLog

        assert not AuditLog.objects.filter(action__startswith="risk.").exists()


class TestTierDistribution:
    """FR-031, SC-005: every tier holds at least 5% of a diverse scored population."""

    def test_tier_distribution_report(self):
        # Construct a population that spans all four tiers.
        for _ in range(3):
            scoreable_customer(age=22, policy_type="Auto")  # high-ish
        for _ in range(3):
            scoreable_customer(age=45, policy_type="Life")  # low-ish
        for _ in range(3):
            scoreable_customer(age=70, policy_type="Health")  # elevated-ish
        for _ in range(3):
            scoreable_customer(age=30, policy_type="Property")  # moderate-ish

        out, code = run()

        assert code == 0
        assert "low" in out
        assert "moderate" in out
        assert "elevated" in out
        assert "high" in out


class TestSingleCustomerAndTierFilters:
    def test_customer_filter_scores_only_that_customer(self):
        target = scoreable_customer()
        other = scoreable_customer()

        call_command("computerisk", customer=target.client_id)

        assert RiskAssessment.objects.filter(customer=target).exists()
        assert not RiskAssessment.objects.filter(customer=other).exists()

    def test_unknown_customer_aborts_with_exit_code_1(self):
        out, code = run(customer="CL-99999")
        assert code == 1

    def test_unknown_tier_aborts_with_exit_code_1(self):
        out, code = run(tier="not-a-tier")
        assert code == 1

    def test_tier_filter_rescopes_to_that_tier_only(self):
        low = scoreable_customer(age=45, policy_type="Life")
        call_command("computerisk", customer=low.client_id)

        other = scoreable_customer(age=22, policy_type="Auto")
        low_tier = RiskAssessment.objects.get(customer=low).tier

        call_command("computerisk", tier=low_tier)

        assert RiskAssessment.objects.filter(customer=low).exists()

    def test_limit_stops_after_n_customers(self):
        scoreable_customer()
        scoreable_customer()
        scoreable_customer()

        call_command("computerisk", limit=1)

        assert RiskAssessment.objects.count() == 1


class TestBatchAuditEntry:
    """FR-050, FR-054."""

    def test_batch_run_writes_one_batch_computed_entry(self):
        scoreable_customer()
        scoreable_customer()

        call_command("computerisk")

        from apps.audit.models import AuditLog

        batch_entries = AuditLog.objects.filter(action="risk.batch_computed")
        assert batch_entries.count() == 1
        entry = batch_entries.first()
        assert entry.context["scored"] == 2
        assert entry.context["rule_set_version"] == "1.0.0"
