"""
Claim and ClaimLoadAnomaly model behaviour.

The status choices test (FR-004, FR-012) is the highest-value test in this
file: `No Claim` being absent from ClaimStatus is what makes FR-004 a
structural guarantee rather than a runtime convention any future code path
could violate silently.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import BigAutoField
from django.utils import timezone

from apps.claims.models import Claim, ClaimLoadAnomaly, ClaimStatus
from apps.core.models import TimeStampedModel
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db


# -- Claim field shape (FR-001, FR-005, FR-006, FR-017) --------------------


def test_claim_inherits_timestamped_model():
    assert issubclass(Claim, TimeStampedModel)


def test_claim_records_created_and_updated(claim_factory):
    claim = claim_factory()

    assert claim.created_at is not None
    assert claim.updated_at is not None


def test_claim_id_is_the_only_identity(claim_factory):
    """FR-006: a stable identifier independent of any source value."""
    claim = claim_factory()

    assert isinstance(Claim._meta.pk, BigAutoField)
    assert claim.id is not None
    # No external reference field carried over from the dataset.
    field_names = {f.name for f in Claim._meta.get_fields()}
    assert "claim_id" not in field_names
    assert "external_id" not in field_names


def test_claim_ordering_is_by_id():
    """FR-017: stable paging depends on a deterministic order."""
    assert Claim._meta.ordering == ["id"]


def test_claim_amount_is_not_nullable():
    """FR-011: zero must stay distinguishable from absent."""
    assert Claim._meta.get_field("claim_amount_usd").null is False


def test_claim_policy_is_required():
    """FR-002: every claim is filed against exactly one policy."""
    assert Claim._meta.get_field("policy").null is False


def test_policy_carries_many_claims(claim_factory):
    """FR-003: a second claim against one policy is not refused."""
    policy = PolicyFactory()

    claim_factory(policy=policy)
    claim_factory(policy=policy)

    assert policy.claims.count() == 2


def test_identical_claims_against_one_policy_are_both_stored(claim_factory):
    """FR-007: two identical claims are legitimately distinct events."""
    policy = PolicyFactory()

    first = claim_factory(
        policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00")
    )
    second = claim_factory(
        policy=policy, claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("500.00")
    )

    assert first.id != second.id
    assert Claim.objects.filter(policy=policy).count() == 2


def test_claim_has_no_uniqueness_constraint():
    """
    FR-007: no UniqueConstraint and no unique_together, deliberately.

    Asserted structurally rather than only behaviourally so that adding one
    later fails loudly instead of silently refusing a valid second claim.
    """
    from django.db.models import UniqueConstraint

    assert not any(
        isinstance(c, UniqueConstraint) for c in Claim._meta.constraints
    )
    assert not Claim._meta.unique_together


# -- ClaimStatus: three values, not four (FR-004, FR-012) ------------------


def test_claim_status_choices_are_exactly_three():
    assert [c[0] for c in ClaimStatus.choices] == ["Approved", "Denied", "Filed"]


def test_no_claim_is_not_a_representable_status():
    """
    FR-004: `No Claim` describes the ABSENCE of a claim, so it can never be
    a stored claim's status. Making it unrepresentable in the model is what
    enforces FR-012 at the deepest layer.
    """
    assert "No Claim" not in [c[0] for c in ClaimStatus.choices]
    assert not hasattr(ClaimStatus, "NO_CLAIM")


# -- DB check constraints (FR-010, FR-011) ---------------------------------


def test_zero_amount_is_accepted(claim_factory):
    """FR-011: 1,507 of 3,000 source rows carry exactly 0.00."""
    claim = claim_factory(claim_amount_usd=Decimal("0.00"))

    claim.refresh_from_db()
    assert claim.claim_amount_usd == Decimal("0.00")


def test_negative_amount_rejected_by_db_constraint():
    """
    FR-011, enforced at the database level so a raw ORM write cannot
    bypass the serializer.
    """
    policy = PolicyFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Claim.all_objects.create(
                policy=policy,
                claim_status=ClaimStatus.APPROVED,
                claim_amount_usd=Decimal("-0.01"),
            )


def test_no_claim_status_rejected_by_db_constraint():
    """
    FR-004 held by the database itself: `choices` is a serializer/form-layer
    convention that raw ORM writes bypass, so the integrity of "no claim
    record ever says No Claim" is worth a constraint Postgres enforces.
    """
    policy = PolicyFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Claim.all_objects.create(
                policy=policy,
                claim_status="No Claim",
                claim_amount_usd=Decimal("100.00"),
            )


# -- Managers (FR-021, FR-028) ---------------------------------------------


def test_default_manager_hides_archived_claims(claim_factory):
    live = claim_factory()
    archived = claim_factory(archived=True)

    assert list(Claim.objects.all()) == [live]
    assert archived in Claim.all_objects.all()


def test_objects_is_the_default_manager():
    """Declared FIRST so it stays _default_manager, as PolicyManager is."""
    assert Claim._meta.default_manager_name in (None, "objects")
    assert Claim._default_manager.__class__.__name__ == "ClaimManager"


# -- ClaimLoadAnomaly (FR-042, FR-043, FR-044) -----------------------------


def test_anomaly_policy_is_unique():
    """FR-043: the idempotency key. One anomaly row per policy."""
    policy = PolicyFactory()
    ClaimLoadAnomaly.objects.create(
        policy=policy,
        source_status="No Claim",
        source_amount_usd=Decimal("19919.13"),
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        source_file="data/Insurance_Dataset.csv",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ClaimLoadAnomaly.objects.create(
                policy=policy,
                source_status="No Claim",
                source_amount_usd=Decimal("100.00"),
                first_observed_at=timezone.now(),
                last_observed_at=timezone.now(),
                source_file="data/Insurance_Dataset.csv",
            )


def test_anomaly_source_status_stores_no_claim():
    """
    The anomaly QUOTES the source, so it must store the very value the
    Claim model refuses to represent. Constraining this column to
    ClaimStatus would make the record unable to hold its own subject.
    """
    anomaly = ClaimLoadAnomaly.objects.create(
        policy=PolicyFactory(),
        source_status="No Claim",
        source_amount_usd=Decimal("8.52"),
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        source_file="f.csv",
    )

    anomaly.refresh_from_db()
    assert anomaly.source_status == "No Claim"


def test_anomaly_defaults_to_open_with_no_reason():
    """FR-044: cleared_reason is null while open. No reasonless clearing."""
    anomaly = ClaimLoadAnomaly.objects.create(
        policy=PolicyFactory(),
        source_status="No Claim",
        source_amount_usd=Decimal("8.52"),
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        source_file="f.csv",
    )

    assert anomaly.status == "open"
    assert anomaly.cleared_reason is None
    assert anomaly.cleared_at is None


def test_claim_str_names_status_amount_and_policy(claim_factory):
    """Appears in admin listings and error messages, so it must be legible."""
    policy = PolicyFactory()
    claim = claim_factory(
        policy=policy,
        claim_status=ClaimStatus.APPROVED,
        claim_amount_usd=Decimal("1204.55"),
    )

    assert str(claim) == f"Approved claim of 1204.55 on policy {policy.id}"


def test_is_archived_reflects_the_archived_marker(claim_factory):
    assert claim_factory().is_archived is False
    assert claim_factory(archived=True).is_archived is True


def test_anomaly_str_names_status_policy_and_source_status():
    policy = PolicyFactory()
    anomaly = ClaimLoadAnomaly.objects.create(
        policy=policy,
        source_status="No Claim",
        source_amount_usd=Decimal("8.52"),
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
        source_file="f.csv",
    )

    assert str(anomaly) == f"open anomaly on policy {policy.id} (No Claim)"


def test_anomaly_has_no_denormalised_history_field():
    """
    A deliberate non-field. A counter or history array here would be a
    second, mutable copy of what AuditLog holds immutably, and the two
    would drift with the mutable one winning by being closer to hand.
    """
    field_names = {f.name for f in ClaimLoadAnomaly._meta.get_fields()}

    assert "cleared_count" not in field_names
    assert "history" not in field_names
