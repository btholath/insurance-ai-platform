import pytest

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role
from apps.audit.factories import AuditLogFactory
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

LIST_URL = "/api/audit/"

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
PERMITTED_ROLES = [Role.COMPLIANCE_OFFICER, Role.SYSTEM_ADMINISTRATOR]
REFUSED_ROLES = [role for role in ALL_ROLES if role not in PERMITTED_ROLES]


def history_url(target_type, target_id):
    return f"/api/audit/history/{target_type}/{target_id}/"


class TestAuditListRbacMatrix:
    def test_unauthenticated_refused_403(self, api_client):
        response = api_client.get(LIST_URL)

        assert response.status_code == 403

    @pytest.mark.parametrize("role", PERMITTED_ROLES)
    def test_permitted_roles_allowed_200(self, authenticated_client, role):
        AuditLogFactory()
        client, _ = authenticated_client(role)

        response = client.get(LIST_URL)

        assert response.status_code == 200
        assert "count" in response.data
        assert "results" in response.data

    @pytest.mark.parametrize("role", REFUSED_ROLES)
    def test_other_roles_refused_403(self, authenticated_client, role):
        client, _ = authenticated_client(role)

        response = client.get(LIST_URL)

        assert response.status_code == 403


class TestAuditHistoryRbacMatrix:
    def test_unauthenticated_refused_404(self, api_client):
        entry = AuditLogFactory(target_type="accounts.User", target_id="7")

        response = api_client.get(history_url(entry.target_type, entry.target_id))

        assert response.status_code == 404

    @pytest.mark.parametrize("role", PERMITTED_ROLES)
    def test_permitted_roles_allowed_200(self, authenticated_client, role):
        entry = AuditLogFactory(target_type="accounts.User", target_id="7")
        client, _ = authenticated_client(role)

        response = client.get(history_url(entry.target_type, entry.target_id))

        assert response.status_code == 200

    @pytest.mark.parametrize("role", REFUSED_ROLES)
    def test_other_roles_refused_404(self, authenticated_client, role):
        entry = AuditLogFactory(target_type="accounts.User", target_id="7")
        client, _ = authenticated_client(role)

        response = client.get(history_url(entry.target_type, entry.target_id))

        assert response.status_code == 404


class TestAuditHistoryOrdering:
    def test_history_returns_entries_in_ascending_chronological_order(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        first = AuditLogFactory(target_type="accounts.User", target_id="7", action="user.created")
        second = AuditLogFactory(target_type="accounts.User", target_id="7", action="user.role_changed")
        third = AuditLogFactory(target_type="accounts.User", target_id="7", action="user.updated")

        response = client.get(history_url("accounts.User", "7"))

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [first.id, second.id, third.id]


class TestAuditHistoryEmptyResult:
    def test_target_with_zero_entries_returns_200_count_zero_not_404(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        response = client.get(history_url("accounts.User", "999999"))

        assert response.status_code == 200
        assert response.data == {
            "target_type": "accounts.User",
            "target_id": "999999",
            "count": 0,
            "results": [],
        }


class TestAuditDeletedActorApiLayer:
    def test_list_and_history_serialize_deleted_actor_as_null_with_snapshot_intact(self, authenticated_client):
        actor = UserFactory(email="admin@example.com", role=Role.SYSTEM_ADMINISTRATOR)
        entry = AuditLogFactory(
            actor=actor,
            actor_identifier="admin@example.com",
            actor_role=Role.SYSTEM_ADMINISTRATOR,
            target_type="accounts.User",
            target_id="7",
            action="user.role_changed",
        )
        entry_id = entry.id
        actor.delete()

        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        list_response = client.get(LIST_URL)
        assert list_response.status_code == 200
        list_row = next(row for row in list_response.data["results"] if row["id"] == entry_id)
        assert list_row["actor"] is None
        assert list_row["actor_identifier"] == "admin@example.com"
        assert list_row["actor_role"] == Role.SYSTEM_ADMINISTRATOR

        history_response = client.get(history_url("accounts.User", "7"))
        assert history_response.status_code == 200
        history_row = next(row for row in history_response.data["results"] if row["id"] == entry_id)
        assert history_row["actor"] is None
        assert history_row["actor_identifier"] == "admin@example.com"
        assert history_row["actor_role"] == Role.SYSTEM_ADMINISTRATOR


class TestAuditListFilters:
    def test_filter_by_target_type_and_target_id(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        match = AuditLogFactory(target_type="accounts.User", target_id="7")
        AuditLogFactory(target_type="accounts.User", target_id="8")
        AuditLogFactory(target_type="claims.Claim", target_id="7")

        response = client.get(LIST_URL, {"target_type": "accounts.User", "target_id": "7"})

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [match.id]

    def test_filter_by_actor(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        actor = UserFactory(role=Role.SYSTEM_ADMINISTRATOR)
        match = AuditLogFactory(actor=actor)
        AuditLogFactory()

        response = client.get(LIST_URL, {"actor": actor.id})

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [match.id]

    def test_filter_by_action(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        match = AuditLogFactory(action="user.role_changed")
        AuditLogFactory(action="user.created")

        response = client.get(LIST_URL, {"action": "user.role_changed"})

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [match.id]

    def test_default_ordering_is_newest_first(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        first = AuditLogFactory()
        second = AuditLogFactory()

        response = client.get(LIST_URL)

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [second.id, first.id]

    def test_ordering_timestamp_param_returns_chronological_order(self, authenticated_client):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
        first = AuditLogFactory()
        second = AuditLogFactory()

        response = client.get(LIST_URL, {"ordering": "timestamp"})

        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [first.id, second.id]


class TestAuditRoutesReadOnly:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_write_methods_refused_405_on_list(self, authenticated_client, method):
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        response = getattr(client, method)(LIST_URL, {}, format="json")

        assert response.status_code == 405

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_write_methods_refused_405_on_history(self, authenticated_client, method):
        entry = AuditLogFactory(target_type="accounts.User", target_id="7")
        client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

        response = getattr(client, method)(history_url(entry.target_type, entry.target_id), {}, format="json")

        assert response.status_code == 405
