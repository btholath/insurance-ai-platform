import pytest

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_create_then_role_change_produces_expected_audit_trail(authenticated_client):
    admin_client, admin = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

    create_response = admin_client.post(
        "/api/users/",
        {
            "email": "adjuster@example.com",
            "password": "a-strong-password-123",
            "first_name": "Dana",
            "last_name": "Reyes",
            "role": Role.CLAIMS_ADJUSTER.value,
        },
        format="json",
    )
    assert create_response.status_code == 201
    created_id = create_response.data["id"]

    patch_response = admin_client.patch(
        f"/api/users/{created_id}/", {"role": Role.UNDERWRITER.value}, format="json"
    )
    assert patch_response.status_code == 200

    entries = list(
        AuditLog.objects.filter(target_type="accounts.User", target_id=str(created_id)).order_by("timestamp", "id")
    )

    assert [e.action for e in entries] == ["user.created", "user.role_changed"]

    created_entry, role_changed_entry = entries
    assert created_entry.before is None
    assert created_entry.after == {
        "email": "adjuster@example.com",
        "role": Role.CLAIMS_ADJUSTER.value,
        "is_active": True,
    }
    assert created_entry.outcome == AuditLog.Outcome.SUCCEEDED

    assert role_changed_entry.before == {"role": Role.CLAIMS_ADJUSTER.value}
    assert role_changed_entry.after == {"role": Role.UNDERWRITER.value}
    assert role_changed_entry.outcome == AuditLog.Outcome.SUCCEEDED

    for entry in entries:
        assert entry.actor_id == admin.id
        assert entry.actor_identifier == admin.email
        assert entry.actor_role == Role.SYSTEM_ADMINISTRATOR
