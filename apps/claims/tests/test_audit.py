"""
Claim auditing (FR-029 through FR-034, FR-039, FR-048, FR-048a).

Two things this file pins that are easy to lose:

1. FR-033 -- an amendment records ONLY the fields that actually changed. A
   PATCH setting a status to the value it already has must write an empty
   diff, not a fabricated one, or the trail asserts changes that never
   happened.

2. FR-048a -- the two anomaly clearing reasons are DISTINCT ACTION NAMES,
   not one action with a reason buried in context. `action` is indexed; a
   JSON context key is not. This is what lets a later phase ask "every
   confirmed correction, ever" as a single indexed query, and what keeps
   "we verified this was fixed" separable from "we stopped seeing it".
"""
import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.claims.factories import ClaimFactory
from apps.claims.models import ClaimLoadAnomaly, ClaimStatus
from apps.core import audit_routes
from apps.policies.factories import PolicyFactory

pytestmark = pytest.mark.django_db

URL = "/api/claims/"
ANOMALY_URL = "/api/claims/anomalies/"
WRITER = Role.CLAIMS_ADJUSTER

HEADER = [
    "Client_ID", "Client_Name", "Client_Email", "Client_Phone", "Client_Age",
    "Client_Gender", "Client_Location", "Policy_Type", "Policy_Start_Date",
    "Policy_End_Date", "Policy_Premium_USD", "Claim_Status", "Claim_Amount_USD",
    "Last_Interaction", "Risk_Score", "Renewal_Probability", "Fraud_Risk_Flag",
    "Cross_Sell_Score", "Lead_Source", "Client_Feedback",
]


def _row(client_id="CL-00001", claim_status="Approved", claim_amount="1204.55"):
    return {
        "Client_ID": client_id, "Client_Name": "Patrick Hart",
        "Client_Email": f"{client_id.lower()}@example.com",
        "Client_Phone": "588-240-1527", "Client_Age": "25",
        "Client_Gender": "Other", "Client_Location": "New Steven",
        "Policy_Type": "Auto", "Policy_Start_Date": "2023-01-13",
        "Policy_End_Date": "2027-03-11", "Policy_Premium_USD": "750.23",
        "Claim_Status": claim_status, "Claim_Amount_USD": claim_amount,
        "Last_Interaction": "2024-12-02", "Risk_Score": "0.16",
        "Renewal_Probability": "0.06", "Fraud_Risk_Flag": "Low",
        "Cross_Sell_Score": "0.75", "Lead_Source": "Agent",
        "Client_Feedback": "Helpful.",
    }


@pytest.fixture
def write_csv(tmp_path):
    def _write(rows, name="data.csv"):
        path = tmp_path / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        return str(path)

    return _write


def load(path, **kwargs):
    call_command("loaddataset", path, stdout=StringIO(), **kwargs)


# -- Create / amend / remove (FR-029, SC-004) ------------------------------


def test_create_writes_an_audit_entry(authenticated_client):
    client, user = authenticated_client(WRITER)
    policy = PolicyFactory()

    client.post(
        URL,
        {"policy": policy.id, "claim_status": "Filed", "claim_amount_usd": "10.00"},
        format="json",
    )

    entry = AuditLog.objects.get(action="claim.created")
    assert entry.actor == user
    assert entry.actor_identifier == user.email
    assert entry.target_type == "claims.Claim"
    assert entry.outcome == "succeeded"
    assert entry.after["claim_status"] == "Filed"
    assert entry.timestamp is not None


def test_amend_records_before_and_after(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_status=ClaimStatus.FILED)

    client.patch(f"{URL}{claim.id}/", {"claim_status": "Approved"}, format="json")

    entry = AuditLog.objects.get(action="claim.updated")
    assert entry.before == {"claim_status": "Filed"}
    assert entry.after == {"claim_status": "Approved"}


def test_previous_values_are_recoverable_from_the_trail(authenticated_client):
    """SC-004: the values before an amendment are recoverable."""
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_amount_usd=Decimal("100.00"))

    client.patch(f"{URL}{claim.id}/", {"claim_amount_usd": "250.50"}, format="json")

    entry = AuditLog.objects.get(action="claim.updated")
    assert entry.before["claim_amount_usd"] == "100.00"


def test_remove_writes_an_audit_entry(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory()

    client.delete(f"{URL}{claim.id}/")

    entry = AuditLog.objects.get(action="claim.deleted")
    assert entry.target_id == str(claim.id)
    assert entry.before is not None
    assert entry.after is None


# -- Only changed fields (FR-033) ------------------------------------------


def test_amendment_records_only_fields_that_changed(authenticated_client):
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(
        claim_status=ClaimStatus.FILED, claim_amount_usd=Decimal("100.00")
    )

    client.patch(
        f"{URL}{claim.id}/",
        {"claim_status": "Approved", "claim_amount_usd": "100.00"},
        format="json",
    )

    entry = AuditLog.objects.get(action="claim.updated")
    assert "claim_status" in entry.before
    # The amount was submitted but did not change, so it must not appear.
    assert "claim_amount_usd" not in entry.before


def test_no_op_amendment_writes_an_empty_diff_not_a_fabricated_one(
    authenticated_client,
):
    """
    A PATCH setting a status to the value it already has. The entry is
    still written -- the request happened -- but it must not assert a
    change that did not occur.
    """
    client, _ = authenticated_client(WRITER)
    claim = ClaimFactory(claim_status=ClaimStatus.APPROVED)

    client.patch(f"{URL}{claim.id}/", {"claim_status": "Approved"}, format="json")

    entry = AuditLog.objects.get(action="claim.updated")
    assert entry.before is None
    assert entry.after is None


# -- Refusals (FR-031, FR-032) ---------------------------------------------


def test_refused_read_is_recorded(authenticated_client):
    client, user = authenticated_client(Role.UNDERWRITER)  # may not read claims
    ClaimFactory()

    client.get(URL)

    entry = AuditLog.objects.get(outcome="refused")
    assert entry.actor == user
    assert entry.action.startswith("claim.")


def test_refusal_does_not_alter_the_response_the_caller_receives(
    authenticated_client,
):
    client, _ = authenticated_client(Role.UNDERWRITER)
    ClaimFactory()

    response = client.get(URL)

    assert response.status_code == 403
    assert AuditLog.objects.filter(outcome="refused").exists()


def test_refused_write_is_recorded(authenticated_client):
    client, _ = authenticated_client(Role.FRAUD_ANALYST)  # reads, cannot write
    claim = ClaimFactory()

    client.delete(f"{URL}{claim.id}/")

    assert AuditLog.objects.filter(outcome="refused").exists()


def test_permitted_users_miss_is_not_recorded_as_a_refusal(authenticated_client):
    """FR-032: an ordinary miss is not a refusal."""
    client, _ = authenticated_client(Role.CLAIMS_ADJUSTER)

    client.get(f"{URL}999999/")

    assert not AuditLog.objects.filter(outcome="refused").exists()


def test_underwriters_claim_404_is_a_refusal_but_their_policy_404_is_not(
    authenticated_client,
):
    """
    The sharp case the per-module registry exists for. Same user, same
    status code, two different meanings -- and only per-module role sets
    can tell them apart.
    """
    client, _ = authenticated_client(Role.UNDERWRITER)

    client.get(f"{URL}999999/")
    claim_refusals = AuditLog.objects.filter(outcome="refused").count()

    # The trail is append-only, so the policy request is counted by
    # difference rather than by clearing the table between the two.
    client.get("/api/policies/999999/")
    policy_refusals = (
        AuditLog.objects.filter(outcome="refused").count() - claim_refusals
    )

    assert claim_refusals == 1  # not permitted to read claims -> refusal
    assert policy_refusals == 0  # permitted to read policies -> ordinary miss


def test_anomaly_refusal_is_recorded(authenticated_client):
    """The anomaly routes are covered by the same /api/claims/ entry."""
    client, _ = authenticated_client(Role.CUSTOMER_SERVICE)

    client.get(ANOMALY_URL)

    assert AuditLog.objects.filter(outcome="refused").exists()


# -- The registry is the whole change (FR-030, SC-008) ---------------------


def test_claims_is_registered_in_the_audited_route_registry():
    route = audit_routes.match("/api/claims/")

    assert route is not None
    assert route.target_type == "claims.Claim"
    assert route.action_prefix == "claim"


def test_registered_roles_are_the_claim_role_sets_not_another_modules():
    """
    FR-030 is explicit that the role sets registered for claims MUST be
    the CLAIM role sets. Copying Policy's by habit would silently give
    Underwriter and Product Manager the wrong refusal semantics.
    """
    route = audit_routes.match("/api/claims/")

    assert set(route.view_roles) == {
        Role.CLAIMS_ADJUSTER,
        Role.FRAUD_ANALYST,
        Role.COMPLIANCE_OFFICER,
        Role.RISK_MANAGER,
        Role.SYSTEM_ADMINISTRATOR,
    }
    assert set(route.write_roles) == {
        Role.CLAIMS_ADJUSTER,
        Role.SYSTEM_ADMINISTRATOR,
    }


def test_anomaly_routes_resolve_to_the_claims_entry():
    """
    Nested under /api/claims/ and sharing its role sets, so the single
    entry covers them. No second registration is needed (research §8).
    """
    route = audit_routes.match("/api/claims/anomalies/")

    assert route is not None
    assert route.target_type == "claims.Claim"


def test_claims_is_a_registered_consumer():
    """
    Originally asserted claims was the registry's THIRD (and, at the time,
    final) consumer -- a closed-world assertion Phase 3a necessarily broke
    by registering risk as a fourth. Relaxed to membership rather than
    exact-set equality, the same predicted-swap treatment T082 applied to
    apps/core/tests/test_audit_routes.py's own closed-world assertion:
    the guarantee under test (claims is registered) is unchanged, only
    the shape of the check.
    """
    prefixes = {route.prefix for route in audit_routes.all_routes()}

    assert {"/api/customers/", "/api/policies/", "/api/claims/"} <= prefixes


# -- Load attribution (FR-039, FR-048) -------------------------------------


def test_loader_claim_entries_are_attributed_to_the_system(write_csv):
    load(write_csv([_row()]))

    entry = AuditLog.objects.get(action="claim.created")
    assert entry.actor is None
    assert entry.actor_identifier == ""
    assert entry.context["source"] == "loaddataset"


def test_loader_anomaly_entries_are_attributed_to_the_system(write_csv):
    load(write_csv([_row(claim_status="No Claim", claim_amount="500.00")]))

    entry = AuditLog.objects.get(action="claim_anomaly.recorded")
    assert entry.actor is None
    assert entry.target_type == "claims.ClaimLoadAnomaly"
    assert entry.context["source"] == "loaddataset"


# -- Clearing reasons are distinct actions (FR-048a, SC-013) ---------------


def test_corrected_and_absent_are_separate_action_names(write_csv):
    both = write_csv([
        _row(client_id="CL-00001", claim_status="No Claim", claim_amount="500.00"),
        _row(client_id="CL-00002", claim_status="No Claim", claim_amount="700.00"),
    ])
    load(both)

    # CL-00001 comes back fixed; CL-00002 vanishes.
    load(write_csv(
        [_row(client_id="CL-00001", claim_status="No Claim", claim_amount="0.0")],
        name="second.csv",
    ))

    assert AuditLog.objects.filter(action="claim_anomaly.cleared_corrected").count() == 1
    assert AuditLog.objects.filter(action="claim_anomaly.cleared_absent").count() == 1


def test_full_clearing_history_survives_reraise(write_csv):
    """
    FR-048a. The anomaly row keeps only its LATEST state -- re-raising
    resets cleared_reason to null -- so the append-only trail is the only
    place a cleared/re-raised/cleared sequence survives intact.
    """
    conflicting = write_csv([_row(claim_status="No Claim", claim_amount="500.00")])
    fixed = write_csv(
        [_row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )

    load(conflicting)   # recorded
    load(fixed)         # cleared_corrected
    load(conflicting)   # reraised
    load(fixed)         # cleared_corrected again

    anomaly = ClaimLoadAnomaly.objects.get()
    history = list(
        AuditLog.objects.filter(
            target_type="claims.ClaimLoadAnomaly", target_id=str(anomaly.id)
        )
        .order_by("timestamp", "id")
        .values_list("action", flat=True)
    )

    assert history == [
        "claim_anomaly.recorded",
        "claim_anomaly.cleared_corrected",
        "claim_anomaly.reraised",
        "claim_anomaly.cleared_corrected",
    ]
    # ...while the row itself remembers only the last clearing.
    assert anomaly.cleared_reason == "corrected"


def test_a_consumer_can_count_confirmed_corrections_excluding_absence(write_csv):
    """
    SC-013 stated as the query a later phase actually runs. Counting all
    clearings would include the absent one and overstate what was verified.
    """
    both = write_csv([
        _row(client_id="CL-00001", claim_status="No Claim", claim_amount="500.00"),
        _row(client_id="CL-00002", claim_status="No Claim", claim_amount="700.00"),
    ])
    load(both)
    load(write_csv(
        [_row(client_id="CL-00001", claim_status="No Claim", claim_amount="0.0")],
        name="second.csv",
    ))

    confirmed = AuditLog.objects.filter(
        action="claim_anomaly.cleared_corrected"
    ).count()
    all_clearings = AuditLog.objects.filter(
        action__startswith="claim_anomaly.cleared_"
    ).count()

    assert confirmed == 1
    assert all_clearings == 2  # the difference is the point


# -- Append-only and same-transaction (FR-034) -----------------------------


def test_a_claim_audit_entry_cannot_be_altered(authenticated_client):
    """FR-034: not alterable after the fact."""
    client, _ = authenticated_client(WRITER)
    client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )
    entry = AuditLog.objects.get(action="claim.created")

    entry.action = "claim.tampered"
    with pytest.raises(NotImplementedError):
        entry.save()


def test_a_claim_audit_entry_cannot_be_removed(authenticated_client):
    client, _ = authenticated_client(WRITER)
    client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )
    entry = AuditLog.objects.get(action="claim.created")

    with pytest.raises(NotImplementedError):
        entry.delete()


def test_an_anomaly_audit_entry_cannot_be_removed(write_csv):
    """The clearing history FR-048a depends on must be undeletable."""
    load(write_csv([_row(claim_status="No Claim", claim_amount="500.00")]))
    entry = AuditLog.objects.get(action="claim_anomaly.recorded")

    with pytest.raises(NotImplementedError):
        entry.delete()


def test_a_stored_change_without_its_audit_entry_cannot_occur(authenticated_client):
    """
    FR-034: the audit write is inside the same transaction as the change,
    so the two commit together or not at all.
    """
    from apps.claims.models import Claim

    client, _ = authenticated_client(WRITER)
    client.post(
        URL,
        {"policy": PolicyFactory().id, "claim_status": "Filed", "claim_amount_usd": "1.00"},
        format="json",
    )

    assert Claim.objects.count() == AuditLog.objects.filter(
        action="claim.created"
    ).count()
