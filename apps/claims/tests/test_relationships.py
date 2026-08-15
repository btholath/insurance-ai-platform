"""
Claim <-> Policy relationship rules (FR-008, FR-009, SC-007).

The two requirements here point in opposite directions and are easy to
conflate:

- FR-008: archiving a policy leaves its claims READABLE. Withdrawing
  coverage must not erase claim history.
- FR-009: hard-deleting a policy that carries claims is PREVENTED, so no
  claim is ever orphaned.

Same relationship, two different operations, two different answers.
"""
import pytest
from django.db.models import ProtectedError

from apps.accounts.models import Role
from apps.claims.factories import ClaimFactory, ClaimLoadAnomalyFactory
from apps.claims.models import Claim
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db

URL = "/api/claims/"


# -- FR-008: claims survive policy archival --------------------------------


def test_claim_remains_readable_when_its_policy_is_archived(authenticated_client):
    """
    The reverse of the instinct to hide it. Claim.objects filters on the
    CLAIM's archived_at, not the policy's, so a live claim against an
    archived policy stays visible -- which is exactly what FR-008 requires.
    """
    client, _ = authenticated_client(Role.CLAIMS_ADJUSTER)
    policy = PolicyFactory(archived=True)
    claim = ClaimFactory(policy=policy)

    listing = client.get(URL)
    detail = client.get(f"{URL}{claim.id}/")

    assert listing.data["count"] == 1
    assert detail.status_code == 200
    assert detail.data["policy"]["id"] == policy.id


def test_claim_retains_its_link_to_an_archived_policy():
    policy = PolicyFactory()
    claim = ClaimFactory(policy=policy)

    policy.archived_at = "2026-01-01T00:00:00Z"
    policy.save(update_fields=["archived_at"])

    claim.refresh_from_db()
    assert claim.policy_id == policy.id
    # The FK resolves to the row, not to its live-ness.
    assert claim.policy.archived_at is not None


def test_archiving_a_policy_does_not_archive_its_claims():
    policy = PolicyFactory()
    claim = ClaimFactory(policy=policy)

    policy.archived_at = "2026-01-01T00:00:00Z"
    policy.save(update_fields=["archived_at"])

    claim.refresh_from_db()
    assert claim.archived_at is None
    assert Claim.objects.filter(id=claim.id).exists()


# -- FR-009 / SC-007: a policy carrying claims cannot be destroyed ---------


def test_hard_deleting_a_policy_with_claims_is_prevented():
    policy = PolicyFactory()
    ClaimFactory(policy=policy)

    with pytest.raises(ProtectedError):
        policy.delete()


def test_hard_deleting_a_policy_with_only_an_anomaly_is_also_prevented():
    """
    The anomaly table is protective too. Destroying the policy would orphan
    the anomaly's only reference to what the source said.
    """
    policy = PolicyFactory()
    ClaimLoadAnomalyFactory(policy=policy)

    with pytest.raises(ProtectedError):
        policy.delete()


def test_a_policy_with_no_claims_can_still_be_deleted():
    """PROTECT must not become a blanket ban on deletion."""
    policy = PolicyFactory()

    policy.delete()  # must not raise


def test_archived_claim_still_protects_its_policy():
    """
    Archival is not deletion: the row is still there, still referencing
    the policy, so PROTECT still applies.
    """
    policy = PolicyFactory()
    ClaimFactory(policy=policy, archived=True)

    with pytest.raises(ProtectedError):
        policy.delete()
