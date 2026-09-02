"""
Prompt library API response shapes (T041-T043, US3).

Two read routes over an in-memory tuple. The list route carries `bindings` --
FR-011 puts the declared field list on the list route specifically, so the
grounding contract is readable without fetching each template one at a time --
but not `body`, which is detail-only.
"""
import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.prompts import library

LIST_URL = "/api/prompts/templates/"
DETAIL_URL = "/api/prompts/templates/risk_assessment_summary/"


@pytest.mark.django_db
def test_list_returns_every_template_without_body(authenticated_client):
    client, _user = authenticated_client(Role.PRODUCT_MANAGER)

    data = client.get(LIST_URL).json()

    assert data["library_version"] == library.PROMPT_LIBRARY_VERSION
    assert data["count"] == 7
    assert len(data["results"]) == 7

    entry = data["results"][0]
    for field in (
        "identifier",
        "purpose",
        "version",
        "bindings",
        "model_preference",
        "phase0_origin",
        "pii_note",
    ):
        assert field in entry

    # FR-011: the declaration is on the list route.
    assert entry["bindings"]
    assert {"record_type", "field_name", "placeholder"} <= set(entry["bindings"][0])

    # ... but the body is not.
    assert "body" not in entry


@pytest.mark.django_db
def test_detail_returns_the_body(authenticated_client):
    client, _user = authenticated_client(Role.UNDERWRITER)

    data = client.get(DETAIL_URL).json()

    assert data["identifier"] == "risk_assessment_summary"
    assert "body" in data
    assert "{Customer.name}" in data["body"]
    assert data["bindings"]


@pytest.mark.django_db
def test_body_and_bindings_agree_in_the_response(authenticated_client):
    """
    Validation guarantees this at app-ready for the whole library, so a
    response can never carry a body and a declaration that disagree. Asserted
    here at the API boundary too -- this is the pairing Phase 4b consumes.
    """
    client, _user = authenticated_client(Role.RISK_MANAGER)

    data = client.get(DETAIL_URL).json()

    for binding in data["bindings"]:
        assert binding["placeholder"] in data["body"]


@pytest.mark.django_db
def test_list_route_executes_no_queries(
    authenticated_client, django_assert_num_queries
):
    """
    The library is served from an in-memory tuple -- there is no table to
    query (plan.md Performance Goals).

    The request is made once first so session/auth lookups are warm and do not
    count against the assertion; the second call is the one measured.
    """
    client, _user = authenticated_client(Role.CUSTOMER_SERVICE)
    client.get(LIST_URL)  # warm auth

    with django_assert_num_queries(0):
        assert client.get(LIST_URL).status_code == 200


@pytest.mark.django_db
def test_detail_route_404s_on_unknown_identifier(authenticated_client):
    """
    An ORDINARY MISS, not a refusal -- the distinction
    apps/core/exception_handlers.py:50-67 draws. A permitted role asking for a
    template that does not exist gets a 404 and writes NO audit row; logging
    it would turn every mistyped identifier into a permission-refusal record
    and make the compliance trail noise.
    """
    client, _user = authenticated_client(Role.RISK_MANAGER)
    before = AuditLog.objects.filter(target_type="prompts.PromptTemplate").count()

    assert client.get("/api/prompts/templates/no_such_template/").status_code == 404

    after = AuditLog.objects.filter(target_type="prompts.PromptTemplate").count()
    assert after == before
