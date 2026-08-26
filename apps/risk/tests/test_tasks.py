"""
Tests for `recompute_customer_risk` (T008-T010, T024-T026, T031-T034;
celery-task-contract.md).

Happy-path/idempotency tests (T008-T010) run under eager mode
(CELERY_TASK_ALWAYS_EAGER, config/settings/test.py) -- `.delay()` executes
synchronously in-process, so a test can assert on the resulting
RiskAssessment state immediately with no worker or Redis.

Retry/backoff (T024-T026) and permanent-failure (T031-T034) tests
deliberately run OUTSIDE eager mode: eager mode disables Celery's retry
machinery entirely (an eager task that raises just raises, immediately, in
the calling thread), so exercising FR-008/FR-009's real backoff and
FR-010's exhaustion path requires calling the task through Celery's own
`apply()` (research.md §5).
"""
from unittest.mock import patch

import pytest

from apps.audit.models import AuditLog
from apps.customers.factories import CustomerFactory

from .. import engine
from ..factories import RiskAssessmentFactory
from ..models import RiskAssessment
from ..tasks import recompute_customer_risk

pytestmark = pytest.mark.django_db


class TestNoOpWhenUnscored:
    """FR-005, celery-task-contract.md: no existing RiskAssessment -> no-op."""

    def test_no_op_when_customer_has_no_existing_assessment(self):
        customer = CustomerFactory()

        with patch.object(engine, "persist") as mock_persist:
            recompute_customer_risk(customer.id)

        mock_persist.assert_not_called()
        assert not RiskAssessment.objects.filter(customer=customer).exists()
        assert not AuditLog.objects.filter(action="risk.computed").exists()


class TestNoOpWhenCustomerMissing:
    """spec.md edge case: archived or nonexistent customer_id -> no-op."""

    def test_no_op_when_customer_id_does_not_resolve(self):
        with patch.object(engine, "persist") as mock_persist:
            recompute_customer_risk(999999)

        mock_persist.assert_not_called()

    def test_no_op_when_customer_is_archived(self):
        customer = CustomerFactory(archived=True)

        with patch.object(engine, "persist") as mock_persist:
            recompute_customer_risk(customer.id)

        mock_persist.assert_not_called()


class TestRecomputeMatchesManualPath:
    """FR-006, FR-007: identical shape to engine.score_customer()+persist(actor=None)."""

    def test_recompute_produces_same_shape_as_manual_call(self):
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        recompute_customer_risk(customer.id)

        assessment = RiskAssessment.objects.get(customer=customer)
        expected = engine.score_customer(customer)

        assert assessment.score == expected.score
        assert assessment.tier == expected.tier
        assert assessment.factors.count() == 5
        assert assessment.computed_by is None
