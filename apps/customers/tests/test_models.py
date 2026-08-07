"""
Model-level tests for Customer (T004, T005, T006).

These cover the three properties that are invisible in ordinary use and
expensive to discover later:

1. The score CheckConstraints must accept NULL. Written naively as
   `Q(risk_score__gte=0) & Q(risk_score__lte=1)`, a NULL score makes the
   comparison SQL-NULL rather than true and Postgres rejects every customer
   created without a score -- which is every customer created via the API.
2. `Customer.objects` must hide archived rows while `Customer.all_objects`
   sees them, and `objects` must remain `_default_manager` so future
   `policy.customer` traversal does not surface archived records.
3. client_id generation must order on the numeric suffix, not the raw
   string. Lexicographic ordering is correct only while every reference is
   exactly five digits; at CL-100000 the string "CL-99999" still sorts
   higher and the generator starts reissuing live references.
"""
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from django.db.utils import DataError
from django.utils import timezone

from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# T004: fields and constraints
# ---------------------------------------------------------------------------


def test_customer_stores_all_specified_fields():
    customer = CustomerFactory(
        client_id="CL-00001",
        name="Patrick Hart",
        email="amandamartinez@hayes.com",
        phone="588-240-1527",
        age=25,
        gender="Other",
        location="New Steven",
        lead_source="Agent",
    )
    customer.refresh_from_db()

    assert customer.client_id == "CL-00001"
    assert customer.name == "Patrick Hart"
    assert customer.email == "amandamartinez@hayes.com"
    assert customer.phone == "588-240-1527"
    assert customer.age == 25
    assert customer.gender == "Other"
    assert customer.location == "New Steven"
    assert customer.lead_source == "Agent"


def test_timestamps_are_populated_on_create():
    """FR-008: created_at and updated_at come from TimeStampedModel."""
    customer = CustomerFactory()

    assert customer.created_at is not None
    assert customer.updated_at is not None


@pytest.mark.parametrize("age", [18, 120])
def test_age_boundaries_accepted(age):
    """FR-011: 18 and 120 are both valid."""
    customer = CustomerFactory(age=age)

    assert customer.pk is not None


@pytest.mark.parametrize("age", [17, 121])
def test_age_outside_range_rejected_by_constraint(age):
    """FR-011: the DB constraint is the backstop behind the serializer."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomerFactory(age=age)


def test_scores_accept_null():
    """
    FR-006 / the SQL three-valued-logic trap.

    A customer with no scores must insert cleanly. If the CheckConstraints
    omit the isnull disjunction, this raises IntegrityError and every
    API-created customer becomes impossible.
    """
    customer = CustomerFactory(risk_score=None, fraud_risk_flag=None, cross_sell_score=None)
    customer.refresh_from_db()

    assert customer.risk_score is None
    assert customer.fraud_risk_flag is None
    assert customer.cross_sell_score is None


@pytest.mark.parametrize("value", [Decimal("0.00"), Decimal("1.00")])
@pytest.mark.parametrize("field", ["risk_score", "cross_sell_score"])
def test_score_boundaries_accepted(field, value):
    """FR-013: 0 and 1 are both inside the accepted range."""
    customer = CustomerFactory(**{field: value})
    customer.refresh_from_db()

    assert getattr(customer, field) == value


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("1.01")])
@pytest.mark.parametrize("field", ["risk_score", "cross_sell_score"])
def test_score_outside_range_rejected_by_constraint(field, value):
    with pytest.raises((IntegrityError, DataError)):
        with transaction.atomic():
            CustomerFactory(**{field: value})


def _raw_create(**overrides):
    """
    Insert bypassing CustomerFactory.

    The factory sets django_get_or_create on client_id, so calling it twice
    with the same reference fetches the existing row rather than attempting
    a duplicate insert -- which would make a uniqueness assertion pass
    vacuously. These tests need a real INSERT.
    """
    fields = dict(
        name="Dup", email="dup@example.com", phone="1", age=30,
        gender="Other", location="X", lead_source="Web",
    )
    fields.update(overrides)
    return Customer.all_objects.create(**fields)


def test_client_id_is_unique():
    """FR-003."""
    _raw_create(client_id="CL-00042")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(client_id="CL-00042")


def test_client_id_uniqueness_holds_across_archived_rows():
    """
    FR-021: archival reserves the reference. Archiving does not remove the
    row, so the unique constraint still rejects a colliding insert -- which
    is exactly why the loader must reconcile rather than blind-insert.
    """
    _raw_create(client_id="CL-00043", archived_at=timezone.now())

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(client_id="CL-00043")


def test_email_is_not_unique():
    """FR-004: the source dataset has three legitimately shared addresses."""
    CustomerFactory(email="shared@example.com")
    second = CustomerFactory(email="shared@example.com")

    assert second.pk is not None
    assert Customer.objects.filter(email="shared@example.com").count() == 2


# ---------------------------------------------------------------------------
# T005: manager isolation
# ---------------------------------------------------------------------------


def test_objects_manager_excludes_archived():
    """FR-020."""
    live = CustomerFactory()
    CustomerFactory(archived=True)

    assert list(Customer.objects.all()) == [live]


def test_all_objects_manager_includes_archived():
    """
    FR-021 depends on this manager existing. The loader must be able to find
    an archived record by reference to reconcile against it.
    """
    live = CustomerFactory()
    archived = CustomerFactory(archived=True)

    assert set(Customer.all_objects.all()) == {live, archived}


def test_default_manager_is_objects():
    """
    Keeps archived customers from surfacing through future policy.customer
    traversal, which uses _default_manager.
    """
    assert Customer._default_manager.__class__ is Customer.objects.__class__
    assert Customer._meta.default_manager_name in (None, "objects")


def test_archived_customer_is_retained_not_deleted():
    """FR-020: removal is reversible archival, not destruction."""
    customer = CustomerFactory()
    pk = customer.pk

    customer.archived_at = timezone.now()
    customer.save()

    assert not Customer.objects.filter(pk=pk).exists()
    assert Customer.all_objects.filter(pk=pk).exists()


# ---------------------------------------------------------------------------
# T006: client_id generation
# ---------------------------------------------------------------------------


def test_generated_reference_matches_source_format():
    """FR-005: same CL-##### format as the source dataset."""
    customer = Customer.objects.create_with_reference(
        name="Ada Lovelace",
        email="ada@example.com",
        phone="555-0100",
        age=36,
        gender="Female",
        location="London",
        lead_source="Referral",
    )

    assert customer.client_id.startswith("CL-")
    assert customer.client_id[3:].isdigit()
    assert len(customer.client_id) >= 8


def test_generated_reference_continues_from_maximum():
    CustomerFactory(client_id="CL-00007")

    customer = Customer.objects.create_with_reference(
        name="Next", email="n@example.com", phone="1", age=30,
        gender="Other", location="X", lead_source="Web",
    )

    assert customer.client_id == "CL-00008"


def test_generated_reference_starts_at_one_on_empty_table():
    customer = Customer.objects.create_with_reference(
        name="First", email="f@example.com", phone="1", age=30,
        gender="Other", location="X", lead_source="Web",
    )

    assert customer.client_id == "CL-00001"


def test_generated_reference_does_not_reissue_archived_reference():
    """
    FR-021: the scan runs through all_objects, so an archived record's
    reference is never handed to a new customer.
    """
    CustomerFactory(client_id="CL-00050", archived=True)

    customer = Customer.objects.create_with_reference(
        name="After", email="a@example.com", phone="1", age=30,
        gender="Other", location="X", lead_source="Web",
    )

    assert customer.client_id == "CL-00051"
    assert Customer.all_objects.filter(client_id="CL-00050").count() == 1


def test_generation_retries_once_when_reference_is_taken_concurrently():
    """
    The empty-table race: SELECT ... FOR UPDATE has no row to lock, so two
    concurrent first-creates can both compute CL-00001. The unique
    constraint rejects the loser and the single retry resolves it.

    Simulated by having generate_client_id() hand back an already-taken
    reference on its first call.
    """
    CustomerFactory(client_id="CL-00001")
    taken_then_fresh = ["CL-00001", "CL-00002"]

    with mock.patch(
        "apps.customers.models.generate_client_id", side_effect=taken_then_fresh
    ):
        customer = Customer.objects.create_with_reference(
            name="Racer", email="r@example.com", phone="1", age=30,
            gender="Other", location="X", lead_source="Web",
        )

    assert customer.client_id == "CL-00002"


def test_explicit_reference_bypasses_generation():
    customer = Customer.objects.create_with_reference(
        client_id="CL-00123", name="Explicit", email="e@example.com", phone="1",
        age=30, gender="Other", location="X", lead_source="Web",
    )

    assert customer.client_id == "CL-00123"


def test_is_archived_property():
    live = CustomerFactory()
    archived = CustomerFactory(archived=True)

    assert live.is_archived is False
    assert archived.is_archived is True


def test_str_includes_reference_and_name():
    customer = CustomerFactory(client_id="CL-00321", name="Named Person")

    assert str(customer) == "CL-00321 Named Person"


def test_generated_reference_orders_numerically_past_five_digits():
    """
    The lexicographic-sort bug (research.md section 2).

    With order_by("-client_id") on a CharField, "CL-99999" sorts above
    "CL-100000" and the generator would return CL-100000 again -- a
    collision with a live row. Ordering on the numeric suffix is correct at
    any width. This failure is data-dependent and would never surface in a
    test built only on the 3,000-row dataset.
    """
    CustomerFactory(client_id="CL-99999")
    CustomerFactory(client_id="CL-100000")

    customer = Customer.objects.create_with_reference(
        name="Wide", email="w@example.com", phone="1", age=30,
        gender="Other", location="X", lead_source="Web",
    )

    assert customer.client_id == "CL-100001"
