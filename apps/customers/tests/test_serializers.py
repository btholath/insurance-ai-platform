"""
Serializer validation tests (T012, T013, T014).

The serializer is the single definition of validity (FR-038): the API and
the CSV loader both go through it, so these tests constrain both paths.
Every refusal must name the offending field (FR-014).
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer, CustomerUpdateSerializer

pytestmark = pytest.mark.django_db


VALID = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "555-0100",
    "age": 36,
    "gender": "Female",
    "location": "London",
    "lead_source": "Referral",
}


def payload(**overrides):
    data = dict(VALID)
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# T012: FR-009 .. FR-014
# ---------------------------------------------------------------------------


def test_valid_payload_is_accepted():
    serializer = CustomerSerializer(data=payload())

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_name_absent_or_empty_refused(bad_name):
    """FR-009."""
    serializer = CustomerSerializer(data=payload(name=bad_name))

    assert not serializer.is_valid()
    assert "name" in serializer.errors


def test_name_missing_key_refused():
    data = payload()
    del data["name"]

    serializer = CustomerSerializer(data=data)

    assert not serializer.is_valid()
    assert "name" in serializer.errors


@pytest.mark.parametrize("bad_email", ["not-an-email", "missing@", "@nodomain.com", "a b@c.com"])
def test_malformed_email_refused(bad_email):
    """FR-010."""
    serializer = CustomerSerializer(data=payload(email=bad_email))

    assert not serializer.is_valid()
    assert "email" in serializer.errors


@pytest.mark.parametrize("age", [18, 120])
def test_age_boundaries_accepted(age):
    """FR-011: both boundaries are valid."""
    serializer = CustomerSerializer(data=payload(age=age))

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("age", [17, 121, 0, -1])
def test_age_outside_range_refused(age):
    """FR-011."""
    serializer = CustomerSerializer(data=payload(age=age))

    assert not serializer.is_valid()
    assert "age" in serializer.errors


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("gender", "Unknown"),
        ("lead_source", "Carrier Pigeon"),
        ("fraud_risk_flag", "Extreme"),
    ],
)
def test_unrecognized_category_refused_naming_field(field, bad_value):
    """FR-012: the offending field must be named."""
    serializer = CustomerSerializer(data=payload(**{field: bad_value}))

    assert not serializer.is_valid()
    assert field in serializer.errors


@pytest.mark.parametrize("value", ["-0.01", "1.01", "2.00"])
def test_cross_sell_score_outside_range_refused(value):
    """FR-013."""
    serializer = CustomerSerializer(data=payload(cross_sell_score=value))

    assert not serializer.is_valid()
    assert "cross_sell_score" in serializer.errors


@pytest.mark.parametrize("value", ["0.00", "1.00", "0.42"])
def test_cross_sell_score_boundaries_accepted(value):
    """FR-013: 0 and 1 are inside the range."""
    serializer = CustomerSerializer(data=payload(cross_sell_score=value))

    assert serializer.is_valid(), serializer.errors


def test_refusal_stores_nothing():
    """FR-014."""
    before = Customer.all_objects.count()

    serializer = CustomerSerializer(data=payload(age=999))
    serializer.is_valid()

    assert Customer.all_objects.count() == before


# ---------------------------------------------------------------------------
# T013: absent is not zero (FR-006)
# ---------------------------------------------------------------------------


def test_scores_absent_when_not_supplied():
    """
    FR-006. Asserted with `is None`, never truthiness -- the source data
    contains genuine 0.0 cross-sell scores, so a falsy check would conflate
    a real zero with an absent value.
    """
    serializer = CustomerSerializer(data=payload())
    assert serializer.is_valid(), serializer.errors
    customer = serializer.save()

    assert customer.risk_score is None
    assert customer.cross_sell_score is None
    assert customer.fraud_risk_flag is None


def test_zero_score_is_distinguishable_from_absent():
    """FR-006: 0.00 and None are different stored values."""
    zero = CustomerSerializer(data=payload(cross_sell_score="0.00", email="z@example.com"))
    assert zero.is_valid(), zero.errors
    zero_customer = zero.save()

    absent = CustomerSerializer(data=payload(email="a@example.com"))
    assert absent.is_valid(), absent.errors
    absent_customer = absent.save()

    assert zero_customer.cross_sell_score == Decimal("0.00")
    assert zero_customer.cross_sell_score is not None
    assert absent_customer.cross_sell_score is None


def test_absent_score_serializes_as_null_not_zero():
    customer = CustomerFactory(risk_score=None)

    data = CustomerSerializer(customer).data

    assert data["risk_score"] is None
    assert data["risk_score"] != "0.00"


def test_stored_scores_are_returned_as_supplied():
    """FR-007: stored and returned, never computed."""
    customer = CustomerFactory(scored=True)

    data = CustomerSerializer(customer).data

    assert data["risk_score"] == "0.42"
    assert data["cross_sell_score"] == "0.75"
    assert data["fraud_risk_flag"] == "Low"


# ---------------------------------------------------------------------------
# risk_score is read-only (FR-056; Phase 3a data-model.md).
#
# With the risk engine as sole writer, an API client setting risk_score
# directly would create a score with no assessment and no explanation --
# a black-box score, which Principle IV forbids. cross_sell_score is
# unaffected: nothing in this feature computes it, so it stays writable.
# ---------------------------------------------------------------------------


def test_risk_score_cannot_be_set_via_create():
    serializer = CustomerSerializer(data=payload(risk_score="0.99"))
    assert serializer.is_valid(), serializer.errors
    customer = serializer.save()

    assert customer.risk_score is None


def test_risk_score_cannot_be_set_via_update():
    customer = CustomerFactory(risk_score=None)

    serializer = CustomerUpdateSerializer(
        customer, data={"risk_score": "0.99"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    assert updated.risk_score is None


# ---------------------------------------------------------------------------
# T014: duplicate handling
# ---------------------------------------------------------------------------


def test_two_customers_may_share_an_email():
    """FR-004: the source dataset has three legitimately shared addresses."""
    first = CustomerSerializer(data=payload(email="shared@example.com"))
    assert first.is_valid(), first.errors
    first.save()

    second = CustomerSerializer(data=payload(email="shared@example.com", name="Other Person"))

    assert second.is_valid(), second.errors
    second.save()
    assert Customer.objects.filter(email="shared@example.com").count() == 2


def test_duplicate_client_id_refused_naming_field():
    """FR-003."""
    CustomerFactory(client_id="CL-00042")

    serializer = CustomerSerializer(data=payload(client_id="CL-00042"))

    assert not serializer.is_valid()
    assert "client_id" in serializer.errors


def test_client_id_colliding_with_archived_record_refused():
    """
    FR-021: archival reserves the reference, so uniqueness must be checked
    against all_objects rather than the archived-hiding default manager.
    """
    CustomerFactory(client_id="CL-00043", archived=True)

    serializer = CustomerSerializer(data=payload(client_id="CL-00043"))

    assert not serializer.is_valid()
    assert "client_id" in serializer.errors


def test_client_id_optional_on_create():
    """FR-005: generated when absent."""
    serializer = CustomerSerializer(data=payload())

    assert serializer.is_valid(), serializer.errors


# ---------------------------------------------------------------------------
# Update serializer
# ---------------------------------------------------------------------------


def test_update_serializer_allows_partial_payload():
    """FR-016."""
    customer = CustomerFactory()

    serializer = CustomerUpdateSerializer(customer, data={"phone": "555-0199"}, partial=True)

    assert serializer.is_valid(), serializer.errors


def test_update_serializer_applies_same_validation():
    customer = CustomerFactory()

    serializer = CustomerUpdateSerializer(customer, data={"age": 5}, partial=True)

    assert not serializer.is_valid()
    assert "age" in serializer.errors


def test_update_to_conflicting_client_id_refused():
    """FR-003: a reference already held by a different customer."""
    CustomerFactory(client_id="CL-00100")
    target = CustomerFactory(client_id="CL-00101")

    serializer = CustomerUpdateSerializer(target, data={"client_id": "CL-00100"}, partial=True)

    assert not serializer.is_valid()
    assert "client_id" in serializer.errors


def test_update_keeping_own_client_id_allowed():
    """Re-submitting a customer's own reference is not a conflict."""
    target = CustomerFactory(client_id="CL-00102")

    serializer = CustomerUpdateSerializer(target, data={"client_id": "CL-00102"}, partial=True)

    assert serializer.is_valid(), serializer.errors


def test_read_only_fields_are_not_writable():
    customer = CustomerFactory()
    original_archived = customer.archived_at

    serializer = CustomerUpdateSerializer(
        customer, data={"archived_at": timezone.now().isoformat()}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    assert updated.archived_at == original_archived
