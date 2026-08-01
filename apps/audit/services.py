"""
The single write path for audit records (FR-020, FR-022, FR-023).

record_action() MUST be called inside the same transaction.atomic() block
as the action it describes, so that if the audit insert fails, the whole
transaction rolls back and the action never commits (FR-022). No signals,
no on_commit hooks, no async dispatch — see research.md §6.
"""
from .models import AuditLog


def record_action(
    *,
    actor,
    action,
    target_type,
    target_id,
    outcome,
    before=None,
    after=None,
    context=None,
):
    actor_identifier = actor.email if actor is not None else ""
    actor_role = actor.role if actor is not None else ""

    return AuditLog.objects.create(
        actor=actor,
        actor_identifier=actor_identifier,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        outcome=outcome,
        before=before,
        after=after,
        context=context,
    )
