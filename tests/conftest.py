import pytest
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_in_role():
    def _make(role, **kwargs):
        return UserFactory(role=role, **kwargs)

    return _make


@pytest.fixture
def authenticated_client(api_client, user_in_role):
    def _make(role, **kwargs):
        user = user_in_role(role, **kwargs)
        api_client.force_authenticate(user=user)
        return api_client, user

    return _make
