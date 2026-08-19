"""
RBAC tests sweeping all nine roles against every risk operation (T040-T045,
FR-042 through FR-047, SC-009, SC-010).

views.py already wires VIEW_ROLES/RECOMPUTE_ROLES (see its module
docstring) since US1 alone was not judged a safe increment -- these tests
are the independent verification that the wiring is correct.
"""
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

from ..factories import RiskAssessmentFactory, RiskFactorFactory

pytestmark = pytest.mark.django_db

URL = "/api/risk/assessments/"

ALL_ROLES = list(Role)

READ_PERMITTED = {
    Role.RISK_MANAGER,
    Role.UNDERWRITER,
    Role.FRAUD_ANALYST,
    Role.COMPLIANCE_OFFICER,
    Role.SYSTEM_ADMINISTRATOR,
}

RECOMPUTE_PERMITTED = {Role.RISK_MANAGER, Role.SYSTEM_ADMINISTRATOR}


def full_assessment(**overrides):
    assessment = RiskAssessmentFactory(**overrides)
    for factor in ("age", "policy_type", "claims_history", "claims_ratio", "denied_claim"):
        RiskFactorFactory(assessment=assessment, factor=factor)
    return assessment


def scoreable_customer():
    customer = CustomerFactory(age=22)
    policy = PolicyFactory(customer=customer, policy_type="Auto", premium_usd=Decimal("1000.00"))
    ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00"))
    return customer


class TestReadRoleSweep:
    """FR-042, SC-009: exactly the five view roles may read."""

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_list_route(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        full_assessment()

        response = client.get(URL)

        if role in READ_PERMITTED:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_retrieve_route(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        assessment = full_assessment()

        response = client.get(f"{URL}{assessment.id}/")

        if role in READ_PERMITTED:
            assert response.status_code == 200
        else:
            assert response.status_code == 404

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_by_customer_route(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        assessment = full_assessment()

        response = client.get(f"{URL}by-customer/{assessment.customer_id}/")

        if role in READ_PERMITTED:
            assert response.status_code == 200
        else:
            # by-customer is a collection route (no lookup kwarg), so
            # HasRole.has_permission is authoritative here and returns the
            # ordinary 403 rather than deferring to the object-level 404
            # non-disclosure path detail routes use.
            assert response.status_code == 403


class TestCustomerServiceDivergence:
    """
    research §7: Customer Service reads customers but not risk
    assessments -- the divergence that makes the fourth registry entry
    meaningful.
    """

    def test_customer_service_cannot_read_assessment(self, authenticated_client):
        client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
        assessment = full_assessment()

        response = client.get(f"{URL}{assessment.id}/")

        assert response.status_code == 404

    def test_customer_service_can_read_the_customer(self, authenticated_client):
        client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
        assessment = full_assessment()

        response = client.get(f"/api/customers/{assessment.customer_id}/")

        assert response.status_code == 200


class TestRecomputeRoleSweep:
    """FR-043: Underwriter (and every other read-only role) may read but not recompute."""

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_recompute_route(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        customer = scoreable_customer()

        response = client.post(f"{URL}recompute/", {"customer": customer.id}, format="json")

        if role in RECOMPUTE_PERMITTED:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_underwriter_refused_recompute_changes_no_score(self, authenticated_client):
        client, _ = authenticated_client(Role.UNDERWRITER)
        customer = scoreable_customer()

        response = client.post(f"{URL}recompute/", {"customer": customer.id}, format="json")

        assert response.status_code == 403

        from ..models import RiskAssessment

        assert not RiskAssessment.objects.filter(customer=customer).exists()


class TestNonDisclosure:
    """FR-045, SC-010: refusal body is identical whether or not the record exists."""

    def test_unpermitted_response_identical_for_existing_and_missing(self, authenticated_client):
        client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
        existing = full_assessment()

        response_existing = client.get(f"{URL}{existing.id}/")
        response_missing = client.get(f"{URL}999999/")

        assert response_existing.status_code == response_missing.status_code == 404
        assert response_existing.data == response_missing.data


class TestUnauthenticated:
    """
    FR-046. SessionAuthentication issues no WWW-Authenticate challenge, so
    the platform convention throughout (see apps.claims.tests.test_
    permissions) is 403 on collection routes and 404 on detail routes,
    not 401 -- refused either way.
    """

    def test_unauthenticated_refused_on_list(self, api_client):
        assert api_client.get(URL).status_code == 403

    def test_unauthenticated_refused_on_detail(self, api_client):
        assert api_client.get(f"{URL}1/").status_code == 404

    def test_unauthenticated_refused_on_recompute(self, api_client):
        response = api_client.post(f"{URL}recompute/", {"customer": 1}, format="json")
        assert response.status_code == 403


class TestNoWriteAccessLeakage:
    """
    FR-047: holding a risk read role must not, BY ITSELF, grant write
    access to customer/policy/claim records. Roles that already hold
    write access to a module on that module's own terms (System
    Administrator everywhere; Underwriter on policies) are excluded --
    proving those roles can still write would show nothing about risk.
    """

    @pytest.mark.parametrize("role", READ_PERMITTED - {Role.SYSTEM_ADMINISTRATOR})
    def test_risk_read_role_cannot_write_customer(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        customer = CustomerFactory()

        response = client.patch(
            f"/api/customers/{customer.id}/", {"name": "Changed"}, format="json"
        )

        assert response.status_code in (403, 404)

    @pytest.mark.parametrize(
        "role", READ_PERMITTED - {Role.SYSTEM_ADMINISTRATOR, Role.UNDERWRITER}
    )
    def test_risk_read_role_cannot_write_policy(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        policy = PolicyFactory()

        response = client.patch(
            f"/api/policies/{policy.id}/", {"premium_usd": "999.99"}, format="json"
        )

        assert response.status_code in (403, 404)

    @pytest.mark.parametrize("role", READ_PERMITTED - {Role.SYSTEM_ADMINISTRATOR})
    def test_risk_read_role_cannot_write_claim(self, authenticated_client, role):
        client, _ = authenticated_client(role)
        claim = ClaimFactory()

        response = client.patch(
            f"/api/claims/{claim.id}/", {"claim_status": "Approved"}, format="json"
        )

        assert response.status_code in (403, 404)
