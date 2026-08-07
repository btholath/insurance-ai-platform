"""
The authoritative FR-024 permission matrix (T047 - T050, SC-005).

Every one of the nine roles, plus the unauthenticated case, is exercised
against every customer operation. This is the proof SC-005 asks for; the
targeted checks in test_views.py are a convenience, this is the record.

Two behaviours are deliberate rather than accidental:

- Collection-route refusals are 403; detail-route refusals are 404. A 403
  on a detail route would confirm the record exists (FR-022).
- Superuser status grants nothing. Only role is consulted (FR-026).
"""
import pytest

from apps.accounts.models import Role
from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db

LIST_URL = "/api/customers/"

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

# FR-024, transcribed directly from the spec table.
CAN_VIEW = {
    Role.CUSTOMER_SERVICE: True,
    Role.UNDERWRITER: True,
    Role.SYSTEM_ADMINISTRATOR: True,
    Role.CLAIMS_ADJUSTER: True,
    Role.FRAUD_ANALYST: True,
    Role.RISK_MANAGER: True,
    Role.COMPLIANCE_OFFICER: True,
    Role.PRODUCT_MANAGER: False,
    Role.EXECUTIVE_LEADERSHIP: False,
}
CAN_WRITE = {role: role in (Role.CUSTOMER_SERVICE, Role.SYSTEM_ADMINISTRATOR) for role in ALL_ROLES}

PAYLOAD = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "555-0100",
    "age": 36,
    "gender": "Female",
    "location": "London",
    "lead_source": "Referral",
}


def detail_url(pk):
    return f"/api/customers/{pk}/"


# ---------------------------------------------------------------------------
# T047: the full matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ALL_ROLES)
def test_list_matches_matrix(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.get(LIST_URL)

    assert response.status_code == (200 if CAN_VIEW[role] else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_retrieve_matches_matrix(authenticated_client, role):
    customer = CustomerFactory()
    client, _ = authenticated_client(role)

    response = client.get(detail_url(customer.pk))

    # Detail refusals are 404, never 403 (FR-022).
    assert response.status_code == (200 if CAN_VIEW[role] else 404)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_create_matches_matrix(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.post(LIST_URL, PAYLOAD, format="json")

    assert response.status_code == (201 if CAN_WRITE[role] else 403)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_patch_matches_matrix(authenticated_client, role):
    customer = CustomerFactory(phone="111-1111")
    client, _ = authenticated_client(role)

    response = client.patch(detail_url(customer.pk), {"phone": "999-9999"}, format="json")

    if CAN_WRITE[role]:
        assert response.status_code == 200
    else:
        assert response.status_code == 404
        customer.refresh_from_db()
        assert customer.phone == "111-1111"  # data unchanged


@pytest.mark.parametrize("role", ALL_ROLES)
def test_delete_matches_matrix(authenticated_client, role):
    customer = CustomerFactory()
    client, _ = authenticated_client(role)

    response = client.delete(detail_url(customer.pk))

    if CAN_WRITE[role]:
        assert response.status_code == 204
    else:
        assert response.status_code == 404
        assert Customer.objects.filter(pk=customer.pk).exists()  # data unchanged


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------


def test_anonymous_refused_on_list(api_client):
    assert api_client.get(LIST_URL).status_code == 403


def test_anonymous_refused_on_detail_without_disclosure(api_client):
    """FR-022: must not reveal whether the customer exists."""
    customer = CustomerFactory()

    assert api_client.get(detail_url(customer.pk)).status_code == 404


def test_anonymous_refused_on_create(api_client):
    assert api_client.post(LIST_URL, PAYLOAD, format="json").status_code == 403


def test_anonymous_refused_on_delete(api_client):
    customer = CustomerFactory()

    assert api_client.delete(detail_url(customer.pk)).status_code == 404
    assert Customer.objects.filter(pk=customer.pk).exists()


# ---------------------------------------------------------------------------
# T048: superuser does not bypass (FR-026)
# ---------------------------------------------------------------------------


def test_superuser_with_unpermitted_role_still_refused_on_list(authenticated_client):
    """
    FR-026: System Administrator access comes from the role, not from
    is_superuser. A superuser whose role cannot view customers cannot view
    customers.
    """
    client, user = authenticated_client(Role.PRODUCT_MANAGER, is_superuser=True, is_staff=True)

    assert user.is_superuser is True
    assert client.get(LIST_URL).status_code == 403


def test_superuser_with_unpermitted_role_still_refused_on_detail(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP, is_superuser=True)

    assert client.get(detail_url(customer.pk)).status_code == 404


def test_superuser_with_view_only_role_still_refused_on_write(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.UNDERWRITER, is_superuser=True)

    assert client.delete(detail_url(customer.pk)).status_code == 404
    assert Customer.objects.filter(pk=customer.pk).exists()


# ---------------------------------------------------------------------------
# T049: role changes take effect immediately (FR-025)
# ---------------------------------------------------------------------------


def test_role_change_takes_effect_on_next_request(authenticated_client, api_client):
    """
    FR-025: the decision reflects the role as it stands at the moment of the
    request.

    Note the Phase 1 force_authenticate staleness gotcha -- the client holds
    a reference to the user object, so the role must be changed on that
    instance (or the client re-authenticated) rather than only in the
    database, otherwise this passes vacuously against a stale copy.
    """
    client, user = authenticated_client(Role.PRODUCT_MANAGER)
    assert client.get(LIST_URL).status_code == 403

    user.role = Role.CUSTOMER_SERVICE
    user.save()
    client.force_authenticate(user=user)

    assert client.get(LIST_URL).status_code == 200


def test_role_revocation_takes_effect_on_next_request(authenticated_client):
    client, user = authenticated_client(Role.CUSTOMER_SERVICE)
    assert client.get(LIST_URL).status_code == 200

    user.role = Role.EXECUTIVE_LEADERSHIP
    user.save()
    client.force_authenticate(user=user)

    assert client.get(LIST_URL).status_code == 403


def test_write_permission_revocation_takes_effect(authenticated_client):
    customer = CustomerFactory()
    client, user = authenticated_client(Role.CUSTOMER_SERVICE)

    user.role = Role.UNDERWRITER
    user.save()
    client.force_authenticate(user=user)

    assert client.delete(detail_url(customer.pk)).status_code == 404


# ---------------------------------------------------------------------------
# T050: route-shape asymmetry is deliberate (FR-022)
# ---------------------------------------------------------------------------


def test_collection_refusal_is_403_detail_refusal_is_404(authenticated_client):
    """
    Documents the asymmetry so it is not later "fixed" into consistency.
    A 403 on the detail route would confirm the record exists.
    """
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    assert client.get(LIST_URL).status_code == 403
    assert client.get(detail_url(customer.pk)).status_code == 404


def test_detail_refusal_indistinguishable_from_nonexistent(authenticated_client):
    """FR-022: the two cases must look identical to the caller."""
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    refused = client.get(detail_url(customer.pk))
    absent = client.get(detail_url(999999))

    assert refused.status_code == absent.status_code == 404
