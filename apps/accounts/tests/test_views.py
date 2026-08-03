import pytest

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

ALL_ROLES = [
    Role.FRAUD_ANALYST,
    Role.CLAIMS_ADJUSTER,
    Role.CUSTOMER_SERVICE,
    Role.UNDERWRITER,
    Role.COMPLIANCE_OFFICER,
    Role.RISK_MANAGER,
    Role.PRODUCT_MANAGER,
    Role.EXECUTIVE_LEADERSHIP,
    Role.SYSTEM_ADMINISTRATOR,
]

NON_ADMIN_ROLES = [role for role in ALL_ROLES if role != Role.SYSTEM_ADMINISTRATOR]


def _create_payload(**overrides):
    payload = {
        "email": "adjuster@example.com",
        "password": "a-strong-password-123",
        "first_name": "Dana",
        "last_name": "Reyes",
        "role": Role.CLAIMS_ADJUSTER.value,
    }
    payload.update(overrides)
    return payload


class TestPostUsersRbacMatrix:
    url = "/api/users/"

    def test_unauthenticated_refused_403(self, api_client):
        response = api_client.post(self.url, _create_payload(), format="json")

        assert response.status_code == 403
        assert not User.objects.filter(email="adjuster@example.com").exists()

    def test_system_administrator_allowed_201(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        response = client.post(self.url, _create_payload(), format="json")

        assert response.status_code == 201
        assert User.objects.filter(email="adjuster@example.com").exists()
        assert "password" not in response.data

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_refused_403(self, authenticated_client, role):
        client, _ = authenticated_client(role)

        response = client.post(self.url, _create_payload(), format="json")

        assert response.status_code == 403
        assert not User.objects.filter(email="adjuster@example.com").exists()


class TestGetUserDetailRbacMatrix:
    def _url(self, user_id):
        return f"/api/users/{user_id}/"

    def test_unauthenticated_refused_404(self, api_client):
        target = UserFactory(role=Role.CLAIMS_ADJUSTER)

        response = api_client.get(self._url(target.id))

        assert response.status_code == 404

    def test_system_administrator_allowed_200(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        target = UserFactory(role=Role.CLAIMS_ADJUSTER)

        response = client.get(self._url(target.id))

        assert response.status_code == 200
        assert response.data["id"] == target.id

    @pytest.mark.parametrize("role", NON_ADMIN_ROLES)
    def test_non_admin_roles_refused_404(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        target = UserFactory(role=Role.CLAIMS_ADJUSTER)

        response = client.get(self._url(target.id))

        assert response.status_code == 404


class TestGetUsersListShape:
    url = "/api/users/"

    def test_response_has_count_and_results_per_contract(self, authenticated_client):
        client, admin = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        UserFactory(role=Role.CLAIMS_ADJUSTER)

        response = client.get(self.url)

        assert response.status_code == 200
        assert set(response.data.keys()) >= {"count", "results"}
        assert response.data["count"] == 2
        assert len(response.data["results"]) == 2
        assert "password" not in response.data["results"][0]


class TestPostUsersInvalidRole:
    url = "/api/users/"

    def test_invalid_role_returns_400_naming_field_no_account_created(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        response = client.post(self.url, _create_payload(role="auditor"), format="json")

        assert response.status_code == 400
        assert "role" in response.data
        assert not User.objects.filter(email="adjuster@example.com").exists()

    def test_missing_role_returns_400_no_account_created(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        payload = _create_payload()
        del payload["role"]

        response = client.post(self.url, payload, format="json")

        assert response.status_code == 400
        assert "role" in response.data
        assert not User.objects.filter(email="adjuster@example.com").exists()


class TestPatchUserRoleImmediateEffect:
    url = "/api/users/"

    def _url(self, user_id):
        return f"/api/users/{user_id}/"

    def test_role_change_by_admin_succeeds_and_takes_effect_next_request(self, authenticated_client):
        from rest_framework.test import APIClient

        admin_client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        target_password = "a-strong-password-123"
        target = UserFactory(role=Role.CLAIMS_ADJUSTER, password=target_password)

        # Target has its own real session — force_authenticate() pins request.user
        # to a fixed Python object and would never re-read the DB, which would
        # make this test prove nothing about FR-016's actual "no re-login needed"
        # guarantee. A real session, backed by AuthenticationMiddleware's
        # per-request DB lookup, is required to prove the claim honestly.
        target_client = APIClient()
        login_response = target_client.post(
            "/api/auth/login/", {"email": target.email, "password": target_password}, format="json"
        )
        assert login_response.status_code == 200

        pre_change_response = target_client.post(self.url, _create_payload(email="before@example.com"), format="json")
        assert pre_change_response.status_code == 403

        response = admin_client.patch(
            self._url(target.id), {"role": Role.SYSTEM_ADMINISTRATOR.value}, format="json"
        )
        assert response.status_code == 200

        # Same session as before — no re-login, no cache invalidation call —
        # yet the very next request sees the new role.
        post_change_response = target_client.post(self.url, _create_payload(email="after@example.com"), format="json")
        assert post_change_response.status_code == 201
        assert User.objects.filter(email="after@example.com").exists()

    def test_setting_is_active_false_records_user_deactivated(self, authenticated_client):
        admin_client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        target = UserFactory(role=Role.CLAIMS_ADJUSTER, is_active=True)

        response = admin_client.patch(self._url(target.id), {"is_active": False}, format="json")

        assert response.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False
        entry = AuditLog.objects.get(action="user.deactivated", target_id=str(target.id))
        assert entry.after == {"is_active": False}

    def test_patch_with_no_changed_fields_records_user_updated(self, authenticated_client):
        admin_client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        target = UserFactory(role=Role.CLAIMS_ADJUSTER, first_name="Original")

        response = admin_client.patch(self._url(target.id), {"first_name": "Original"}, format="json")

        assert response.status_code == 200
        entry = AuditLog.objects.get(action="user.updated", target_id=str(target.id))
        assert entry.before is None
        assert entry.after is None
