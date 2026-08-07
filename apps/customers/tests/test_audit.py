"""
Audit trail tests (T051 - T055, FR-027 through FR-033).

The subtle one is test_permitted_user_404_is_not_recorded_as_refusal: a
detail route raises NotFound both when a permitted user asks for a
nonexistent customer and when an unpermitted user is refused. If the
handler cannot tell them apart, every mistyped reference becomes a
"permission refusal" and the compliance record fills with noise.
"""
from unittest import mock

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db

LIST_URL = "/api/customers/"

PAYLOAD = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "555-0100",
    "age": 36,
    "gender": "Female",
    "location": "London",
    "lead_source": "Referral",
}


def detail_url(pk):
    return f"/api/customers/{pk}/"


def customer_entries(**filters):
    return AuditLog.objects.filter(target_type="customers.Customer", **filters)


# ---------------------------------------------------------------------------
# T051: entry content (FR-027, FR-028, FR-029)
# ---------------------------------------------------------------------------


def test_create_writes_audit_entry_with_full_after(authenticated_client):
    client, user = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.post(LIST_URL, PAYLOAD, format="json")

    entry = customer_entries(action="customer.created").get()
    assert entry.target_id == str(response.data["id"])
    assert entry.actor == user
    assert entry.outcome == "succeeded"
    assert entry.before is None
    assert entry.after["name"] == "Ada Lovelace"
    assert entry.after["email"] == "ada@example.com"


def test_update_records_only_changed_fields(authenticated_client):
    """
    FR-028. Patching only phone must not list name or email in the diff.
    """
    customer = CustomerFactory(name="Original", email="orig@example.com", phone="111-1111")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.patch(detail_url(customer.pk), {"phone": "999-9999"}, format="json")

    entry = customer_entries(action="customer.updated").get()
    assert set(entry.before) == {"phone"}
    assert set(entry.after) == {"phone"}
    assert entry.before["phone"] == "111-1111"
    assert entry.after["phone"] == "999-9999"
    assert "name" not in entry.after
    assert "email" not in entry.after


def test_update_records_multiple_changed_fields(authenticated_client):
    customer = CustomerFactory(name="Original", phone="111-1111")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.patch(detail_url(customer.pk), {"name": "Corrected", "phone": "999-9999"}, format="json")

    entry = customer_entries(action="customer.updated").get()
    assert set(entry.before) == {"name", "phone"}


def test_noop_update_records_no_field_diff(authenticated_client):
    """A PATCH setting a field to its current value changes nothing."""
    customer = CustomerFactory(phone="111-1111")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.patch(detail_url(customer.pk), {"phone": "111-1111"}, format="json")

    entry = customer_entries(action="customer.updated").get()
    assert entry.before is None
    assert entry.after is None


def test_delete_records_values_at_removal(authenticated_client):
    """FR-029."""
    customer = CustomerFactory(name="Departing Person", client_id="CL-00777")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.delete(detail_url(customer.pk))

    entry = customer_entries(action="customer.deleted").get()
    assert entry.before["name"] == "Departing Person"
    assert entry.before["client_id"] == "CL-00777"
    assert entry.after is None


def test_three_operations_produce_three_entries(authenticated_client):
    """SC-006."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    created = client.post(LIST_URL, PAYLOAD, format="json").data
    client.patch(detail_url(created["id"]), {"phone": "222-2222"}, format="json")
    client.delete(detail_url(created["id"]))

    actions = list(customer_entries(target_id=str(created["id"])).order_by("id").values_list("action", flat=True))
    assert actions == ["customer.created", "customer.updated", "customer.deleted"]


# ---------------------------------------------------------------------------
# T052: atomicity (FR-031)
# ---------------------------------------------------------------------------


def test_audit_failure_rolls_back_create(authenticated_client):
    """
    FR-031: the customer change and its audit entry both succeed or both
    fail. record_action is called inside the same transaction, so an audit
    failure must take the customer with it.
    """
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    before_count = Customer.all_objects.count()

    with mock.patch("apps.customers.views.record_action", side_effect=RuntimeError("audit down")):
        with pytest.raises(RuntimeError):
            client.post(LIST_URL, PAYLOAD, format="json")

    assert Customer.all_objects.count() == before_count
    assert customer_entries().count() == 0


def test_audit_failure_rolls_back_update(authenticated_client):
    customer = CustomerFactory(phone="111-1111")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    with mock.patch("apps.customers.views.record_action", side_effect=RuntimeError("audit down")):
        with pytest.raises(RuntimeError):
            client.patch(detail_url(customer.pk), {"phone": "999-9999"}, format="json")

    customer.refresh_from_db()
    assert customer.phone == "111-1111"


def test_audit_failure_rolls_back_delete(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    with mock.patch("apps.customers.views.record_action", side_effect=RuntimeError("audit down")):
        with pytest.raises(RuntimeError):
            client.delete(detail_url(customer.pk))

    customer.refresh_from_db()
    assert customer.archived_at is None
    assert Customer.objects.filter(pk=customer.pk).exists()


# ---------------------------------------------------------------------------
# T053: reads are not audited (FR-033)
# ---------------------------------------------------------------------------


def test_list_produces_no_audit_entry(authenticated_client):
    CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.get(LIST_URL)

    assert customer_entries().count() == 0


def test_search_produces_no_audit_entry(authenticated_client):
    CustomerFactory(name="Searchable")
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.get(LIST_URL, {"search": "Searchable"})

    assert customer_entries().count() == 0


def test_retrieve_produces_no_audit_entry(authenticated_client):
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.get(detail_url(customer.pk))

    assert customer_entries().count() == 0


# ---------------------------------------------------------------------------
# T054: refusals are audited, ordinary misses are not (FR-030)
# ---------------------------------------------------------------------------


def test_refused_create_is_recorded_as_refusal(authenticated_client):
    """FR-030."""
    client, user = authenticated_client(Role.UNDERWRITER)

    response = client.post(LIST_URL, PAYLOAD, format="json")

    assert response.status_code == 403
    entry = customer_entries(outcome="refused").get()
    assert entry.actor == user


def test_refused_list_is_recorded_as_refusal(authenticated_client):
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    client.get(LIST_URL)

    assert customer_entries(outcome="refused").count() == 1


def test_refused_delete_leaves_customer_unchanged(authenticated_client):
    """FR-030: the refusal is recorded, the data is not touched."""
    customer = CustomerFactory()
    client, _ = authenticated_client(Role.UNDERWRITER)

    client.delete(detail_url(customer.pk))

    assert customer_entries(outcome="refused").count() == 1
    assert Customer.objects.filter(pk=customer.pk).exists()


def test_anonymous_refusal_is_recorded(api_client):
    api_client.get(LIST_URL)

    assert customer_entries(outcome="refused").count() == 1


def test_permitted_user_404_is_not_recorded_as_refusal(authenticated_client):
    """
    The distinction that keeps the compliance record usable.

    A permitted user hitting a nonexistent id is an ordinary miss, not a
    permission refusal. Without this, every mistyped reference would be
    logged as a refusal.
    """
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.get(detail_url(999999))

    assert response.status_code == 404
    assert customer_entries(outcome="refused").count() == 0


def test_permitted_user_404_on_archived_is_not_a_refusal(authenticated_client):
    customer = CustomerFactory(archived=True)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.get(detail_url(customer.pk))

    assert customer_entries(outcome="refused").count() == 0


def test_validation_failure_is_not_recorded_as_refusal(authenticated_client):
    """A 400 is not a permission refusal."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.post(LIST_URL, dict(PAYLOAD, age=5), format="json")

    assert customer_entries(outcome="refused").count() == 0


def test_refusal_response_body_reveals_nothing(authenticated_client):
    """FR-022: refusal logging must not change what the caller sees."""
    customer = CustomerFactory(name="Secret Person")
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    response = client.get(detail_url(customer.pk))

    assert response.status_code == 404
    assert "Secret Person" not in str(response.data)


# ---------------------------------------------------------------------------
# T055: append-only holds (FR-032)
# ---------------------------------------------------------------------------


def test_customer_operations_never_modify_existing_entries(authenticated_client):
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    created = client.post(LIST_URL, PAYLOAD, format="json").data
    first_entry = customer_entries().get()
    original_timestamp = first_entry.timestamp

    client.patch(detail_url(created["id"]), {"phone": "222-2222"}, format="json")
    client.delete(detail_url(created["id"]))

    first_entry.refresh_from_db()
    assert first_entry.timestamp == original_timestamp
    assert first_entry.action == "customer.created"
    assert customer_entries().count() == 3


def test_audit_entries_remain_append_only(authenticated_client):
    """FR-032: the Phase 1 guarantee still holds."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)
    client.post(LIST_URL, PAYLOAD, format="json")
    entry = customer_entries().get()

    with pytest.raises(NotImplementedError):
        entry.save()

    with pytest.raises(NotImplementedError):
        entry.delete()
