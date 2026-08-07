"""
Customer API tests (T027 - T032, T039 - T042, T062).

Note the deliberate status asymmetry inherited from Phase 1's HasRole:
collection-route refusals are 403, detail-route refusals are 404. A 403 on
a detail route would confirm the record exists, which FR-022 forbids.
"""
import pytest

from apps.accounts.models import Role
from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db

LIST_URL = "/api/customers/"


def detail_url(pk):
    return f"/api/customers/{pk}/"


VIEW_ROLES = [
    Role.CUSTOMER_SERVICE,
    Role.SYSTEM_ADMINISTRATOR,
    Role.UNDERWRITER,
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.RISK_MANAGER,
    Role.COMPLIANCE_OFFICER,
]
NO_VIEW_ROLES = [Role.PRODUCT_MANAGER, Role.EXECUTIVE_LEADERSHIP]

VALID_PAYLOAD = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "555-0100",
    "age": 36,
    "gender": "Female",
    "location": "London",
    "lead_source": "Referral",
}


# ---------------------------------------------------------------------------
# T027: read permissions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", VIEW_ROLES)
def test_permitted_roles_can_list(authenticated_client, role):
    client, _ = authenticated_client(role)

    assert client.get(LIST_URL).status_code == 200


@pytest.mark.parametrize("role", NO_VIEW_ROLES)
def test_unpermitted_roles_refused_on_list(authenticated_client, role):
    """FR-024: collection route refusal is 403."""
    client, _ = authenticated_client(role)

    assert client.get(LIST_URL).status_code == 403


def test_unauthenticated_refused_on_list(api_client):
    assert api_client.get(LIST_URL).status_code == 403


# ---------------------------------------------------------------------------
# T028: pagination and ordering (FR-017)
# ---------------------------------------------------------------------------


def test_list_is_paginated_to_50(authenticated_client):
    CustomerFactory.create_batch(60)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL)

    assert len(response.data["results"]) == 50
    assert response.data["count"] == 60


def test_list_reports_total_matching_count(authenticated_client):
    CustomerFactory.create_batch(3)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL).data["count"] == 3


def test_list_ordering_is_stable_across_requests(authenticated_client):
    CustomerFactory.create_batch(60)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    first = [c["id"] for c in client.get(LIST_URL, {"page": 2}).data["results"]]
    second = [c["id"] for c in client.get(LIST_URL, {"page": 2}).data["results"]]

    assert first == second


# ---------------------------------------------------------------------------
# T029: search (FR-018, SC-008)
# ---------------------------------------------------------------------------


def test_search_by_partial_name_case_insensitive(authenticated_client):
    CustomerFactory(name="Patrick Hart")
    CustomerFactory(name="Someone Else")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL, {"search": "patrick"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["name"] == "Patrick Hart"


def test_search_by_shared_email_returns_both_holders(authenticated_client):
    """SC-008 / FR-004."""
    CustomerFactory(email="shared@example.com")
    CustomerFactory(email="shared@example.com")
    CustomerFactory(email="other@example.com")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL, {"search": "shared@example.com"})

    assert response.data["count"] == 2


def test_search_by_client_id(authenticated_client):
    CustomerFactory(client_id="CL-00777")
    CustomerFactory(client_id="CL-00888")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL, {"search": "CL-00777"})

    assert response.data["count"] == 1


def test_search_is_case_insensitive_for_client_id(authenticated_client):
    CustomerFactory(client_id="CL-00777")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL, {"search": "cl-00777"}).data["count"] == 1


def test_search_with_no_matches_returns_empty_not_error(authenticated_client):
    CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL, {"search": "nobody-matches-this"})

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["results"] == []


# ---------------------------------------------------------------------------
# T030: filters (FR-019)
# ---------------------------------------------------------------------------


def test_filter_by_lead_source(authenticated_client):
    CustomerFactory(lead_source="Agent")
    CustomerFactory(lead_source="Web")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL, {"lead_source": "Agent"}).data["count"] == 1


def test_filter_by_gender(authenticated_client):
    CustomerFactory(gender="Female")
    CustomerFactory(gender="Male")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL, {"gender": "Female"}).data["count"] == 1


def test_filter_by_fraud_risk_flag(authenticated_client):
    CustomerFactory(fraud_risk_flag="High")
    CustomerFactory(fraud_risk_flag="Low")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL, {"fraud_risk_flag": "High"}).data["count"] == 1


def test_filters_combine(authenticated_client):
    CustomerFactory(lead_source="Agent", gender="Female")
    CustomerFactory(lead_source="Agent", gender="Male")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL, {"lead_source": "Agent", "gender": "Female"})

    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# T031: retrieve (FR-022)
# ---------------------------------------------------------------------------


def test_retrieve_returns_full_record(authenticated_client):
    customer = CustomerFactory(scored=True)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(detail_url(customer.pk))

    assert response.status_code == 200
    assert response.data["client_id"] == customer.client_id
    assert response.data["risk_score"] == "0.42"
    assert response.data["fraud_risk_flag"] == "Low"
    assert response.data["cross_sell_score"] == "0.75"


def test_retrieve_absent_scores_are_null(authenticated_client):
    """FR-006."""
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(detail_url(customer.pk))

    assert response.data["risk_score"] is None
    assert response.data["cross_sell_score"] is None


def test_retrieve_nonexistent_returns_404(authenticated_client):
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(detail_url(999999)).status_code == 404


@pytest.mark.parametrize("role", NO_VIEW_ROLES)
def test_retrieve_by_unpermitted_role_returns_404_not_403(authenticated_client, role):
    """
    FR-022: a 403 here would confirm the record exists. The refusal must be
    indistinguishable from a nonexistent record.
    """
    customer = CustomerFactory()
    client, _ = authenticated_client(role)

    assert client.get(detail_url(customer.pk)).status_code == 404


def test_retrieve_unauthenticated_returns_404(api_client):
    customer = CustomerFactory()

    assert api_client.get(detail_url(customer.pk)).status_code == 404


# ---------------------------------------------------------------------------
# T032: archived invisibility (FR-020)
# ---------------------------------------------------------------------------


def test_archived_customer_absent_from_list(authenticated_client):
    live = CustomerFactory()
    CustomerFactory(archived=True)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(LIST_URL)

    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == live.pk


def test_archived_customer_absent_from_search(authenticated_client):
    CustomerFactory(name="Ghost Person", archived=True)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(LIST_URL, {"search": "Ghost"}).data["count"] == 0


def test_archived_customer_returns_404_on_detail(authenticated_client):
    customer = CustomerFactory(archived=True)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(detail_url(customer.pk)).status_code == 404


# ---------------------------------------------------------------------------
# T039 - T042: write operations
# ---------------------------------------------------------------------------


def test_create_returns_201_with_generated_reference(authenticated_client):
    """FR-005."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.post(LIST_URL, VALID_PAYLOAD, format="json")

    assert response.status_code == 201
    assert response.data["client_id"].startswith("CL-")


def test_created_customer_is_immediately_retrievable(authenticated_client):
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    created = client.post(LIST_URL, VALID_PAYLOAD, format="json").data

    assert client.get(detail_url(created["id"])).status_code == 200


def test_created_customer_has_null_scores(authenticated_client):
    """FR-006: absent, not zero."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.post(LIST_URL, VALID_PAYLOAD, format="json")

    assert response.data["risk_score"] is None
    assert response.data["fraud_risk_flag"] is None
    assert response.data["cross_sell_score"] is None


@pytest.mark.parametrize(
    "field,bad_value",
    [("age", 17), ("age", 121), ("email", "not-an-email"), ("name", ""), ("gender", "Unknown")],
)
def test_create_with_invalid_field_refused_naming_field(authenticated_client, field, bad_value):
    """FR-014."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    payload = dict(VALID_PAYLOAD, **{field: bad_value})

    response = client.post(LIST_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data


def test_create_with_shared_email_accepted(authenticated_client):
    """FR-004."""
    CustomerFactory(email="shared@example.com")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.post(LIST_URL, dict(VALID_PAYLOAD, email="shared@example.com"), format="json")

    assert response.status_code == 201


def test_create_with_duplicate_client_id_refused(authenticated_client):
    """FR-003."""
    CustomerFactory(client_id="CL-00042")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.post(LIST_URL, dict(VALID_PAYLOAD, client_id="CL-00042"), format="json")

    assert response.status_code == 400
    assert "client_id" in response.data


def test_partial_update_changes_only_named_field(authenticated_client):
    """FR-016."""
    customer = CustomerFactory(name="Original Name", email="orig@example.com", phone="111-1111")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.patch(detail_url(customer.pk), {"phone": "999-9999"}, format="json")

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.phone == "999-9999"
    assert customer.name == "Original Name"
    assert customer.email == "orig@example.com"


def test_partial_update_with_invalid_value_refused(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.patch(detail_url(customer.pk), {"age": 5}, format="json")

    assert response.status_code == 400
    assert "age" in response.data


def test_patch_to_conflicting_client_id_refused(authenticated_client):
    """FR-003."""
    CustomerFactory(client_id="CL-00100")
    target = CustomerFactory(client_id="CL-00101")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.patch(detail_url(target.pk), {"client_id": "CL-00100"}, format="json")

    assert response.status_code == 400
    assert "client_id" in response.data


def test_delete_archives_rather_than_destroys(authenticated_client):
    """FR-020."""
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.delete(detail_url(customer.pk))

    assert response.status_code == 204
    assert not Customer.objects.filter(pk=customer.pk).exists()
    assert Customer.all_objects.filter(pk=customer.pk).exists()
    assert Customer.all_objects.get(pk=customer.pk).archived_at is not None


def test_delete_is_terminal_second_delete_404s(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    client.delete(detail_url(customer.pk))

    assert client.delete(detail_url(customer.pk)).status_code == 404


def test_delete_reserves_client_id(authenticated_client):
    """FR-021."""
    customer = CustomerFactory(client_id="CL-00500")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    client.delete(detail_url(customer.pk))

    response = client.post(LIST_URL, dict(VALID_PAYLOAD, client_id="CL-00500"), format="json")

    assert response.status_code == 400
    assert "client_id" in response.data


# ---------------------------------------------------------------------------
# T062: placeholder removed (FR-043, SC-010)
# ---------------------------------------------------------------------------


def test_placeholder_route_is_gone(authenticated_client):
    """SC-010: no route serves a fixed non-record response."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get("/api/customers/placeholder/").status_code == 404
