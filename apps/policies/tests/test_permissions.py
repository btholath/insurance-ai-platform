"""
Policy RBAC tests (T043, T053, T062 - T065).

The permission matrix is FR-026, and SC-005 requires every role tried
against every operation. Two differences from the customer module are
deliberate and pinned here so neither is later "harmonized" away:

- Writes are Underwriter + System Administrator, not Customer Service.
- Product Manager may READ policies though they may not read customers.

Refusal status depends on route shape, inherited from HasRole: collection
routes 403, detail routes 404 so a refusal is indistinguishable from a
nonexistent record (FR-023).
"""
import pytest

from apps.accounts.models import Role
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory
from apps.policies.models import Policy

pytestmark = pytest.mark.django_db

URL = "/api/policies/"


def detail(policy_id):
    return f"{URL}{policy_id}/"


VIEW_ROLES = [
    Role.CUSTOMER_SERVICE,
    Role.SYSTEM_ADMINISTRATOR,
    Role.UNDERWRITER,
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.RISK_MANAGER,
    Role.COMPLIANCE_OFFICER,
    Role.PRODUCT_MANAGER,
]
WRITE_ROLES = [Role.UNDERWRITER, Role.SYSTEM_ADMINISTRATOR]
ALL_ROLES = VIEW_ROLES + [Role.EXECUTIVE_LEADERSHIP]
READ_ONLY_ROLES = [r for r in VIEW_ROLES if r not in WRITE_ROLES]


def payload(customer, **overrides):
    data = {
        "customer": customer.pk,
        "policy_type": "Health",
        "start_date": "2026-01-01",
        "end_date": "2027-01-01",
        "premium_usd": "1200.00",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# T043: read permissions (FR-026)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", VIEW_ROLES)
def test_viewing_roles_get_200_on_list(authenticated_client, role):
    PolicyFactory()
    client, _ = authenticated_client(role)

    assert client.get(URL).status_code == 200


def test_executive_leadership_gets_403_on_the_collection(authenticated_client):
    PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    assert client.get(URL).status_code == 403


def test_anonymous_gets_403_on_the_collection(api_client):
    PolicyFactory()

    assert api_client.get(URL).status_code == 403


@pytest.mark.parametrize("role", VIEW_ROLES)
def test_viewing_roles_get_200_on_detail(authenticated_client, role):
    policy = PolicyFactory()
    client, _ = authenticated_client(role)

    assert client.get(detail(policy.id)).status_code == 200


def test_executive_leadership_gets_404_on_detail(authenticated_client):
    """Detail routes 404 rather than 403 so refusal is non-disclosing."""
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    assert client.get(detail(policy.id)).status_code == 404


def test_anonymous_gets_404_on_detail(api_client):
    policy = PolicyFactory()

    assert api_client.get(detail(policy.id)).status_code == 404


# ---------------------------------------------------------------------------
# T053: write permissions -- the reverse of the customer module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", WRITE_ROLES)
def test_writing_roles_may_create(authenticated_client, role):
    customer = CustomerFactory()
    client, _ = authenticated_client(role)

    assert client.post(URL, payload(customer), format="json").status_code == 201


@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_view_only_roles_may_not_create(authenticated_client, role):
    """Collection route, so 403 rather than 404."""
    customer = CustomerFactory()
    client, _ = authenticated_client(role)

    response = client.post(URL, payload(customer), format="json")

    assert response.status_code == 403
    assert Policy.all_objects.count() == 0


@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_view_only_roles_may_not_patch_and_data_is_unchanged(authenticated_client, role):
    policy = PolicyFactory()
    original = policy.premium_usd
    client, _ = authenticated_client(role)

    response = client.patch(detail(policy.id), {"premium_usd": "1.00"}, format="json")

    assert response.status_code == 404
    policy.refresh_from_db()
    assert policy.premium_usd == original


@pytest.mark.parametrize("role", READ_ONLY_ROLES)
def test_view_only_roles_may_not_delete_and_data_is_unchanged(authenticated_client, role):
    policy = PolicyFactory()
    client, _ = authenticated_client(role)

    response = client.delete(detail(policy.id))

    assert response.status_code == 404
    policy.refresh_from_db()
    assert policy.archived_at is None


def test_customer_service_may_read_but_not_write_policies(authenticated_client):
    """
    The headline reversal: Customer Service writes customers but only
    reads policies.
    """
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(URL).status_code == 200
    assert client.patch(detail(policy.id), {"premium_usd": "1.00"}, format="json").status_code == 404


# ---------------------------------------------------------------------------
# T062: the exhaustive matrix (SC-005)
# ---------------------------------------------------------------------------


def _expected(role, operation):
    """The FR-026 table, expressed once."""
    if operation == "list":
        return 200 if role in VIEW_ROLES else 403
    if operation == "retrieve":
        return 200 if role in VIEW_ROLES else 404
    if operation == "create":
        return 201 if role in WRITE_ROLES else 403
    # patch and delete are detail routes
    if role in WRITE_ROLES:
        return 200 if operation == "patch" else 204
    return 404


@pytest.mark.parametrize("operation", ["list", "retrieve", "create", "patch", "delete"])
@pytest.mark.parametrize("role", ALL_ROLES)
def test_full_permission_matrix(authenticated_client, role, operation):
    """SC-005: all 9 roles x 5 operations, against the FR-026 table."""
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer, policy_type="Auto")
    client, _ = authenticated_client(role)

    if operation == "list":
        status = client.get(URL).status_code
    elif operation == "retrieve":
        status = client.get(detail(policy.id)).status_code
    elif operation == "create":
        status = client.post(
            URL, payload(customer, policy_type="Life"), format="json"
        ).status_code
    elif operation == "patch":
        status = client.patch(
            detail(policy.id), {"premium_usd": "1350.00"}, format="json"
        ).status_code
    else:
        status = client.delete(detail(policy.id)).status_code

    assert status == _expected(role, operation)


@pytest.mark.parametrize("operation", ["list", "retrieve", "create", "patch", "delete"])
def test_anonymous_across_every_operation(api_client, operation):
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    if operation == "list":
        assert api_client.get(URL).status_code == 403
    elif operation == "create":
        assert api_client.post(URL, payload(customer), format="json").status_code == 403
    elif operation == "retrieve":
        assert api_client.get(detail(policy.id)).status_code == 404
    elif operation == "patch":
        assert api_client.patch(
            detail(policy.id), {"premium_usd": "1.00"}, format="json"
        ).status_code == 404
    else:
        assert api_client.delete(detail(policy.id)).status_code == 404


# ---------------------------------------------------------------------------
# T063: cross-module asymmetry -- the two deliberate divergences
# ---------------------------------------------------------------------------


def test_product_manager_reads_policies_but_not_customers(authenticated_client):
    """
    Product mix is a product concern; individual personal data is not.
    Pinned so neither module is later harmonized into the other.
    """
    PolicyFactory()
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    assert client.get(URL).status_code == 200
    assert client.get("/api/customers/").status_code == 403


def test_customer_service_writes_customers_but_not_policies(authenticated_client):
    """The reverse asymmetry: writing policy terms is underwriting work."""
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(URL).status_code == 200
    assert client.post(
        URL, payload(policy.customer, policy_type="Life"), format="json"
    ).status_code == 403

    # ...but may still write customers.
    assert client.patch(
        f"/api/customers/{policy.customer.id}/", {"name": "Renamed"}, format="json"
    ).status_code == 200


def test_underwriter_writes_policies_but_not_customers(authenticated_client):
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.UNDERWRITER)

    assert client.patch(
        detail(policy.id), {"premium_usd": "1350.00"}, format="json"
    ).status_code == 200
    assert client.patch(
        f"/api/customers/{policy.customer.id}/", {"name": "Renamed"}, format="json"
    ).status_code == 404


# ---------------------------------------------------------------------------
# T064: superuser does not bypass (FR-027)
# ---------------------------------------------------------------------------


def test_superuser_in_a_denied_role_still_gets_403_on_list(authenticated_client):
    """
    Only role is consulted, never is_superuser. A superuser flag must not
    become an unaudited back door into commercial terms.
    """
    PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP, is_superuser=True)

    assert client.get(URL).status_code == 403


def test_superuser_in_a_denied_role_still_gets_404_on_detail(authenticated_client):
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP, is_superuser=True)

    assert client.get(detail(policy.id)).status_code == 404


def test_superuser_in_a_read_only_role_still_cannot_write(authenticated_client):
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.COMPLIANCE_OFFICER, is_superuser=True)

    assert client.delete(detail(policy.id)).status_code == 404
    policy.refresh_from_db()
    assert policy.archived_at is None


# ---------------------------------------------------------------------------
# T065: role freshness (FR-025)
# ---------------------------------------------------------------------------


def test_role_change_takes_effect_on_the_next_request(authenticated_client, api_client):
    """
    FR-025: the role is read fresh per request, never cached across them.

    The user object is re-authenticated after the change rather than
    reused -- force_authenticate pins the instance it was given, so a
    stale in-memory copy would keep the old role and the test would pass
    for the wrong reason.
    """
    PolicyFactory()
    client, user = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    assert client.get(URL).status_code == 403

    user.role = Role.UNDERWRITER
    user.save(update_fields=["role"])

    user.refresh_from_db()
    client.force_authenticate(user=user)

    assert client.get(URL).status_code == 200


def test_revoking_write_access_takes_effect_immediately(authenticated_client):
    policy = PolicyFactory()
    client, user = authenticated_client(Role.UNDERWRITER)

    assert client.patch(
        detail(policy.id), {"premium_usd": "1350.00"}, format="json"
    ).status_code == 200

    user.role = Role.COMPLIANCE_OFFICER
    user.save(update_fields=["role"])
    user.refresh_from_db()
    client.force_authenticate(user=user)

    assert client.patch(
        detail(policy.id), {"premium_usd": "99.00"}, format="json"
    ).status_code == 404
