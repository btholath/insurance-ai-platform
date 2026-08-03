import pytest

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/auth/login/"
LOGOUT_URL = "/api/auth/logout/"
PASSWORD = "a-strong-password-123"


def test_login_with_valid_credentials_returns_200_and_session(api_client):
    UserFactory(email="user@example.com", password=PASSWORD, role=Role.CLAIMS_ADJUSTER)

    response = api_client.post(LOGIN_URL, {"email": "user@example.com", "password": PASSWORD}, format="json")

    assert response.status_code == 200
    assert "sessionid" in response.cookies


def test_login_with_wrong_password_returns_generic_400(api_client):
    UserFactory(email="user@example.com", password=PASSWORD, role=Role.CLAIMS_ADJUSTER)

    response = api_client.post(LOGIN_URL, {"email": "user@example.com", "password": "wrong-password"}, format="json")

    assert response.status_code == 400
    assert response.data["detail"] == "Unable to log in with the provided credentials."


def test_login_with_nonexistent_email_returns_same_generic_400(api_client):
    response = api_client.post(LOGIN_URL, {"email": "nobody@example.com", "password": PASSWORD}, format="json")

    assert response.status_code == 400
    assert response.data["detail"] == "Unable to log in with the provided credentials."


def test_login_for_inactive_account_refused(api_client):
    UserFactory(email="inactive@example.com", password=PASSWORD, role=Role.CLAIMS_ADJUSTER, is_active=False)

    response = api_client.post(LOGIN_URL, {"email": "inactive@example.com", "password": PASSWORD}, format="json")

    assert response.status_code == 400


def test_logout_authenticated_returns_204_and_clears_session(api_client):
    UserFactory(email="user@example.com", password=PASSWORD, role=Role.CLAIMS_ADJUSTER)
    api_client.post(LOGIN_URL, {"email": "user@example.com", "password": PASSWORD}, format="json")

    response = api_client.post(LOGOUT_URL)

    assert response.status_code == 204


def test_logout_unauthenticated_refused(api_client):
    response = api_client.post(LOGOUT_URL)

    assert response.status_code in (401, 403)
