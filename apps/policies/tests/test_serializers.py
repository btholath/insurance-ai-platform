"""
Serializer validation tests (T014 - T018).

The serializer is the single definition of validity (FR-043): the API and
the dataset loader both go through it. Every refusal must name the
offending field (FR-015).

The subtle one is T016: an archived customer must be refused with a message
saying so, not "does not exist". Resolving the FK through Customer.objects
(which hides archived rows) would produce the second message and send an
underwriter hunting for a record that was deliberately removed.
"""
from datetime import date
from decimal import Decimal

import pytest

from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory
from apps.policies.serializers import PolicySerializer, PolicyUpdateSerializer

pytestmark = pytest.mark.django_db


def payload(customer=None, **overrides):
    # Accepts either a Customer or a bare pk; callers use both. Serialized
    # input is always the pk, which is what the API actually receives.
    if customer is None:
        customer = CustomerFactory()
    data = {
        "customer": getattr(customer, "pk", customer),
        "policy_type": "Health",
        "start_date": "2026-01-01",
        "end_date": "2027-01-01",
        "premium_usd": "1200.00",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# T014: field validation
# ---------------------------------------------------------------------------


def test_valid_payload_accepted():
    serializer = PolicySerializer(data=payload())

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("bad_type", ["Motor", "life", "", "Travel"])
def test_unrecognized_policy_type_refused(bad_type):
    """FR-009."""
    serializer = PolicySerializer(data=payload(policy_type=bad_type))

    assert not serializer.is_valid()
    assert "policy_type" in serializer.errors


@pytest.mark.parametrize("premium", ["0.00", "-1.00", "-0.01"])
def test_non_positive_premium_refused(premium):
    """FR-011."""
    serializer = PolicySerializer(data=payload(premium_usd=premium))

    assert not serializer.is_valid()
    assert "premium_usd" in serializer.errors


@pytest.mark.parametrize("value", ["-0.01", "1.01", "2.00"])
def test_renewal_probability_outside_range_refused(value):
    """FR-012."""
    serializer = PolicySerializer(data=payload(renewal_probability=value))

    assert not serializer.is_valid()
    assert "renewal_probability" in serializer.errors


def test_missing_customer_refused():
    """FR-002."""
    data = payload()
    del data["customer"]

    serializer = PolicySerializer(data=data)

    assert not serializer.is_valid()
    assert "customer" in serializer.errors


# ---------------------------------------------------------------------------
# T015: date coherence (FR-010)
# ---------------------------------------------------------------------------


def test_end_date_equal_to_start_refused_naming_both_dates():
    serializer = PolicySerializer(
        data=payload(start_date="2026-01-01", end_date="2026-01-01")
    )

    assert not serializer.is_valid()
    reported = " ".join(str(v) for v in serializer.errors.values()).lower()
    assert "start_date" in serializer.errors or "start" in reported
    assert "end_date" in serializer.errors or "end" in reported


def test_end_date_before_start_refused():
    serializer = PolicySerializer(
        data=payload(start_date="2026-06-01", end_date="2026-01-01")
    )

    assert not serializer.is_valid()


def test_end_date_one_day_after_start_accepted():
    serializer = PolicySerializer(
        data=payload(start_date="2026-01-01", end_date="2026-01-02")
    )

    assert serializer.is_valid(), serializer.errors


def test_patching_end_date_alone_checks_against_stored_start_date():
    """
    A PATCH supplying only end_date must still be validated against the
    policy's existing start_date, not skipped for lack of both fields.
    """
    policy = PolicyFactory(start_date=date(2025, 1, 1), end_date=date(2027, 1, 1))

    serializer = PolicyUpdateSerializer(
        policy, data={"end_date": "2024-01-01"}, partial=True
    )

    assert not serializer.is_valid()


def test_patching_start_date_alone_checks_against_stored_end_date():
    policy = PolicyFactory(start_date=date(2025, 1, 1), end_date=date(2027, 1, 1))

    serializer = PolicyUpdateSerializer(
        policy, data={"start_date": "2028-01-01"}, partial=True
    )

    assert not serializer.is_valid()


def test_backdated_and_future_dated_policies_accepted():
    """
    Only the ordering is incoherent, never the absolute position. A rule
    forbidding past start dates would refuse most of the dataset, whose
    start dates run from 2022.
    """
    past = PolicySerializer(data=payload(start_date="2020-01-01", end_date="2021-01-01"))
    future = PolicySerializer(data=payload(start_date="2030-01-01", end_date="2031-01-01"))

    assert past.is_valid(), past.errors
    assert future.is_valid(), future.errors


# ---------------------------------------------------------------------------
# T016: customer resolution (FR-013, FR-014)
# ---------------------------------------------------------------------------


def test_nonexistent_customer_refused_naming_customer():
    """FR-013."""
    serializer = PolicySerializer(data=payload(customer=999999))

    assert not serializer.is_valid()
    assert "customer" in serializer.errors


def test_archived_customer_refused_naming_customer():
    """FR-014."""
    archived = CustomerFactory(archived=True)

    serializer = PolicySerializer(data=payload(customer=archived.pk))

    assert not serializer.is_valid()
    assert "customer" in serializer.errors


def test_archived_customer_refusal_says_archived_not_missing():
    """
    The message must distinguish "removed" from "never existed" -- an
    underwriter should not go hunting for a record that was deliberately
    archived. Resolving through Customer.objects instead of all_objects
    would produce the misleading message.
    """
    archived = CustomerFactory(archived=True)

    serializer = PolicySerializer(data=payload(customer=archived.pk))
    serializer.is_valid()

    message = " ".join(str(m) for m in serializer.errors["customer"]).lower()
    assert "archiv" in message


def test_live_customer_accepted():
    live = CustomerFactory()

    serializer = PolicySerializer(data=payload(customer=live.pk))

    assert serializer.is_valid(), serializer.errors


# ---------------------------------------------------------------------------
# T017: absent is not zero (FR-004)
# ---------------------------------------------------------------------------


def test_renewal_probability_absent_when_not_supplied():
    serializer = PolicySerializer(data=payload())
    assert serializer.is_valid(), serializer.errors
    policy = serializer.save()

    assert policy.renewal_probability is None


def test_zero_renewal_probability_distinguishable_from_absent():
    """
    13 rows in the source dataset carry a genuine 0.0. A truthiness check
    would silently reclassify all 13 as "not recorded".
    """
    zero = PolicySerializer(data=payload(renewal_probability="0.00"))
    assert zero.is_valid(), zero.errors
    zero_policy = zero.save()

    absent = PolicySerializer(data=payload())
    assert absent.is_valid(), absent.errors
    absent_policy = absent.save()

    assert zero_policy.renewal_probability == Decimal("0.00")
    assert zero_policy.renewal_probability is not None
    assert absent_policy.renewal_probability is None


def test_absent_renewal_probability_serializes_as_null():
    policy = PolicyFactory(renewal_probability=None)

    data = PolicySerializer(policy).data

    assert data["renewal_probability"] is None
    assert data["renewal_probability"] != "0.00"


def test_stored_renewal_probability_returned_as_supplied():
    """FR-005: stored and returned, never computed."""
    policy = PolicyFactory(scored=True)

    data = PolicySerializer(policy).data

    assert data["renewal_probability"] == "0.06"


# ---------------------------------------------------------------------------
# T018: boundary acceptance (SC-007)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0.00", "1.00"])
def test_renewal_probability_boundaries_accepted(value):
    serializer = PolicySerializer(data=payload(renewal_probability=value))

    assert serializer.is_valid(), serializer.errors


def test_smallest_positive_premium_accepted():
    serializer = PolicySerializer(data=payload(premium_usd="0.01"))

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("policy_type", ["Life", "Auto", "Property", "Health"])
def test_every_recognized_policy_type_accepted(policy_type):
    serializer = PolicySerializer(data=payload(policy_type=policy_type))

    assert serializer.is_valid(), serializer.errors


# ---------------------------------------------------------------------------
# Read shape and update serializer
# ---------------------------------------------------------------------------


def test_read_shape_embeds_customer_summary():
    """US1 must not need a second request per row."""
    customer = CustomerFactory(client_id="CL-00001", name="Patrick Hart")
    policy = PolicyFactory(customer=customer)

    data = PolicySerializer(policy).data

    assert data["customer"]["id"] == customer.pk
    assert data["customer"]["client_id"] == "CL-00001"
    assert data["customer"]["name"] == "Patrick Hart"


def test_update_serializer_allows_partial_payload():
    """FR-017."""
    policy = PolicyFactory()

    serializer = PolicyUpdateSerializer(policy, data={"premium_usd": "999.99"}, partial=True)

    assert serializer.is_valid(), serializer.errors


def test_update_serializer_applies_same_validation():
    policy = PolicyFactory()

    serializer = PolicyUpdateSerializer(policy, data={"premium_usd": "0.00"}, partial=True)

    assert not serializer.is_valid()
    assert "premium_usd" in serializer.errors


def test_duplicate_live_type_for_same_customer_refused():
    """
    The constraint the loader's match key depends on, surfaced as a field
    error rather than an IntegrityError.
    """
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto")

    serializer = PolicySerializer(data=payload(customer=customer, policy_type="Auto"))

    assert not serializer.is_valid()
    assert "policy_type" in serializer.errors or "non_field_errors" in serializer.errors


def test_second_policy_of_different_type_accepted():
    """FR-003."""
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto")

    serializer = PolicySerializer(data=payload(customer=customer, policy_type="Health"))

    assert serializer.is_valid(), serializer.errors


def test_archiving_releases_the_slot_at_the_serializer_layer():
    """
    FR-021 at the validation layer, not just the database.

    test_models.py proves the partial index releases the slot. This proves
    the serializer agrees. The two can diverge: ModelSerializer synthesizes
    a UniqueTogetherValidator from the model's UniqueConstraint, and that
    validator does NOT carry the constraint's archived_at IS NULL
    condition -- it is scoped only by the queryset it is built from. It is
    correct here because that queryset comes from Policy.objects, which
    already hides archived rows. Swap the model's default manager and this
    silently starts refusing coverage the database would accept.
    """
    customer = CustomerFactory()
    PolicyFactory(customer=customer, policy_type="Auto", archived=True)

    serializer = PolicySerializer(data=payload(customer=customer, policy_type="Auto"))

    assert serializer.is_valid(), serializer.errors
