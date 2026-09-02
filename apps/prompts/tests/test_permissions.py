"""
RBAC for the prompt library (T035-T037, US3).

The fifth distinct role shape on the platform, and a new one in both halves:
nine view roles (a first -- universal) and one write role (also a first;
every existing module pairs a business role with System Administrator).
"""
import pytest
from django.urls import reverse

from apps.accounts.models import Role

LIST_URL = "/api/prompts/templates/"
DETAIL_URL = "/api/prompts/templates/risk_assessment_summary/"


@pytest.mark.django_db
@pytest.mark.parametrize("role", [r.value for r in Role])
def test_all_nine_roles_may_read(authenticated_client, role):
    """
    FR-012. EVERY role reads -- the platform's first universal view set,
    against Customer's 7, Policy's 8, Claim's 5 and Risk's 5.

    A prompt template holds field NAMES, never field VALUES. It describes what
    a future narrative may draw on and discloses nothing about any customer,
    so the restrictions that make those four sets narrow have nothing to
    protect here.

    EXECUTIVE LEADERSHIP RETURNING 200 IS THE SIGNAL THAT MATTERS. It is
    excluded from all four existing view sets. A 403 there would mean this
    role set was copied from a neighbouring module rather than chosen for this
    one -- which is exactly what FR-013's "own role sets" language exists to
    prevent.
    """
    client, _user = authenticated_client(role)

    assert client.get(LIST_URL).status_code == 200
    assert client.get(DETAIL_URL).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role", [r.value for r in Role if r != Role.SYSTEM_ADMINISTRATOR]
)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_are_refused_for_non_admin_roles(
    authenticated_client, role, method
):
    """
    FR-012. Phase 4a exposes no write route at all (the library is
    code-resident), so every write method is refused for everyone -- but the
    refusal must be a REFUSAL for the eight non-admin roles, classified
    against this module's own write role set.

    405 is acceptable alongside 403/404: DRF rejects an unrouted method before
    permissions in some configurations. What must never happen is a 2xx.
    """
    client, _user = authenticated_client(role)

    for url in (LIST_URL, DETAIL_URL):
        response = getattr(client, method)(url)
        assert response.status_code in (403, 404, 405), (
            f"{method.upper()} {url} as {role} returned "
            f"{response.status_code}; no write may succeed in Phase 4a"
        )


@pytest.mark.django_db
def test_unauthenticated_is_refused(api_client):
    """
    The two shapes differ BY DESIGN, per apps/core/permissions.py:16-30:

      - collection route -> 403, from has_permission() returning False
      - detail route     -> 404, from has_object_permission() raising
                            NotFound, so a 403 cannot confirm the record
                            exists (existence non-disclosure)

    Asserted explicitly rather than as "not 200", because collapsing the two
    would silently lose the non-disclosure property.
    """
    assert api_client.get(LIST_URL).status_code in (401, 403)
    assert api_client.get(DETAIL_URL).status_code == 404
