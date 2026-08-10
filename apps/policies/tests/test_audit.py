"""
Policy audit tests (T066 - T071).

The subtle one is T069, the refusal-vs-miss distinction (FR-031, FR-032).
A detail route raises NotFound both when a permitted user asks for a
policy that does not exist and when an unpermitted user is refused, so the
exception alone cannot tell them apart -- the registry's per-module role
set is what separates them. The Product Manager case is included
specifically: they may read policies, so their 404 is an ordinary miss,
which is the opposite of their standing on customers.
"""
from decimal import Decimal
from unittest import mock

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory
from apps.policies.models import Policy

pytestmark = pytest.mark.django_db

URL = "/api/policies/"


def detail(policy_id):
    return f"{URL}{policy_id}/"


def policy_entries(**filters):
    return AuditLog.objects.filter(target_type="policies.Policy", **filters)


@pytest.fixture
def underwriter(authenticated_client):
    client, user = authenticated_client(Role.UNDERWRITER)
    return client, user


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
# T066: audit content (FR-028, FR-029, FR-030)
# ---------------------------------------------------------------------------


def test_create_writes_policy_created_with_full_after(underwriter):
    client, user = underwriter
    customer = CustomerFactory()

    response = client.post(URL, payload(customer), format="json")

    entry = policy_entries().get()
    assert entry.action == "policy.created"
    assert entry.outcome == "succeeded"
    assert entry.actor == user
    assert entry.target_id == str(response.data["id"])
    assert entry.before is None
    assert entry.after["policy_type"] == "Health"
    assert entry.after["premium_usd"] == "1200.00"
    assert entry.after["customer_id"] == customer.id


def test_update_records_only_the_changed_fields(underwriter):
    """
    FR-029. Patching premium_usd must not list policy_type -- an audit
    diff that names untouched fields makes a real change impossible to
    spot in review.
    """
    client, _ = underwriter
    policy = PolicyFactory(scored=True)

    client.patch(detail(policy.id), {"premium_usd": "1350.00"}, format="json")

    entry = policy_entries(action="policy.updated").get()
    assert set(entry.before) == {"premium_usd"}
    assert set(entry.after) == {"premium_usd"}
    assert entry.before["premium_usd"] == "750.23"
    assert entry.after["premium_usd"] == "1350.00"
    assert "policy_type" not in entry.after


def test_patch_to_an_identical_value_records_no_field_diff(underwriter):
    """A PATCH that changes nothing contributes nothing to the diff."""
    client, _ = underwriter
    policy = PolicyFactory()

    client.patch(
        detail(policy.id), {"premium_usd": str(policy.premium_usd)}, format="json"
    )

    entry = policy_entries(action="policy.updated").get()
    assert entry.before is None
    assert entry.after is None


def test_multi_field_patch_records_every_changed_field(underwriter):
    client, _ = underwriter
    policy = PolicyFactory()

    client.patch(
        detail(policy.id),
        {"premium_usd": "1350.00", "policy_type": "Life"},
        format="json",
    )

    entry = policy_entries(action="policy.updated").get()
    assert set(entry.before) == {"premium_usd", "policy_type"}


def test_delete_writes_policy_deleted_with_full_before(underwriter):
    """FR-030: the values as at removal, so history survives the archival."""
    client, _ = underwriter
    policy = PolicyFactory(scored=True)

    client.delete(detail(policy.id))

    entry = policy_entries(action="policy.deleted").get()
    assert entry.outcome == "succeeded"
    assert entry.after is None
    assert entry.before["policy_type"] == policy.policy_type
    assert entry.before["premium_usd"] == "750.23"
    assert entry.before["renewal_probability"] == "0.06"
    assert entry.before["customer_id"] == policy.customer_id


def test_absent_renewal_probability_is_recorded_as_null(underwriter):
    """FR-004 inside the trail: absent must not become "0.00"."""
    client, _ = underwriter
    policy = PolicyFactory()

    client.delete(detail(policy.id))

    entry = policy_entries(action="policy.deleted").get()
    assert entry.before["renewal_probability"] is None


# ---------------------------------------------------------------------------
# T067: atomicity (FR-033)
# ---------------------------------------------------------------------------


def test_failed_audit_write_rolls_the_create_back(underwriter):
    """
    FR-033: neither persists. If the audit insert could fail
    independently, the platform would hold changes it cannot account for.
    """
    client, _ = underwriter
    customer = CustomerFactory()

    with mock.patch(
        "apps.policies.views.record_action", side_effect=RuntimeError("audit down")
    ):
        with pytest.raises(RuntimeError):
            client.post(URL, payload(customer), format="json")

    assert Policy.all_objects.count() == 0
    assert policy_entries().count() == 0


def test_failed_audit_write_rolls_the_update_back(underwriter):
    client, _ = underwriter
    policy = PolicyFactory()
    original = policy.premium_usd

    with mock.patch(
        "apps.policies.views.record_action", side_effect=RuntimeError("audit down")
    ):
        with pytest.raises(RuntimeError):
            client.patch(detail(policy.id), {"premium_usd": "1350.00"}, format="json")

    policy.refresh_from_db()
    assert policy.premium_usd == original


def test_failed_audit_write_rolls_the_archival_back(underwriter):
    client, _ = underwriter
    policy = PolicyFactory()

    with mock.patch(
        "apps.policies.views.record_action", side_effect=RuntimeError("audit down")
    ):
        with pytest.raises(RuntimeError):
            client.delete(detail(policy.id))

    policy.refresh_from_db()
    assert policy.archived_at is None


# ---------------------------------------------------------------------------
# T068: reads are not audited (FR-035)
# ---------------------------------------------------------------------------


def test_list_writes_no_audit_entry(underwriter):
    client, _ = underwriter
    PolicyFactory.create_batch(3)

    client.get(URL)

    assert policy_entries().count() == 0


def test_filtered_list_writes_no_audit_entry(underwriter):
    client, _ = underwriter
    PolicyFactory(expired=True)

    client.get(URL, {"expired": "true", "policy_type": "Auto"})

    assert policy_entries().count() == 0


def test_retrieve_writes_no_audit_entry(underwriter):
    client, _ = underwriter
    policy = PolicyFactory()

    client.get(detail(policy.id))

    assert policy_entries().count() == 0


# ---------------------------------------------------------------------------
# T069: refusal vs miss (FR-031, FR-032) -- the subtle one
# ---------------------------------------------------------------------------


def test_refused_write_records_outcome_refused_and_changes_nothing(authenticated_client):
    """FR-031."""
    policy = PolicyFactory()
    client, user = authenticated_client(Role.COMPLIANCE_OFFICER)

    response = client.patch(detail(policy.id), {"premium_usd": "1.00"}, format="json")

    assert response.status_code == 404
    entry = policy_entries(outcome="refused").get()
    assert entry.action == "policy.updated"
    assert entry.actor == user
    assert entry.target_id == str(policy.id)

    policy.refresh_from_db()
    assert policy.premium_usd == Decimal("750.23")


def test_refused_collection_read_is_recorded(authenticated_client):
    PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    assert client.get(URL).status_code == 403

    entry = policy_entries(outcome="refused").get()
    assert entry.action == "policy.viewed"


def test_anonymous_refusal_is_recorded_without_an_actor(api_client):
    PolicyFactory()

    api_client.get(URL)

    entry = policy_entries(outcome="refused").get()
    assert entry.actor is None


def test_permitted_users_404_on_a_missing_policy_writes_nothing(underwriter):
    """
    FR-032. Otherwise every mistyped id becomes a "refusal" and the
    compliance record fills with noise.
    """
    client, _ = underwriter

    assert client.get(detail(999999)).status_code == 404

    assert policy_entries().count() == 0


def test_product_manager_404_on_a_missing_policy_is_a_miss_not_a_refusal(
    authenticated_client,
):
    """
    The case the per-module registry exists for. A Product Manager may
    read policies, so their 404 here is an ordinary miss -- while the same
    user's 404 on a missing CUSTOMER is a refusal, because they may not
    read customers at all.
    """
    client, _ = authenticated_client(Role.PRODUCT_MANAGER)

    assert client.get(detail(999999)).status_code == 404
    assert policy_entries().count() == 0

    # Same user, same shape of request, other module: recorded.
    assert client.get("/api/customers/999999/").status_code == 404
    assert AuditLog.objects.filter(
        target_type="customers.Customer", outcome="refused"
    ).count() == 1


def test_unpermitted_users_404_on_a_missing_policy_is_a_refusal(authenticated_client):
    """Executive Leadership may not read policies at all, so this is refused."""
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    assert client.get(detail(999999)).status_code == 404

    assert policy_entries(outcome="refused").count() == 1


def test_refusal_entry_names_the_policy_target_type(authenticated_client):
    """T071: the registry must not mislabel policy refusals as customers."""
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    client.get(detail(policy.id))

    entry = AuditLog.objects.get(outcome="refused")
    assert entry.target_type == "policies.Policy"
    assert entry.action.startswith("policy.")


@pytest.mark.parametrize(
    "method,expected_action",
    [
        ("get", "policy.viewed"),
        ("post", "policy.created"),
        ("patch", "policy.updated"),
        ("delete", "policy.deleted"),
    ],
)
def test_refusal_action_matches_the_method(authenticated_client, method, expected_action):
    policy = PolicyFactory()
    client, _ = authenticated_client(Role.EXECUTIVE_LEADERSHIP)

    target = URL if method == "post" else detail(policy.id)
    getattr(client, method)(target)

    assert policy_entries(outcome="refused").get().action == expected_action


# ---------------------------------------------------------------------------
# T070: append-only (FR-034)
# ---------------------------------------------------------------------------


def test_no_policy_operation_updates_or_deletes_an_existing_entry(underwriter):
    client, _ = underwriter
    customer = CustomerFactory()

    created = client.post(URL, payload(customer), format="json")
    policy_id = created.data["id"]
    first = policy_entries().get()

    client.patch(detail(policy_id), {"premium_usd": "1350.00"}, format="json")
    client.delete(detail(policy_id))

    # The original entry is untouched, and the trail only grew.
    first.refresh_from_db()
    assert first.action == "policy.created"
    assert first.after["premium_usd"] == "1200.00"
    assert policy_entries().count() == 3


def test_audit_rows_reject_mutation(underwriter):
    """Guaranteed by AuditLog.save()/delete() and the Phase 1 DB trigger."""
    client, _ = underwriter
    PolicyFactory()
    client.post(URL, payload(CustomerFactory()), format="json")

    entry = policy_entries().get()

    with pytest.raises(Exception):
        entry.outcome = "refused"
        entry.save()

    with pytest.raises(Exception):
        entry.delete()
