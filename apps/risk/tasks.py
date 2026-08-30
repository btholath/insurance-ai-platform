"""
Automatic risk recompute (Phase 3b, research.md §1-§3).

Signals are used here after being explicitly rejected for audit writes
(apps/audit/services.py's "no signals, no on_commit hooks, no async
dispatch" stance) and after Phase 3a's own test asserting the codebase
contained no signal handler at all. That is not a contradiction: the audit
write must share the triggering transaction so a failure rolls both back
together, while this task's enqueue must NOT share it -- a slow or failing
recompute must never be able to fail the Customer/Policy/Claim write that
triggered it (FR-018). Signals are the correct mechanism for exactly the
reason they were the wrong one for audit writes; see research.md §1 for the
full rationale.
"""
import logging

from celery import Task, shared_task

from apps.audit.services import record_action
from apps.customers.models import Customer

from . import engine
from .models import RiskAssessment

logger = logging.getLogger(__name__)


class RecomputeCustomerRiskTask(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        customer_id = args[0]
        assessment = RiskAssessment.objects.filter(customer_id=customer_id).first()
        target_id = assessment.id if assessment is not None else customer_id

        record_action(
            actor=None,
            action="risk.recompute_failed",
            target_type="risk.RiskAssessment",
            target_id=target_id,
            outcome="refused",
            context={
                "customer_id": customer_id,
                "exception": str(exc),
                "attempts": self.request.retries,
            },
        )
        logger.error(
            "recompute_customer_risk permanently failed for customer_id=%s: %s",
            customer_id,
            exc,
            extra={"customer_id": customer_id, "exception": str(exc)},
        )


@shared_task(
    bind=True,
    base=RecomputeCustomerRiskTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def recompute_customer_risk(self, customer_id):
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        return

    if not RiskAssessment.objects.filter(customer=customer).exists():
        return

    result = engine.score_customer(customer)
    engine.persist(customer, result, actor=None)
