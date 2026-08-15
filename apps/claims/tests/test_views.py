"""
Claims API behaviour (FR-016 through FR-024) and the anomalies read API.

Replaces the Phase 1 placeholder's tests (FR-049). The placeholder asserted
GET /api/claims/placeholder/ returned a stub; those assertions are replaced
rather than deleted, so claims never has an untested route.
"""
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.claims.factories import ClaimFactory, ClaimLoadAnomalyFactory
from apps.claims.models import Claim, ClaimStatus
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db

URL = "/api/claims/"
ANOMALY_URL = "/api/claims/anomalies/"

READER = Role.CLAIMS_ADJUSTER
WRITER = Role.CLAIMS_ADJUSTER


# -- List and pagination (FR-017, SC-010) ----------------------------------


def test_list_returns_live_claims(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimFactory.create_batch(3)

    response = client.get(URL)

    assert response.status_code == 200
    assert response.data["count"] == 3


def test_list_paginates_at_fifty(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimFactory.create_batch(51)

    response = client.get(URL)

    assert response.data["count"] == 51
    assert len(response.data["results"]) == 50
    assert response.data["next"] is not None


def test_paging_yields_each_claim_exactly_once(authenticated_client):
    """SC-010: no claim omitted or repeated across pages."""
    client, _ = authenticated_client(READER)
    ClaimFactory.create_batch(75)

    first = client.get(URL).data["results"]
    second = client.get(URL, {"page": 2}).data["results"]

    ids = [row["id"] for row in first] + [row["id"] for row in second]
    assert len(ids) == 75
    assert len(set(ids)) == 75


def test_list_is_ordered_by_id(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimFactory.create_batch(5)

    ids = [row["id"] for row in client.get(URL).data["results"]]

    assert ids == sorted(ids)


def test_archived_claims_never_appear_in_list(authenticated_client):
    """FR-021: removal is invisible, not destructive."""
    client, _ = authenticated_client(READER)
    live = ClaimFactory()
    ClaimFactory(archived=True)

    response = client.get(URL)

    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == live.id


# -- Filters (FR-018, FR-019) ----------------------------------------------


def test_filter_by_policy(authenticated_client):
    client, _ = authenticated_client(READER)
    policy = PolicyFactory()
    ClaimFactory.create_batch(3, policy=policy)
    ClaimFactory()  # a claim against a different policy

    response = client.get(URL, {"policy": policy.id})

    assert response.data["count"] == 3
    assert {row["policy"]["id"] for row in response.data["results"]} == {policy.id}


def test_filter_by_status(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimFactory.create_batch(2, claim_status=ClaimStatus.APPROVED)
    ClaimFactory(claim_status=ClaimStatus.DENIED)

    response = client.get(URL, {"claim_status": "Approved"})

    assert response.data["count"] == 2
    assert {row["claim_status"] for row in response.data["results"]} == {"Approved"}


def test_filters_combine(authenticated_client):
    client, _ = authenticated_client(READER)
    policy = PolicyFactory()
    ClaimFactory(policy=policy, claim_status=ClaimStatus.APPROVED)
    ClaimFactory(policy=policy, claim_status=ClaimStatus.DENIED)

    response = client.get(URL, {"policy": policy.id, "claim_status": "Approved"})

    assert response.data["count"] == 1


# -- Retrieve (FR-016, FR-023) ---------------------------------------------


def test_retrieve_returns_the_claim(authenticated_client):
    client, _ = authenticated_client(READER)
    claim = ClaimFactory()

    response = client.get(f"{URL}{claim.id}/")

    assert response.status_code == 200
    assert response.data["id"] == claim.id


def test_retrieve_embeds_policy_type(authenticated_client):
    """FR-023, SC-001: coverage type without a second request."""
    client, _ = authenticated_client(READER)
    claim = ClaimFactory(policy=PolicyFactory(policy_type="Health"))

    response = client.get(f"{URL}{claim.id}/")

    assert response.data["policy"]["policy_type"] == "Health"


def test_retrieve_archived_claim_returns_404(authenticated_client):
    client, _ = authenticated_client(READER)
    claim = ClaimFactory(archived=True)

    response = client.get(f"{URL}{claim.id}/")

    assert response.status_code == 404


def test_permitted_user_missing_claim_returns_404(authenticated_client):
    client, _ = authenticated_client(READER)

    response = client.get(f"{URL}999999/")

    assert response.status_code == 404


# -- Create (FR-020) -------------------------------------------------------


def test_create_records_a_claim(authenticated_client):
    client, _ = authenticated_client(WRITER)
    policy = PolicyFactory()

    response = client.post(
        URL,
        {"policy": policy.id, "claim_status": "Filed", "claim_amount_usd": "0.00"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["id"] is not None
    assert Claim.objects.count() == 1


def test_create_with_negative_amount_refused_and_stores_nothing(authenticated_client):
    client, _ = authenticated_client(WRITER)

    response = client.post(
        URL,
        {
            "policy": PolicyFactory().id,
            "claim_status": "Filed",
            "claim_amount_usd": "-5.00",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "claim_amount_usd" in response.data
    assert Claim.objects.count() == 0


def test_create_against_archived_policy_refused(authenticated_client):
    client, _ = authenticated_client(WRITER)

    response = client.post(
        URL,
        {
            "policy": PolicyFactory(archived=True).id,
            "claim_status": "Filed",
            "claim_amount_usd": "10.00",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "policy" in response.data


# -- Update (FR-020, FR-022, FR-024) ---------------------------------------


def test_patch_amends_status(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_status=ClaimStatus.FILED)

    response = client.patch(
        f"{URL}{claim.id}/", {"claim_status": "Approved"}, format="json"
    )

    assert response.status_code == 200
    claim.refresh_from_db()
    assert claim.claim_status == "Approved"


def test_patch_amends_amount(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_amount_usd=Decimal("100.00"))

    response = client.patch(
        f"{URL}{claim.id}/", {"claim_amount_usd": "250.50"}, format="json"
    )

    assert response.status_code == 200
    claim.refresh_from_db()
    assert claim.claim_amount_usd == Decimal("250.50")


def test_patch_cannot_reassign_policy(authenticated_client):
    """
    FR-022: reassignment would silently rewrite the coverage context a
    claim was judged under. Supplying `policy` is ignored, not an error,
    consistent with DRF read-only field handling.
    """
    client, _ = authenticated_client(WRITER)
    original = PolicyFactory()
    claim = ClaimFactory(policy=original)
    other = PolicyFactory()

    response = client.patch(f"{URL}{claim.id}/", {"policy": other.id}, format="json")

    assert response.status_code == 200
    claim.refresh_from_db()
    assert claim.policy_id == original.id


def test_no_status_transition_is_enforced(authenticated_client):
    """FR-024: status is a recorded fact, not a state machine."""
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_status=ClaimStatus.APPROVED)

    response = client.patch(
        f"{URL}{claim.id}/", {"claim_status": "Filed"}, format="json"
    )

    assert response.status_code == 200


# -- Delete (FR-021) -------------------------------------------------------


def test_delete_archives_rather_than_destroys(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory()

    response = client.delete(f"{URL}{claim.id}/")

    assert response.status_code == 204
    assert not Claim.objects.filter(id=claim.id).exists()
    # Recoverable in storage.
    assert Claim.all_objects.filter(id=claim.id).exists()
    claim.refresh_from_db()
    assert claim.archived_at is not None


def test_deleted_claim_vanishes_from_list_and_detail(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory()
    client.delete(f"{URL}{claim.id}/")

    assert client.get(URL).data["count"] == 0
    assert client.get(f"{URL}{claim.id}/").status_code == 404


# -- Anomalies read API ----------------------------------------------------


def test_anomaly_list_returns_anomalies(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimLoadAnomalyFactory.create_batch(3)

    response = client.get(ANOMALY_URL)

    assert response.status_code == 200
    assert response.data["count"] == 3


def test_anomaly_list_paginates_at_fifty(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimLoadAnomalyFactory.create_batch(51)

    response = client.get(ANOMALY_URL)

    assert len(response.data["results"]) == 50


def test_anomaly_shape_quotes_the_source(authenticated_client):
    """source_status reads "No Claim" -- a value Claim refuses to represent."""
    client, _ = authenticated_client(READER)
    anomaly = ClaimLoadAnomalyFactory(source_amount_usd=Decimal("19919.13"))

    response = client.get(f"{ANOMALY_URL}{anomaly.id}/")

    assert response.status_code == 200
    assert response.data["source_status"] == "No Claim"
    assert response.data["source_amount_usd"] == "19919.13"
    assert response.data["policy"]["policy_type"] is not None


def test_anomaly_filter_by_policy(authenticated_client):
    client, _ = authenticated_client(READER)
    anomaly = ClaimLoadAnomalyFactory()
    ClaimLoadAnomalyFactory()

    response = client.get(ANOMALY_URL, {"policy": anomaly.policy_id})

    assert response.data["count"] == 1


def test_anomaly_filter_by_status(authenticated_client):
    client, _ = authenticated_client(READER)
    ClaimLoadAnomalyFactory()
    ClaimLoadAnomalyFactory(cleared_corrected=True)

    assert client.get(ANOMALY_URL, {"status": "open"}).data["count"] == 1
    assert client.get(ANOMALY_URL, {"status": "cleared"}).data["count"] == 1


def test_cleared_reason_filter_excludes_absent_from_corrections(authenticated_client):
    """
    FR-044a / SC-013 -- the query this endpoint exists to make possible.

    Counting all cleared rows would silently include rows that merely
    vanished from an export, understating source inconsistency invisibly.
    """
    client, _ = authenticated_client(READER)
    ClaimLoadAnomalyFactory(cleared_corrected=True)
    ClaimLoadAnomalyFactory(cleared_absent=True)
    ClaimLoadAnomalyFactory(cleared_absent=True)

    corrected = client.get(
        ANOMALY_URL, {"status": "cleared", "cleared_reason": "corrected"}
    )
    absent = client.get(ANOMALY_URL, {"status": "cleared", "cleared_reason": "absent"})

    assert corrected.data["count"] == 1
    assert absent.data["count"] == 2


def test_open_anomaly_has_null_cleared_reason(authenticated_client):
    """There is no reasonless clearing, and no empty-string reason."""
    client, _ = authenticated_client(READER)
    anomaly = ClaimLoadAnomalyFactory()

    response = client.get(f"{ANOMALY_URL}{anomaly.id}/")

    assert response.data["cleared_reason"] is None
    assert response.data["cleared_at"] is None


@pytest.mark.parametrize("method,payload", [("post", {}), ("patch", {}), ("delete", None)])
def test_anomalies_are_read_only(authenticated_client, method, payload):
    """The loader is the only writer. No manual clear/dismiss exists."""
    client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)
    anomaly = ClaimLoadAnomalyFactory()

    url = ANOMALY_URL if method == "post" else f"{ANOMALY_URL}{anomaly.id}/"
    response = getattr(client, method)(url, payload, format="json")

    assert response.status_code in (403, 404, 405)


# -- The placeholder is gone (FR-049) --------------------------------------


def test_placeholder_route_no_longer_exists(authenticated_client):
    client, _ = authenticated_client(Role.SYSTEM_ADMINISTRATOR)

    response = client.get("/api/claims/placeholder/")

    assert response.status_code == 404
