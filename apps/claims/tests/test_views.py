import pytest

from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

URL = "/api/claims/placeholder/"
PERMITTED_ROLES = [Role.CLAIMS_ADJUSTER, Role.FRAUD_ANALYST, Role.SYSTEM_ADMINISTRATOR]
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
REFUSED_ROLES = [role for role in ALL_ROLES if role not in PERMITTED_ROLES]


def test_unauthenticated_refused_403(api_client):
    response = api_client.get(URL)

    assert response.status_code == 403


@pytest.mark.parametrize("role", PERMITTED_ROLES)
def test_permitted_roles_allowed_200(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.get(URL)

    assert response.status_code == 200
    assert response.data == {"module": "claims", "status": "placeholder"}


@pytest.mark.parametrize("role", REFUSED_ROLES)
def test_other_roles_refused_403(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.get(URL)

    assert response.status_code == 403
