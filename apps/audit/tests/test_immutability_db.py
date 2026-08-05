import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit.factories import AuditLogFactory

pytestmark = pytest.mark.django_db


def test_db_trigger_rejects_raw_update():
    entry = AuditLogFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditlog SET outcome = %s WHERE id = %s",
                    ["refused", entry.id],
                )


def test_db_trigger_rejects_raw_delete():
    entry = AuditLogFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [entry.id])


def test_db_trigger_leaves_row_intact_after_rejected_update():
    entry = AuditLogFactory(outcome="succeeded")

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditlog SET outcome = %s WHERE id = %s",
                    ["refused", entry.id],
                )

    entry.refresh_from_db()
    assert entry.outcome == "succeeded"
