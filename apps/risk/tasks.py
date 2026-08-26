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
from celery import shared_task

from apps.customers.models import Customer

from . import engine
from .models import RiskAssessment


@shared_task(
    bind=True,
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
