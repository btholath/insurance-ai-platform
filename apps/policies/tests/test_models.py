"""
Model-level tests for Policy (T004 - T007).

Three properties here are invisible in ordinary use and expensive to find
later:

1. The renewal_probability CheckConstraint must accept NULL. Written without
   the isnull disjunction, a NULL makes the comparison SQL-NULL rather than
   true and Postgres rejects every policy created without a renewal
   probability -- which is every policy created through the API.
2. The (customer, policy_type) uniqueness must be scoped to LIVE rows.
   Spanning archived rows would mean archiving a customer's auto policy
   makes auto cover permanently impossible for them. This is deliberately
   the opposite of Customer, where an archived client_id stays reserved
   forever.
3. on_delete=PROTECT is the backstop against a hard customer delete
   destroying policy history.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer
from apps.policies.factories import PolicyFactory
from apps.policies.models import Policy

pytestmark = pytest.mark.django_db


def _raw_create(**overrides):
    """
    Insert bypassing PolicyFactory's SubFactory, so uniqueness and
    constraint assertions exercise a real INSERT rather than a fetch.
    """
    fields = dict(
        policy_type="Auto",
        start_date=date(2024, 1, 1),
        end_date=date(2026, 1, 1),
        premium_usd=Decimal("750.23"),
    )
    fields.update(overrides)
    if "customer" not in fields:
        fields["customer"] = CustomerFactory()
    return Policy.all_objects.create(**fields)


# ---------------------------------------------------------------------------
# T004: fields and constraints
# ---------------------------------------------------------------------------


def test_policy_stores_all_specified_fields():
    customer = CustomerFactory()
    policy = PolicyFactory(
        customer=customer,
        policy_type="Health",
        start_date=date(2023, 1, 13),
        end_date=date(2027, 3, 11),
        premium_usd=Decimal("750.23"),
        renewal_probability=Decimal("0.06"),
    )
    policy.refresh_from_db()

    assert policy.customer == customer
    assert policy.policy_type == "Health"
    assert policy.start_date == date(2023, 1, 13)
    assert policy.end_date == date(2027, 3, 11)
    assert policy.premium_usd == Decimal("750.23")
    assert policy.renewal_probability == Decimal("0.06")


def test_timestamps_populated_on_create():
    """FR-006."""
    policy = PolicyFactory()

    assert policy.created_at is not None
    assert policy.updated_at is not None


def test_end_date_must_be_after_start_date():
    """FR-010 constraint backstop."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(start_date=date(2025, 1, 1), end_date=date(2025, 1, 1))


def test_end_date_before_start_date_rejected():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(start_date=date(2025, 6, 1), end_date=date(2025, 1, 1))


def test_end_date_one_day_after_start_accepted():
    policy = _raw_create(start_date=date(2025, 1, 1), end_date=date(2025, 1, 2))

    assert policy.pk is not None


@pytest.mark.parametrize("premium", [Decimal("0.00"), Decimal("-1.00")])
def test_premium_must_be_positive(premium):
    """FR-011 constraint backstop."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(premium_usd=premium)


def test_smallest_positive_premium_accepted():
    policy = _raw_create(premium_usd=Decimal("0.01"))

    assert policy.premium_usd == Decimal("0.01")


def test_renewal_probability_accepts_null():
    """
    FR-004 / the SQL three-valued-logic trap.

    A policy with no renewal probability must insert cleanly. If the
    CheckConstraint omits the isnull disjunction this raises IntegrityError
    and every API-created policy becomes impossible.
    """
    policy = _raw_create(renewal_probability=None)
    policy.refresh_from_db()

    assert policy.renewal_probability is None


@pytest.mark.parametrize("value", [Decimal("0.00"), Decimal("1.00")])
def test_renewal_probability_boundaries_accepted(value):
    policy = _raw_create(renewal_probability=value)
    policy.refresh_from_db()

    assert policy.renewal_probability == value


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("1.01")])
def test_renewal_probability_outside_range_rejected(value):
    """FR-012."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(renewal_probability=value)


# ---------------------------------------------------------------------------
# T005: manager isolation
# ---------------------------------------------------------------------------


def test_objects_manager_excludes_archived():
    """FR-021."""
    live = PolicyFactory()
    PolicyFactory(archived=True)

    assert list(Policy.objects.all()) == [live]


def test_all_objects_manager_includes_archived():
    live = PolicyFactory()
    archived = PolicyFactory(archived=True)

    assert set(Policy.all_objects.all()) == {live, archived}


def test_default_manager_is_objects():
    """Keeps archived policies out of customer.policies traversal."""
    assert Policy._default_manager.__class__ is Policy.objects.__class__


def test_archived_policy_retained_not_deleted():
    """FR-021: removal is reversible archival, never destruction."""
    policy = PolicyFactory()
    pk = policy.pk

    policy.archived_at = timezone.now()
    policy.save()

    assert not Policy.objects.filter(pk=pk).exists()
    assert Policy.all_objects.filter(pk=pk).exists()


def test_is_archived_property():
    """Mirrors the same property on Customer."""
    live = PolicyFactory()
    archived = PolicyFactory(archived=True)

    assert live.is_archived is False
    assert archived.is_archived is True


# ---------------------------------------------------------------------------
# T006: live-scoped uniqueness -- the deliberate divergence from Customer
# ---------------------------------------------------------------------------


def test_customer_cannot_hold_two_live_policies_of_same_type():
    """FR-039's match key depends on this holding."""
    customer = CustomerFactory()
    _raw_create(customer=customer, policy_type="Auto")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_create(customer=customer, policy_type="Auto")


def test_customer_may_hold_policies_of_different_types():
    """FR-003."""
    customer = CustomerFactory()
    _raw_create(customer=customer, policy_type="Auto")
    second = _raw_create(customer=customer, policy_type="Health")

    assert second.pk is not None
    assert Policy.objects.filter(customer=customer).count() == 2


def test_archiving_a_policy_releases_the_coverage_slot():
    """
    The divergence from Customer, stated as a test so it is not later
    "fixed" into consistency.

    Customer reserves an archived client_id forever (FR-021 there requires
    the reference stay reserved). Here the opposite is required: archiving
    a customer's auto policy must not make auto cover permanently
    impossible for them.
    """
    customer = CustomerFactory()
    first = _raw_create(customer=customer, policy_type="Auto")

    first.archived_at = timezone.now()
    first.save()

    replacement = _raw_create(customer=customer, policy_type="Auto")

    assert replacement.pk is not None
    assert Policy.objects.filter(customer=customer, policy_type="Auto").count() == 1
    assert Policy.all_objects.filter(customer=customer, policy_type="Auto").count() == 2


def test_two_archived_policies_of_same_type_coexist():
    """The partial index must not constrain archived rows at all."""
    customer = CustomerFactory()
    for _ in range(2):
        _raw_create(customer=customer, policy_type="Life", archived_at=timezone.now())

    assert Policy.all_objects.filter(customer=customer, policy_type="Life").count() == 2


def test_different_customers_may_hold_same_policy_type():
    _raw_create(customer=CustomerFactory(), policy_type="Auto")
    second = _raw_create(customer=CustomerFactory(), policy_type="Auto")

    assert second.pk is not None


# ---------------------------------------------------------------------------
# T007: foreign key behaviour
# ---------------------------------------------------------------------------


def test_related_name_gives_customer_policies():
    """FR-019 depends on this."""
    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    assert list(customer.policies.all()) == [policy]


def test_customer_policies_excludes_archived_policies():
    """
    Reverse direction of the archival guarantee: related traversal uses
    the related model's _default_manager, which hides archived policies.
    """
    customer = CustomerFactory()
    live = PolicyFactory(customer=customer, policy_type="Auto")
    PolicyFactory(customer=customer, policy_type="Life", archived=True)

    assert list(customer.policies.all()) == [live]


def test_hard_delete_of_customer_is_protected():
    """
    FR-021 / Claims dependency: removing a customer must never become a
    mechanism for destroying policy history. Customer removal through the
    API is archival and never reaches this, but PROTECT is the backstop
    for the path that does.
    """
    customer = CustomerFactory()
    PolicyFactory(customer=customer)

    with pytest.raises(ProtectedError):
        with transaction.atomic():
            Customer.all_objects.filter(pk=customer.pk).delete()


def test_policy_requires_a_customer():
    """FR-002."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Policy.all_objects.create(
                customer=None,
                policy_type="Auto",
                start_date=date(2024, 1, 1),
                end_date=date(2026, 1, 1),
                premium_usd=Decimal("100.00"),
            )


def test_str_includes_type_and_customer_reference():
    customer = CustomerFactory(client_id="CL-00321")
    policy = PolicyFactory(customer=customer, policy_type="Health")

    assert "Health" in str(policy)
    assert "CL-00321" in str(policy)


# ---------------------------------------------------------------------------
# Factory traits
# ---------------------------------------------------------------------------


def test_factory_default_is_currently_in_force():
    """
    Without this, every factory-made policy would be in force and the
    FR-020 expiry filter would pass vacuously.
    """
    policy = PolicyFactory()
    today = date.today()

    assert policy.start_date < today < policy.end_date


def test_expired_trait_produces_ended_coverage():
    policy = PolicyFactory(expired=True)

    assert policy.end_date < date.today()


def test_scored_trait_sets_renewal_probability():
    policy = PolicyFactory(scored=True)

    assert policy.renewal_probability is not None
