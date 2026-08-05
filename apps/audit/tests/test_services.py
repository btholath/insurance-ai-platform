from unittest.mock import patch

import pytest
from django.db import DatabaseError, transaction

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.audit.services import record_action

pytestmark = pytest.mark.django_db


def test_record_action_writes_row_with_all_required_fields():
    actor = UserFactory(email="admin@example.com", role=Role.SYSTEM_ADMINISTRATOR)

    entry = record_action(
        actor=actor,
        action="user.created",
        target_type="accounts.User",
        target_id=7,
        outcome=AuditLog.Outcome.SUCCEEDED,
        before=None,
        after={"email": "new@example.com", "role": "claims_adjuster", "is_active": True},
    )

    entry.refresh_from_db()
    assert entry.actor_id == actor.id
    assert entry.actor_identifier == "admin@example.com"
    assert entry.actor_role == Role.SYSTEM_ADMINISTRATOR
    assert entry.action == "user.created"
    assert entry.target_type == "accounts.User"
    assert entry.target_id == "7"
    assert entry.outcome == AuditLog.Outcome.SUCCEEDED
    assert entry.after == {"email": "new@example.com", "role": "claims_adjuster", "is_active": True}


def test_audit_insert_failure_rolls_back_enclosing_action():
    admin = UserFactory(role=Role.SYSTEM_ADMINISTRATOR)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            created = User.objects.create_user(
                email="should-not-persist@example.com",
                password="a-strong-password-123",
                role=Role.CLAIMS_ADJUSTER,
            )
            with patch.object(AuditLog.objects, "create", side_effect=DatabaseError("simulated audit write failure")):
                record_action(
                    actor=admin,
                    action="user.created",
                    target_type="accounts.User",
                    target_id=created.id,
                    outcome=AuditLog.Outcome.SUCCEEDED,
                    before=None,
                    after={"email": created.email, "role": created.role, "is_active": created.is_active},
                )

    assert not User.objects.filter(email="should-not-persist@example.com").exists()
