"""
post_save receivers wiring Customer/Policy/Claim saves to automatic risk
recompute (Phase 3b, research.md §1).

Every receiver enqueues via transaction.on_commit(), never a bare
.delay(). A save that later rolls back inside a larger transaction (e.g.
a serializer validation failure inside an atomic() block) must never
enqueue a recompute for data that was never actually persisted -- this is
the one on_commit() usage in this feature, and it exists for exactly the
opposite reason apps/audit/services.py forbids on_commit for the audit
write: that write must share the triggering transaction, this enqueue
must not (research.md §1).

Receivers are connected in each source app's AppConfig.ready(), not here
-- see apps/customers/apps.py, apps/policies/apps.py, apps/claims/apps.py.
"""
from django.db import transaction

from .tasks import recompute_customer_risk


def on_customer_saved(sender, instance, **kwargs):
    transaction.on_commit(lambda: recompute_customer_risk.delay(instance.id))


def on_policy_saved(sender, instance, **kwargs):
    transaction.on_commit(lambda: recompute_customer_risk.delay(instance.customer_id))


def on_claim_saved(sender, instance, **kwargs):
    customer_id = instance.policy.customer_id
    transaction.on_commit(lambda: recompute_customer_risk.delay(customer_id))
