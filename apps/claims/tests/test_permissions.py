"""
RBAC across all nine roles (FR-025 through FR-028, FR-047, SC-005, SC-006).

Constitution Principle III is NON-NEGOTIABLE, and claims carry both
financial detail and fraud-investigation relevance, so an over-broad
default here is a compliance failure rather than a convenience.

The sharp case this file pins: an Underwriter may WRITE policies but may
not READ claims. Their 404 on a claim is a refusal; their 404 on a policy
is an ordinary miss. That is precisely the distinction the per-module
audit registry exists to make.
"""
import pytest

from apps.accounts.models import Role
from apps.claims.factories import ClaimFactory, ClaimLoadAnomalyFactory
from apps.claims.models import Claim
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db

URL = "/api/claims/"
ANOMALY_URL = "/api/claims/anomalies/"

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

READ_ROLES = [
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.COMPLIANCE_OFFICER,
    Role.RISK_MANAGER,
    Role.SYSTEM_ADMINISTRATOR,
]
WRITE_ROLES = [Role.CLAIMS_ADJUSTER, Role.SYSTEM_ADMINISTRATOR]

NO_READ_ROLES = [r for r in ALL_ROLES if r not in READ_ROLES]
NO_WRITE_ROLES = [r for r in ALL_ROLES if r not in WRITE_ROLES]

# Read-permitted but write-refused. Fraud Analyst is the substantive case:
# investigation is not adjudication.
READ_BUT_NOT_WRITE = [r for r in READ_ROLES if r not in WRITE_ROLES]


def test_the_role_sets_are_the_expected_sizes():
    """
    Guards the deliberate narrowing. Five read roles, against Customer's
    seven and Policy's eight; two write roles, a third distinct write set.
    """
    assert len(READ_ROLES) == 5
    assert len(WRITE_ROLES) == 2
    assert len(ALL_ROLES) == 9


# -- Unauthenticated (FR-025) ----------------------------------------------


def test_unauthenticated_refused_on_list(api_client):
    assert api_client.get(URL).status_code == 403


def test_unauthenticated_refused_on_detail(api_client):
    claim = ClaimFactory()

    assert api_client.get(f"{URL}{claim.id}/").status_code == 404


def test_unauthenticated_refused_on_create(api_client):
    response = api_client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )

    assert response.status_code == 403
    assert Claim.objects.count() == 0


def test_unauthenticated_refused_on_anomalies(api_client):
    assert api_client.get(ANOMALY_URL).status_code == 403


# -- Reads (FR-026, SC-005) ------------------------------------------------


@pytest.mark.parametrize("role", READ_ROLES)
def test_read_permitted_roles_get_200(authenticated_client, role):
    client, _ = authenticated_client(role)
    ClaimFactory()

    assert client.get(URL).status_code == 200


@pytest.mark.parametrize("role", NO_READ_ROLES)
def test_read_refused_roles_get_403_on_collection(authenticated_client, role):
    client, _ = authenticated_client(role)
    ClaimFactory()

    assert client.get(URL).status_code == 403


def test_underwriter_may_not_read_claims(authenticated_client):
    """
    Explicit because it is the counter-intuitive one: an Underwriter writes
    policies but has no claim access at all.
    """
    client, _ = authenticated_client(Role.UNDERWRITER)
    ClaimFactory()

    assert client.get(URL).status_code == 403


def test_customer_service_may_not_read_claims(authenticated_client):
    """Servicing an account does not require the claim ledger."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    assert client.get(URL).status_code == 403


# -- Writes (FR-027, SC-005) -----------------------------------------------


@pytest.mark.parametrize("role", WRITE_ROLES)
def test_write_permitted_roles_can_create(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.parametrize("role", NO_WRITE_ROLES)
def test_write_refused_roles_cannot_create_and_store_nothing(authenticated_client, role):
    client, _ = authenticated_client(role)

    response = client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )

    assert response.status_code == 403
    assert Claim.objects.count() == 0


@pytest.mark.parametrize("role", READ_BUT_NOT_WRITE)
def test_read_only_roles_cannot_amend(authenticated_client, role):
    """FR-027: refused even to roles permitted to READ claims."""
    client, _ = authenticated_client(role)
    claim = ClaimFactory(claim_status="Filed")

    response = client.patch(
        f"{URL}{claim.id}/", {"claim_status": "Approved"}, format="json"
    )

    assert response.status_code == 404  # detail route: non-disclosure
    claim.refresh_from_db()
    assert claim.claim_status == "Filed"


@pytest.mark.parametrize("role", READ_BUT_NOT_WRITE)
def test_read_only_roles_cannot_remove(authenticated_client, role):
    client, _ = authenticated_client(role)
    claim = ClaimFactory()

    response = client.delete(f"{URL}{claim.id}/")

    assert response.status_code == 404
    claim.refresh_from_db()
    assert claim.archived_at is None


def test_fraud_analyst_reads_but_does_not_write(authenticated_client):
    """Explicit: investigation is not adjudication."""
    client, _ = authenticated_client(Role.FRAUD_ANALYST)
    claim = ClaimFactory()

    assert client.get(URL).status_code == 200
    assert client.delete(f"{URL}{claim.id}/").status_code == 404


# -- Non-disclosure (FR-028, SC-006) ---------------------------------------


@pytest.mark.parametrize("role", NO_READ_ROLES)
def test_existing_and_missing_claims_are_indistinguishable(authenticated_client, role):
    """
    SC-006: a caller not permitted to read claims cannot distinguish, from
    the response alone, a claim that exists from one that does not.
    """
    client, _ = authenticated_client(role)
    claim = ClaimFactory()

    existing = client.get(f"{URL}{claim.id}/")
    missing = client.get(f"{URL}999999/")

    assert existing.status_code == 404
    assert missing.status_code == 404
    assert existing.data == missing.data


@pytest.mark.parametrize("role", READ_ROLES)
def test_permitted_roles_get_404_for_genuinely_missing_claims(authenticated_client, role):
    client, _ = authenticated_client(role)

    assert client.get(f"{URL}999999/").status_code == 404


# -- Anomalies inherit the claim read set (FR-047) -------------------------


@pytest.mark.parametrize("role", READ_ROLES)
def test_anomaly_read_permitted_roles_get_200(authenticated_client, role):
    client, _ = authenticated_client(role)
    ClaimLoadAnomalyFactory()

    assert client.get(ANOMALY_URL).status_code == 200


@pytest.mark.parametrize("role", NO_READ_ROLES)
def test_anomaly_read_refused_roles_get_403(authenticated_client, role):
    """
    An anomaly discloses claim-adjacent financial detail -- the amount the
    source carried -- so it cannot be readable by anyone who may not read
    claims.
    """
    client, _ = authenticated_client(role)
    ClaimLoadAnomalyFactory()

    assert client.get(ANOMALY_URL).status_code == 403


@pytest.mark.parametrize("role", NO_READ_ROLES)
def test_anomaly_detail_non_disclosure(authenticated_client, role):
    client, _ = authenticated_client(role)
    anomaly = ClaimLoadAnomalyFactory()

    existing = client.get(f"{ANOMALY_URL}{anomaly.id}/")
    missing = client.get(f"{ANOMALY_URL}999999/")

    assert existing.status_code == 404
    assert existing.data == missing.data
