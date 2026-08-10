"""
Policy API tests (T044 - T048, T054 - T057, T078).

Replaces the Phase 1 placeholder tests: that module asserted
{"module": "policies", "status": "placeholder"} and covered nothing else,
so it is replaced rather than amended (FR-049, T077).

Permission behaviour lives in test_permissions.py; this module uses a
writing role throughout and covers shape, filtering, and mutation.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory
from apps.policies.models import Policy

pytestmark = pytest.mark.django_db

URL = "/api/policies/"


def detail(policy_id):
    return f"{URL}{policy_id}/"


@pytest.fixture
def underwriter(authenticated_client):
    client, user = authenticated_client(Role.UNDERWRITER)
    return client


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
# T044: list and pagination (FR-018)
# ---------------------------------------------------------------------------


def test_list_returns_live_policies(underwriter):
    PolicyFactory.create_batch(3)

    response = underwriter.get(URL)

    assert response.status_code == 200
    assert response.data["count"] == 3


def test_list_excludes_archived_policies(underwriter):
    PolicyFactory()
    PolicyFactory(archived=True)

    response = underwriter.get(URL)

    assert response.data["count"] == 1


def test_list_pages_at_fifty(underwriter):
    PolicyFactory.create_batch(55)

    response = underwriter.get(URL)

    assert response.data["count"] == 55
    assert len(response.data["results"]) == 50
    assert response.data["next"] is not None


def test_second_page_holds_the_remainder(underwriter):
    PolicyFactory.create_batch(55)

    response = underwriter.get(URL, {"page": 2})

    assert len(response.data["results"]) == 5
    assert response.data["previous"] is not None


def test_ordering_by_id_is_stable_across_requests(underwriter):
    PolicyFactory.create_batch(10)

    first = [r["id"] for r in underwriter.get(URL).data["results"]]
    second = [r["id"] for r in underwriter.get(URL).data["results"]]

    assert first == second == sorted(first)


def test_list_embeds_the_customer_summary(underwriter):
    customer = CustomerFactory(name="Patrick Hart")
    PolicyFactory(customer=customer)

    row = underwriter.get(URL).data["results"][0]

    assert row["customer"] == {
        "id": customer.id,
        "client_id": customer.client_id,
        "name": "Patrick Hart",
    }


def test_archived_at_is_not_exposed(underwriter):
    PolicyFactory()

    row = underwriter.get(URL).data["results"][0]

    assert "archived_at" not in row


# ---------------------------------------------------------------------------
# T045: customer filter (FR-019)
# ---------------------------------------------------------------------------


def test_customer_filter_returns_only_that_customers_policies(underwriter):
    mine = CustomerFactory()
    PolicyFactory(customer=mine, policy_type="Auto")
    PolicyFactory(customer=mine, policy_type="Life")
    PolicyFactory()  # someone else's

    response = underwriter.get(URL, {"customer": mine.id})

    assert response.data["count"] == 2
    assert {r["customer"]["id"] for r in response.data["results"]} == {mine.id}


def test_customer_filter_matching_nothing_returns_empty_not_error(underwriter):
    PolicyFactory()

    response = underwriter.get(URL, {"customer": 999999})

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["results"] == []


# ---------------------------------------------------------------------------
# T046: type and expiry filters (FR-020)
# ---------------------------------------------------------------------------


def test_policy_type_filter_matches_exactly(underwriter):
    PolicyFactory(policy_type="Auto")
    PolicyFactory(policy_type="Health")

    response = underwriter.get(URL, {"policy_type": "Auto"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["policy_type"] == "Auto"


def test_expired_filter_returns_only_past_end_dates(underwriter):
    PolicyFactory(expired=True)
    PolicyFactory()  # in force

    response = underwriter.get(URL, {"expired": "true"})

    assert response.data["count"] == 1
    assert date.fromisoformat(response.data["results"][0]["end_date"]) < date.today()


def test_expired_false_returns_only_in_force_policies(underwriter):
    PolicyFactory(expired=True)
    PolicyFactory()

    response = underwriter.get(URL, {"expired": "false"})

    assert response.data["count"] == 1
    assert date.fromisoformat(response.data["results"][0]["end_date"]) >= date.today()


def test_a_policy_ending_today_is_not_expired(underwriter):
    """Expiry is end_date < today, so the last day of cover still counts."""
    customer = CustomerFactory()
    PolicyFactory(
        customer=customer,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
    )

    assert underwriter.get(URL, {"expired": "true"}).data["count"] == 0
    assert underwriter.get(URL, {"expired": "false"}).data["count"] == 1


def test_type_and_expiry_filters_combine(underwriter):
    PolicyFactory(policy_type="Auto", expired=True)
    PolicyFactory(policy_type="Health", expired=True)
    PolicyFactory(policy_type="Auto")

    response = underwriter.get(URL, {"policy_type": "Auto", "expired": "true"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["policy_type"] == "Auto"


def test_customer_and_type_filters_combine(underwriter):
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto")
    PolicyFactory(customer=customer, policy_type="Life")
    PolicyFactory(policy_type="Auto")

    response = underwriter.get(URL, {"customer": customer.id, "policy_type": "Auto"})

    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# T047: retrieve (FR-023)
# ---------------------------------------------------------------------------


def test_retrieve_returns_the_full_record(underwriter):
    policy = PolicyFactory(scored=True)

    response = underwriter.get(detail(policy.id))

    assert response.status_code == 200
    assert response.data["id"] == policy.id
    assert response.data["policy_type"] == policy.policy_type
    assert response.data["premium_usd"] == "750.23"
    assert response.data["renewal_probability"] == "0.06"
    assert response.data["customer"]["client_id"] == policy.customer.client_id


def test_retrieve_absent_renewal_probability_is_null_not_zero(underwriter):
    """FR-004: absent must stay distinguishable from a genuine 0.00."""
    policy = PolicyFactory()

    response = underwriter.get(detail(policy.id))

    assert response.data["renewal_probability"] is None


def test_retrieve_nonexistent_returns_404(underwriter):
    assert underwriter.get(detail(999999)).status_code == 404


def test_retrieve_archived_returns_404(underwriter):
    policy = PolicyFactory(archived=True)

    assert underwriter.get(detail(policy.id)).status_code == 404


# ---------------------------------------------------------------------------
# T048: no N+1 across a page
# ---------------------------------------------------------------------------


def test_embedded_customer_does_not_cause_n_plus_one(underwriter, django_assert_num_queries):
    """
    Two queries: the pagination count, and the page itself with its
    customers joined in. Without select_related this would be 52.
    """
    PolicyFactory.create_batch(50)

    with django_assert_num_queries(2):
        underwriter.get(URL)


def test_query_count_is_flat_as_the_page_grows(underwriter, django_assert_num_queries):
    """The count must not track the number of rows returned."""
    PolicyFactory.create_batch(5)
    with django_assert_num_queries(2):
        underwriter.get(URL)

    PolicyFactory.create_batch(45)
    with django_assert_num_queries(2):
        underwriter.get(URL)


# ---------------------------------------------------------------------------
# T054: create (FR-004)
# ---------------------------------------------------------------------------


def test_create_returns_201_with_the_embedded_customer(underwriter):
    customer = CustomerFactory()

    response = underwriter.post(URL, payload(customer), format="json")

    assert response.status_code == 201
    assert response.data["customer"]["id"] == customer.id
    assert response.data["policy_type"] == "Health"


def test_created_policy_is_immediately_retrievable(underwriter):
    customer = CustomerFactory()

    created = underwriter.post(URL, payload(customer), format="json")
    response = underwriter.get(detail(created.data["id"]))

    assert response.status_code == 200
    assert response.data["id"] == created.data["id"]


def test_create_without_renewal_probability_stores_null(underwriter):
    """FR-004."""
    customer = CustomerFactory()

    response = underwriter.post(URL, payload(customer), format="json")

    assert response.data["renewal_probability"] is None
    assert Policy.objects.get(id=response.data["id"]).renewal_probability is None


def test_create_accepts_an_explicit_zero_renewal_probability(underwriter):
    customer = CustomerFactory()

    response = underwriter.post(
        URL, payload(customer, renewal_probability="0.00"), format="json"
    )

    assert response.status_code == 201
    assert Policy.objects.get(id=response.data["id"]).renewal_probability == Decimal("0.00")


def test_create_with_incoherent_dates_is_refused_naming_both(underwriter):
    customer = CustomerFactory()

    response = underwriter.post(
        URL, payload(customer, start_date="2027-01-01", end_date="2026-01-01"), format="json"
    )

    assert response.status_code == 400
    assert "start_date" in response.data
    assert "end_date" in response.data
    assert Policy.all_objects.count() == 0


def test_create_with_unknown_type_is_refused_naming_the_field(underwriter):
    customer = CustomerFactory()

    response = underwriter.post(URL, payload(customer, policy_type="Motor"), format="json")

    assert response.status_code == 400
    assert "policy_type" in response.data
    assert Policy.all_objects.count() == 0


# ---------------------------------------------------------------------------
# T055: multiple policies per customer (FR-003, SC-009)
# ---------------------------------------------------------------------------


def test_second_policy_of_a_different_type_succeeds(underwriter):
    """
    FR-003. customer= is passed explicitly: the factory's SubFactory would
    otherwise give each policy its own customer and never exercise this.
    """
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto")

    response = underwriter.post(URL, payload(customer, policy_type="Life"), format="json")

    assert response.status_code == 201
    assert Policy.objects.filter(customer=customer).count() == 2


def test_second_live_policy_of_the_same_type_is_refused_naming_policy_type(underwriter):
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto")

    response = underwriter.post(URL, payload(customer, policy_type="Auto"), format="json")

    assert response.status_code == 400
    assert "policy_type" in response.data
    assert Policy.objects.filter(customer=customer).count() == 1


# ---------------------------------------------------------------------------
# T056: partial update (FR-017)
# ---------------------------------------------------------------------------


def test_patching_one_field_leaves_every_other_field_identical(underwriter):
    policy = PolicyFactory(scored=True)
    before = {
        "policy_type": policy.policy_type,
        "start_date": policy.start_date,
        "end_date": policy.end_date,
        "renewal_probability": policy.renewal_probability,
        "customer_id": policy.customer_id,
    }

    response = underwriter.patch(
        detail(policy.id), {"premium_usd": "1350.00"}, format="json"
    )

    assert response.status_code == 200
    policy.refresh_from_db()
    assert policy.premium_usd == Decimal("1350.00")
    assert policy.policy_type == before["policy_type"]
    assert policy.start_date == before["start_date"]
    assert policy.end_date == before["end_date"]
    assert policy.renewal_probability == before["renewal_probability"]
    assert policy.customer_id == before["customer_id"]


def test_patching_end_date_alone_checks_against_the_stored_start_date(underwriter):
    policy = PolicyFactory()

    response = underwriter.patch(
        detail(policy.id),
        {"end_date": (policy.start_date - timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert "end_date" in response.data


def test_patch_on_archived_returns_404(underwriter):
    policy = PolicyFactory(archived=True)

    response = underwriter.patch(detail(policy.id), {"premium_usd": "1.00"}, format="json")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# T057: archive (FR-021, SC-012)
# ---------------------------------------------------------------------------


def test_delete_returns_204_and_sets_archived_at(underwriter):
    policy = PolicyFactory()

    response = underwriter.delete(detail(policy.id))

    assert response.status_code == 204
    policy.refresh_from_db()
    assert policy.archived_at is not None


def test_archived_row_survives_in_all_objects(underwriter):
    policy = PolicyFactory()

    underwriter.delete(detail(policy.id))

    assert not Policy.objects.filter(id=policy.id).exists()
    assert Policy.all_objects.filter(id=policy.id).exists()


def test_re_delete_returns_404(underwriter):
    policy = PolicyFactory()

    assert underwriter.delete(detail(policy.id)).status_code == 204
    assert underwriter.delete(detail(policy.id)).status_code == 404


def test_archiving_releases_the_coverage_slot(underwriter):
    """
    SC-012, and the opposite of Customer, where an archived client_id
    stays reserved forever.
    """
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer, policy_type="Auto")

    underwriter.delete(detail(policy.id))
    response = underwriter.post(URL, payload(customer, policy_type="Auto"), format="json")

    assert response.status_code == 201
    assert Policy.objects.filter(customer=customer, policy_type="Auto").count() == 1


# ---------------------------------------------------------------------------
# T078: the Phase 1 placeholder is gone (SC-011, FR-049)
# ---------------------------------------------------------------------------


def test_placeholder_route_returns_404(underwriter):
    """
    The Phase 1 route returned {"module": "policies", "status":
    "placeholder"}. It is deleted, and DRF's router resolves the path as a
    detail lookup that matches nothing.
    """
    response = underwriter.get("/api/policies/placeholder/")

    assert response.status_code == 404
