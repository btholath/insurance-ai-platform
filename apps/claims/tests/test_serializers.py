"""
ClaimSerializer: the single definition of claim validity.

Both the API and the dataset loader construct this serializer rather than
writing models directly, so the loader's validation and the API's hold by
construction rather than by two definitions kept in step by hand.
"""
from decimal import Decimal

import pytest

from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimStatus
from apps.claims.serializers import ClaimSerializer
from apps.customers.factories import CustomerFactory
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db


# -- Read shape (FR-023, SC-001) -------------------------------------------


def test_read_embeds_policy_summary_with_coverage_type():
    """FR-023: a retrieval identifies the policy AND its coverage type."""
    policy = PolicyFactory(policy_type="Auto")
    claim = ClaimFactory(policy=policy)

    data = ClaimSerializer(claim).data

    assert data["policy"]["id"] == policy.id
    assert data["policy"]["policy_type"] == "Auto"


def test_read_embeds_customer_through_the_policy():
    """No claim references a customer directly; the path is Claim -> Policy."""
    customer = CustomerFactory(client_id="CL-00004", name="Ada Lovelace")
    claim = ClaimFactory(policy=PolicyFactory(customer=customer))

    data = ClaimSerializer(claim).data

    assert data["policy"]["customer"]["client_id"] == "CL-00004"
    assert data["policy"]["customer"]["name"] == "Ada Lovelace"


def test_read_shape_carries_status_and_amount():
    claim = ClaimFactory(
        claim_status=ClaimStatus.APPROVED, claim_amount_usd=Decimal("1204.55")
    )

    data = ClaimSerializer(claim).data

    assert data["claim_status"] == "Approved"
    assert data["claim_amount_usd"] == "1204.55"


# -- Status validation (FR-010, FR-012) ------------------------------------


def test_unrecognised_status_refused_naming_the_field():
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "Escalated",
            "claim_amount_usd": "10.00",
        }
    )

    assert not serializer.is_valid()
    assert "claim_status" in serializer.errors


def test_no_claim_status_refused_naming_the_field():
    """FR-012: consistent with FR-004, `No Claim` is not a claim."""
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "No Claim",
            "claim_amount_usd": "10.00",
        }
    )

    assert not serializer.is_valid()
    assert "claim_status" in serializer.errors


def test_no_claim_message_explains_the_absence_rule():
    """
    The message must say more than "not a valid choice", or an adjuster
    reads it as a bug rather than as the modelling decision it is.
    """
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "No Claim",
            "claim_amount_usd": "10.00",
        }
    )
    serializer.is_valid()

    message = " ".join(str(m) for m in serializer.errors["claim_status"]).lower()
    assert "absence" in message
    assert "record" in message


# -- Amount validation (FR-011) --------------------------------------------


def test_negative_amount_refused_naming_the_field():
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "Filed",
            "claim_amount_usd": "-0.01",
        }
    )

    assert not serializer.is_valid()
    assert "claim_amount_usd" in serializer.errors


def test_zero_amount_is_accepted():
    """1,507 of 3,000 source rows carry exactly 0.00."""
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "Filed",
            "claim_amount_usd": "0.00",
        }
    )

    assert serializer.is_valid(), serializer.errors


def test_omitted_amount_is_refused_and_distinct_from_zero():
    """FR-011: zero must remain distinguishable from absent."""
    serializer = ClaimSerializer(
        data={"policy": PolicyFactory().pk, "claim_status": "Filed"}
    )

    assert not serializer.is_valid()
    assert "claim_amount_usd" in serializer.errors


# -- Policy validation (FR-002, FR-013, FR-014) ----------------------------


def test_missing_policy_refused_naming_the_field():
    serializer = ClaimSerializer(
        data={"claim_status": "Filed", "claim_amount_usd": "10.00"}
    )

    assert not serializer.is_valid()
    assert "policy" in serializer.errors


def test_nonexistent_policy_refused_naming_the_field():
    serializer = ClaimSerializer(
        data={"policy": 999999, "claim_status": "Filed", "claim_amount_usd": "10.00"}
    )

    assert not serializer.is_valid()
    assert "policy" in serializer.errors


def test_archived_policy_refused_and_says_archived_not_missing():
    """
    FR-014. Resolved through Policy.all_objects so the message can say the
    policy is ARCHIVED rather than nonexistent -- reporting "does not
    exist" for a policy that is right there sends an adjuster hunting.
    """
    archived = PolicyFactory(archived=True)

    serializer = ClaimSerializer(
        data={
            "policy": archived.pk,
            "claim_status": "Filed",
            "claim_amount_usd": "10.00",
        }
    )

    assert not serializer.is_valid()
    assert "policy" in serializer.errors
    assert "archiv" in " ".join(str(m) for m in serializer.errors["policy"]).lower()


def test_valid_claim_against_live_policy_passes():
    serializer = ClaimSerializer(
        data={
            "policy": PolicyFactory().pk,
            "claim_status": "Approved",
            "claim_amount_usd": "1204.55",
        }
    )

    assert serializer.is_valid(), serializer.errors
