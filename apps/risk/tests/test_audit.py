"""
Audit trail tests (T072-T077; FR-048 through FR-054).

The write paths under test (engine.persist's risk.computed,
computerisk's risk.batch_computed) already exist from T033/T079 -- these
tests are the independent verification, following the "verify in full"
posture T078 calls for.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from .. import engine

pytestmark = pytest.mark.django_db


def scoreable_customer():
    customer = CustomerFactory(age=22)
    policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
    ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
    return customer


class TestComputedEntry:
    def test_every_computation_writes_actor_time_before_after(self):
        actor = UserFactory(role=Role.RISK_MANAGER)
        customer = scoreable_customer()

        result = engine.score_customer(customer)
        assessment = engine.persist(customer, result, actor=actor)

        entry = AuditLog.objects.get(action="risk.computed", target_id=str(assessment.id))
        assert entry.actor_id == actor.id
        assert entry.timestamp is not None
        assert entry.before == {"score": None}
        assert entry.after["score"] == result.score

    def test_recompute_records_previous_score_as_before(self):
        actor = UserFactory(role=Role.RISK_MANAGER)
        customer = scoreable_customer()

        first = engine.persist(customer, engine.score_customer(customer), actor=actor)
        second = engine.persist(customer, engine.score_customer(customer), actor=actor)

        entries = AuditLog.objects.filter(
            action="risk.computed", target_id=str(second.id)
        ).order_by("id")
        assert entries.count() == 2
        assert entries[1].before == {"score": first.score}


class TestUnchangedScoreStillRecorded:
    def test_recompute_with_unchanged_score_is_recorded(self):
        customer = scoreable_customer()
        engine.persist(customer, engine.score_customer(customer), actor=None)

        before_count = AuditLog.objects.filter(action="risk.computed").count()
        engine.persist(customer, engine.score_customer(customer), actor=None)
        after_count = AuditLog.objects.filter(action="risk.computed").count()

        assert after_count == before_count + 1


class TestBatchEntryDistinctFromPerCustomer:
    def test_batch_computed_distinguishable_from_computed_entries(self):
        from django.core.management import call_command

        scoreable_customer()
        scoreable_customer()

        call_command("computerisk")

        assert AuditLog.objects.filter(action="risk.computed").count() == 2
        assert AuditLog.objects.filter(action="risk.batch_computed").count() == 1


class TestRuleSetVersionCarried:
    def test_every_entry_carries_rule_set_version(self):
        customer = scoreable_customer()
        result = engine.score_customer(customer)
        assessment = engine.persist(customer, result, actor=None)

        entry = AuditLog.objects.get(action="risk.computed", target_id=str(assessment.id))
        assert entry.after["rule_set_version"] == result.rule_set_version
        assert assessment.rule_set_version == result.rule_set_version


class TestAuditWriteSharesTheTransaction:
    def test_forcing_the_audit_write_to_fail_leaves_the_score_uncommitted(self, monkeypatch):
        customer = scoreable_customer()
        result = engine.score_customer(customer)

        def boom(**kwargs):
            raise IntegrityError("synthetic audit failure")

        monkeypatch.setattr("apps.risk.engine.record_action", boom)

        with pytest.raises(IntegrityError):
            engine.persist(customer, result, actor=None)

        from ..models import RiskAssessment

        assert not RiskAssessment.objects.filter(customer=customer).exists()
        customer.refresh_from_db()
        assert customer.risk_score is None


class TestAppendOnly:
    def test_risk_audit_entries_are_append_only(self):
        customer = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)
        entry = AuditLog.objects.get(action="risk.computed", target_id=str(assessment.id))

        entry.outcome = "tampered"
        with pytest.raises(NotImplementedError):
            entry.save()

    def test_risk_audit_entries_cannot_be_deleted(self):
        customer = scoreable_customer()
        assessment = engine.persist(customer, engine.score_customer(customer), actor=None)
        entry = AuditLog.objects.get(action="risk.computed", target_id=str(assessment.id))

        with pytest.raises(NotImplementedError):
            entry.delete()


class TestRefusedOperationsRecorded:
    def test_refused_recompute_is_recorded_by_the_registry_path(self, authenticated_client):
        """
        FR-051: a refused risk operation is recorded with actor and
        attempted action -- via the shared audit-refusal path the registry
        entry (T080) wires up, not a bespoke mechanism in this app.
        """
        client, user = authenticated_client(Role.UNDERWRITER)
        customer = scoreable_customer()

        response = client.post(
            "/api/risk/assessments/recompute/", {"customer": customer.id}, format="json"
        )

        assert response.status_code == 403
        entry = AuditLog.objects.filter(
            actor=user, action__startswith="risk.", outcome="refused"
        ).first()
        assert entry is not None
