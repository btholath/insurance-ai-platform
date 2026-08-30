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
from django.test import override_settings

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


class TestRetrySucceedsAfterTransientFailure:
    """
    FR-008, FR-009, Acceptance Scenario 2 (US2): a transient failure is
    retried automatically and the assessment ends up correctly recomputed.

    Uses task.apply() rather than .delay()/a bare call: apply() always runs
    the real (non-eager-bypassed) retry path -- autoretry_for wraps the
    task's run() to call self.retry() on a matching exception regardless of
    CELERY_TASK_ALWAYS_EAGER, which only affects .delay()/.apply_async().
    See research.md §5 and this file's module docstring.
    """

    def test_retry_recovers_and_produces_correct_result(self):
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        real_persist = engine.persist
        call_count = {"n": 0}

        def flaky_persist(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            return real_persist(*args, **kwargs)

        with patch.object(engine, "persist", side_effect=flaky_persist):
            # throw=False: retry() returns its Retry signal instead of
            # raising it, which is what lets apply() recurse into the next
            # attempt itself (Task.apply's `if isinstance(retval, Retry):
            # return retval.sig.apply(retries=retries + 1)` branch) --
            # with the default throw=True (task_eager_propagates, T005),
            # the first retry raises straight out of apply() instead.
            result = recompute_customer_risk.apply(args=[customer.id], throw=False)

        assert result.successful()
        assert call_count["n"] == 2

        assessment = RiskAssessment.objects.get(customer=customer)
        expected = engine.score_customer(customer)
        assert assessment.score == expected.score
        assert assessment.tier == expected.tier


class TestRetryBackoffIsDelayedAndIncreasing:
    """
    FR-008, Acceptance Scenario 1 (US2): the retry is delayed, not
    immediate, and later attempts wait longer than earlier ones.

    Jitter (retry_backoff's default retry_jitter=True) makes the actual
    per-call countdown a random draw in [0, ceiling] via
    get_exponential_backoff_interval (celery.utils.time) -- comparing two
    individual draws for strict ordering would be flaky by construction, so
    this asserts on the deterministic ceiling itself (the same calculation
    add_autoretry_behaviour makes from self.request.retries) rather than a
    jittered draw, using the task's actual retry_backoff/retry_backoff_max
    configuration.
    """

    def test_backoff_ceiling_is_nonzero_and_grows_with_retry_count(self):
        from celery.utils.time import get_exponential_backoff_interval

        task = recompute_customer_risk
        ceilings = [
            get_exponential_backoff_interval(
                factor=int(max(1.0, float(task.retry_backoff))),
                retries=retries,
                maximum=task.retry_backoff_max,
                full_jitter=False,
            )
            for retries in range(3)
        ]

        assert all(c > 0 for c in ceilings)
        assert ceilings == sorted(ceilings)
        assert ceilings[1] > ceilings[0]
        assert ceilings[2] > ceilings[1]

    def test_retry_countdown_is_nonzero_and_grows_across_real_attempts(self):
        """
        Same claim as the ceiling test above, but exercised through a real
        failing-then-succeeding task run spanning TWO retries.

        Task.apply()'s own recursive step for a caught Retry --
        `retval.sig.apply(retries=retries + 1)` in celery.app.task.Task.apply
        -- does NOT forward the `throw` argument, so it re-defaults to
        CELERY_TASK_EAGER_PROPAGATES on every retry past the first. A
        single top-level `apply(throw=False)` therefore only survives one
        retry before reverting to raising; override_settings is required
        here (unlike the single-retry tests above) because this scenario
        needs two.

        Patches celery.app.autoretry.get_exponential_backoff_interval (the
        exact call add_autoretry_behaviour makes from self.request.retries
        on each attempt) to record its (retries, computed countdown) pairs,
        with jitter disabled via full_jitter so the recorded values are the
        deterministic ceiling rather than a random draw.
        """
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        from celery.utils.time import get_exponential_backoff_interval as real_backoff

        calls = []

        def recording_backoff(*, factor, retries, maximum, full_jitter):
            countdown = real_backoff(
                factor=factor, retries=retries, maximum=maximum, full_jitter=False
            )
            calls.append((retries, countdown))
            return countdown

        real_persist = engine.persist
        call_count = {"n": 0}

        def fail_twice_then_succeed(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError("transient failure")
            return real_persist(*args, **kwargs)

        with override_settings(CELERY_TASK_EAGER_PROPAGATES=False), patch.object(
            engine, "persist", side_effect=fail_twice_then_succeed
        ), patch(
            "celery.app.autoretry.get_exponential_backoff_interval",
            side_effect=recording_backoff,
        ):
            result = recompute_customer_risk.apply(args=[customer.id])

        assert result.successful()
        assert len(calls) == 2
        (first_retries, first_countdown), (second_retries, second_countdown) = calls
        assert second_retries > first_retries
        assert first_countdown > 0
        assert second_countdown > first_countdown


class TestExhaustedRetryWritesFailureRecord:
    """
    FR-010, Acceptance Scenario 1 (US3): when every retry attempt fails,
    the task's on_failure handler (T035) writes one AuditLog entry
    recording the permanent failure -- the "durable, discoverable record"
    the spec requires, using the platform's existing audit mechanism
    rather than a new alerting channel.

    Uses task.apply() like TestRetrySucceedsAfterTransientFailure --
    apply() runs the real (non-eager-bypassed) retry path regardless of
    CELERY_TASK_ALWAYS_EAGER. Reaching actual exhaustion requires
    surviving all 5 retries, not just the first: as
    TestRetryBackoffIsDelayedAndIncreasing's second test documents,
    apply()'s own recursive step for a caught Retry
    (`retval.sig.apply(retries=retries + 1)`) does not forward `throw`, so
    a bare `apply(throw=False)` only survives one retry before reverting
    to the settings-derived default and raising. override_settings makes
    every retry -- not just the first -- eager-non-propagating, which is
    what lets exhaustion actually happen inside apply() instead of the
    test failing on an uncaught Retry/exception partway through.
    """

    def test_exhausted_retries_write_one_recompute_failed_audit_entry(self):
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        with override_settings(CELERY_TASK_EAGER_PROPAGATES=False), patch.object(
            engine, "persist", side_effect=RuntimeError("permanent failure")
        ):
            result = recompute_customer_risk.apply(args=[customer.id])

        assert not result.successful()

        entries = AuditLog.objects.filter(action="risk.recompute_failed")
        assert entries.count() == 1

        entry = entries.get()
        assert entry.outcome == "refused"
        assert entry.context["customer_id"] == customer.id


class TestExhaustedRetryDoesNotCrashOrCorrupt:
    """
    Acceptance Scenario 1 (US3), "without raising an unhandled error": the
    worker process must survive permanent failure, and the customer's
    existing RiskAssessment must be left exactly as it was -- a failed
    recompute must never leave a partial or corrupted write behind, only
    the absence of an update.
    """

    def test_exhausted_retries_leave_existing_assessment_untouched(self):
        customer = CustomerFactory(age=22)
        assessment = RiskAssessmentFactory(customer=customer, score=42)
        original_score = assessment.score
        original_computed_at = assessment.computed_at

        with override_settings(CELERY_TASK_EAGER_PROPAGATES=False), patch.object(
            engine, "persist", side_effect=RuntimeError("permanent failure")
        ):
            # Does not raise out of apply() -- on_failure handles the
            # exhausted exception rather than letting it propagate, so the
            # calling thread (a worker process, in production) survives.
            result = recompute_customer_risk.apply(args=[customer.id])

        assert not result.successful()

        assessment.refresh_from_db()
        assert assessment.score == original_score
        assert assessment.computed_at == original_computed_at


class TestFailureRecordDoesNotBlockFutureRecompute:
    """
    FR-011, Acceptance Scenario 2 (US3): an exhausted-retry failure record
    for a customer must not make that customer permanently ineligible for
    automatic recompute -- a later data change (simulated here by simply
    invoking the task again, standing in for the next signal-triggered
    enqueue) proceeds normally.
    """

    def test_fresh_invocation_after_exhaustion_succeeds_normally(self):
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        with override_settings(CELERY_TASK_EAGER_PROPAGATES=False), patch.object(
            engine, "persist", side_effect=RuntimeError("permanent failure")
        ):
            recompute_customer_risk.apply(args=[customer.id])

        assert AuditLog.objects.filter(action="risk.recompute_failed").count() == 1

        # A later invocation -- the earlier failure record must not
        # short-circuit or block it in any way.
        recompute_customer_risk(customer.id)

        assessment = RiskAssessment.objects.get(customer=customer)
        expected = engine.score_customer(customer)
        assert assessment.score == expected.score
        assert assessment.tier == expected.tier
        assert AuditLog.objects.filter(action="risk.computed").exists()


class TestRetryLeavesNoInconsistentState:
    """
    Acceptance Scenario 2 (US2): "no trace of the earlier failed attempt"
    -- exactly one RiskAssessment exists both before and after a
    failed-then-succeeded retry sequence, never a duplicate or partial row.
    """

    def test_exactly_one_assessment_before_and_after_retry_sequence(self):
        customer = CustomerFactory(age=22)
        RiskAssessmentFactory(customer=customer)

        assert RiskAssessment.objects.filter(customer=customer).count() == 1

        real_persist = engine.persist
        call_count = {"n": 0}

        def flaky_persist(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("transient failure")
            return real_persist(*args, **kwargs)

        with patch.object(engine, "persist", side_effect=flaky_persist):
            result = recompute_customer_risk.apply(args=[customer.id], throw=False)

        assert result.successful()
        assert RiskAssessment.objects.filter(customer=customer).count() == 1
