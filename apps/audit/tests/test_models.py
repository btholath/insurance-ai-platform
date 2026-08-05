import pytest

from apps.accounts.factories import UserFactory
from apps.audit.factories import AuditLogFactory
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_save_raises_on_update_of_existing_record():
    entry = AuditLogFactory()

    entry.outcome = AuditLog.Outcome.REFUSED
    with pytest.raises(NotImplementedError):
        entry.save()


def test_delete_raises():
    entry = AuditLogFactory()

    with pytest.raises(NotImplementedError):
        entry.delete()


def test_queryset_update_raises():
    AuditLogFactory()

    with pytest.raises(NotImplementedError):
        AuditLog.objects.all().update(outcome=AuditLog.Outcome.REFUSED)


def test_queryset_delete_raises():
    AuditLogFactory()

    with pytest.raises(NotImplementedError):
        AuditLog.objects.all().delete()


def test_deleting_actor_leaves_audit_entries_readable_with_actor_null():
    actor = UserFactory(email="admin@example.com", role="system_administrator")
    entry = AuditLogFactory(actor=actor, actor_identifier="admin@example.com", actor_role="system_administrator")
    entry_id = entry.id

    actor.delete()

    entry.refresh_from_db()
    assert entry.actor is None
    assert entry.actor_identifier == "admin@example.com"
    assert entry.actor_role == "system_administrator"
    assert AuditLog.objects.filter(id=entry_id).exists()
