"""
Cross-entity archival guarantees (T072 - T075).

This is the contract between Customer and Policy (FR-008, FR-022,
SC-008), belonging to neither feature alone. The two archival directions
fail independently, so they are asserted separately rather than in one
combined test:

- Archived customer -> live policy: policy stays readable and linked.
  Broken by resolving the FK through Customer.objects, which hides
  archived rows and would orphan the policy.
- Live customer -> archived policy: policy hidden from customer.policies.
  Broken by declaring all_objects before objects, which would make
  all_objects the _default_manager that related traversal uses.
"""
import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer
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


def archive_customer(customer):
    customer.archived_at = timezone.now()
    customer.save(update_fields=["archived_at"])
    return customer


# ---------------------------------------------------------------------------
# T072: archiving a customer leaves their policies live (FR-008, FR-022)
# ---------------------------------------------------------------------------


def test_archiving_a_customer_leaves_their_policies_live(underwriter):
    """
    SC-008. This is the guarantee that stops customer removal from
    destroying coverage history.
    """
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    archive_customer(customer)

    policy.refresh_from_db()
    assert policy.archived_at is None
    assert Policy.objects.filter(id=policy.id).exists()


def test_policy_of_an_archived_customer_is_still_listed(underwriter):
    customer = CustomerFactory()
    PolicyFactory(customer=customer)

    archive_customer(customer)

    response = underwriter.get(URL)
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_policy_of_an_archived_customer_is_still_retrievable(underwriter):
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    archive_customer(customer)

    response = underwriter.get(detail(policy.id))
    assert response.status_code == 200
    assert response.data["id"] == policy.id


def test_customer_summary_still_resolves_after_archival(underwriter):
    """
    FR-008. Resolving the FK through Customer.objects would 404 or blank
    this out -- precisely the orphaning FR-022 forbids.
    """
    customer = CustomerFactory(name="Patrick Hart")
    policy = PolicyFactory(customer=customer)

    archive_customer(customer)

    response = underwriter.get(detail(policy.id))
    assert response.data["customer"] == {
        "id": customer.id,
        "client_id": customer.client_id,
        "name": "Patrick Hart",
    }


def test_the_link_survives_at_the_orm_level(underwriter):
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    archive_customer(customer)

    policy.refresh_from_db()
    assert policy.customer_id == customer.id
    assert policy.customer.client_id == customer.client_id


def test_an_archived_customers_policy_can_still_be_updated(underwriter):
    """Coverage terms remain administrable after the customer is removed."""
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    archive_customer(customer)

    response = underwriter.patch(
        detail(policy.id), {"premium_usd": "1350.00"}, format="json"
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# T073: the reverse direction -- archived policy, live customer
# ---------------------------------------------------------------------------


def test_archived_policy_is_hidden_from_customer_traversal(underwriter):
    """
    Related traversal uses _default_manager, which is why `objects` must
    be declared before `all_objects` on the model.
    """
    customer = CustomerFactory()
    live = PolicyFactory(customer=customer, policy_type="Auto")
    PolicyFactory(customer=customer, policy_type="Life", archived=True)

    assert list(customer.policies.all()) == [live]


def test_archiving_a_policy_leaves_its_customer_live(underwriter):
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    underwriter.delete(detail(policy.id))

    customer.refresh_from_db()
    assert customer.archived_at is None
    assert Customer.objects.filter(id=customer.id).exists()


def test_both_archived_independently(underwriter):
    """Neither archival implies the other."""
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    underwriter.delete(detail(policy.id))
    archive_customer(customer)

    policy.refresh_from_db()
    customer.refresh_from_db()
    assert policy.archived_at is not None
    assert customer.archived_at is not None
    assert Policy.all_objects.filter(id=policy.id).exists()
    assert Customer.all_objects.filter(id=customer.id).exists()


# ---------------------------------------------------------------------------
# T074: creating a policy for an archived customer (FR-014)
# ---------------------------------------------------------------------------


def test_create_for_an_archived_customer_is_refused_naming_customer(underwriter):
    customer = CustomerFactory()
    archive_customer(customer)

    response = underwriter.post(
        URL,
        {
            "customer": customer.pk,
            "policy_type": "Health",
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "premium_usd": "1200.00",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "customer" in response.data
    assert Policy.all_objects.count() == 0


def test_the_refusal_says_archived_not_does_not_exist(underwriter):
    """
    FR-014. "Does not exist" would send an underwriter hunting for a
    record that was deliberately removed.
    """
    customer = CustomerFactory()
    archive_customer(customer)

    response = underwriter.post(
        URL,
        {
            "customer": customer.pk,
            "policy_type": "Health",
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "premium_usd": "1200.00",
        },
        format="json",
    )

    message = " ".join(str(m) for m in response.data["customer"]).lower()
    assert "archiv" in message
    assert "does not exist" not in message


def test_a_nonexistent_customer_says_does_not_exist(underwriter):
    """FR-013: the other message, so the two remain distinguishable."""
    response = underwriter.post(
        URL,
        {
            "customer": 999999,
            "policy_type": "Health",
            "start_date": "2026-01-01",
            "end_date": "2027-01-01",
            "premium_usd": "1200.00",
        },
        format="json",
    )

    assert response.status_code == 400
    message = " ".join(str(m) for m in response.data["customer"]).lower()
    assert "does not exist" in message
    assert "archiv" not in message


# ---------------------------------------------------------------------------
# T075: Phase 2a regression -- customer removal must still work
# ---------------------------------------------------------------------------


def test_archiving_a_customer_who_holds_policies_still_returns_204(
    authenticated_client,
):
    """
    This feature must not have made customer removal fail. PROTECT on the
    FK guards a hard delete; archival is not a delete and must be
    unaffected.
    """
    customer = CustomerFactory()
    PolicyFactory(customer=customer)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    response = client.delete(f"/api/customers/{customer.id}/")

    assert response.status_code == 204
    customer.refresh_from_db()
    assert customer.archived_at is not None


def test_archiving_a_customer_who_holds_policies_still_audits(authenticated_client):
    customer = CustomerFactory()
    PolicyFactory(customer=customer)
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.delete(f"/api/customers/{customer.id}/")

    entry = AuditLog.objects.get(
        target_type="customers.Customer", action="customer.deleted"
    )
    assert entry.outcome == "succeeded"
    assert entry.target_id == str(customer.id)


def test_hard_delete_of_a_customer_with_policies_is_protected():
    """
    on_delete=PROTECT is the backstop against a hard delete destroying
    policy history. The API never does this; a mistaken shell command
    might.
    """
    from django.db.models import ProtectedError

    customer = CustomerFactory()
    PolicyFactory(customer=customer)

    with pytest.raises(ProtectedError):
        customer.delete()

    assert Customer.all_objects.filter(id=customer.id).exists()
