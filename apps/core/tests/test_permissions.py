import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role
from apps.core.permissions import HasRole

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


class AnonymousUser:
    is_authenticated = False


def _drf_request(user):
    request = Request(factory.get("/"))
    request.user = user
    return request


def test_unauthenticated_denied():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    request = _drf_request(AnonymousUser())

    assert permission.has_permission(request, None) is False


def test_wrong_role_denied():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.CLAIMS_ADJUSTER)
    request = _drf_request(user)

    assert permission.has_permission(request, None) is False


def test_correct_role_allowed():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.SYSTEM_ADMINISTRATOR)
    request = _drf_request(user)

    assert permission.has_permission(request, None) is True


@pytest.mark.parametrize("role", [None, "", "not-a-real-role"])
def test_null_blank_or_unrecognised_role_denied(role):
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.SYSTEM_ADMINISTRATOR)
    user.role = role
    request = _drf_request(user)

    assert permission.has_permission(request, None) is False


def test_superuser_with_non_permitted_role_still_denied():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.CLAIMS_ADJUSTER, is_superuser=True)
    request = _drf_request(user)

    assert permission.has_permission(request, None) is False


def test_has_object_permission_raises_not_found_for_unauthenticated():
    from rest_framework.exceptions import NotFound

    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    request = _drf_request(AnonymousUser())

    with pytest.raises(NotFound):
        permission.has_object_permission(request, None, object())


def test_has_object_permission_raises_not_found_for_wrong_role():
    from rest_framework.exceptions import NotFound

    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.CLAIMS_ADJUSTER)
    request = _drf_request(user)

    with pytest.raises(NotFound):
        permission.has_object_permission(request, None, object())


def test_has_object_permission_true_for_correct_role():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.SYSTEM_ADMINISTRATOR)
    request = _drf_request(user)

    assert permission.has_object_permission(request, None, object()) is True


class _DetailView:
    lookup_url_kwarg = None
    lookup_field = "pk"

    def __init__(self, kwargs):
        self.kwargs = kwargs


def test_has_permission_defers_to_object_check_on_detail_route_for_unauthenticated():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    request = _drf_request(AnonymousUser())
    view = _DetailView(kwargs={"pk": 1})

    assert permission.has_permission(request, view) is True


def test_has_permission_defers_to_object_check_on_detail_route_for_wrong_role():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    user = UserFactory(role=Role.CLAIMS_ADJUSTER)
    request = _drf_request(user)
    view = _DetailView(kwargs={"pk": 1})

    assert permission.has_permission(request, view) is True


def test_has_permission_still_denies_on_collection_route_with_view_present():
    permission = HasRole(Role.SYSTEM_ADMINISTRATOR)()
    request = _drf_request(AnonymousUser())
    view = _DetailView(kwargs={})

    assert permission.has_permission(request, view) is False
