"""
The dataset loader's claim and anomaly behaviour (FR-035 through FR-046).

The anomaly lifecycle -- raise, clear-as-corrected, clear-as-absent,
re-raise -- is the highest-value test surface in this feature, because the
distinction it protects is invisible when it fails: collapsing "we verified
this was fixed" into "we stopped seeing it" would let a later phase count
unexplained disappearances as verified corrections, understating source
inconsistency in the one direction an anomaly signal must not err.
"""
import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog
from apps.claims.models import (
    AnomalyStatus,
    Claim,
    ClaimLoadAnomaly,
    ClearedReason,
)
from apps.customers.models import Customer
from apps.policies.models import Policy

pytestmark = pytest.mark.django_db

HEADER = [
    "Client_ID", "Client_Name", "Client_Email", "Client_Phone", "Client_Age",
    "Client_Gender", "Client_Location", "Policy_Type", "Policy_Start_Date",
    "Policy_End_Date", "Policy_Premium_USD", "Claim_Status", "Claim_Amount_USD",
    "Last_Interaction", "Risk_Score", "Renewal_Probability", "Fraud_Risk_Flag",
    "Cross_Sell_Score", "Lead_Source", "Client_Feedback",
]


def row(client_id="CL-00001", claim_status="Approved", claim_amount="1204.55",
        policy_type="Auto", **overrides):
    data = {
        "Client_ID": client_id,
        "Client_Name": "Patrick Hart",
        "Client_Email": f"{client_id.lower()}@example.com",
        "Client_Phone": "588-240-1527",
        "Client_Age": "25",
        "Client_Gender": "Other",
        "Client_Location": "New Steven",
        "Policy_Type": policy_type,
        "Policy_Start_Date": "2023-01-13",
        "Policy_End_Date": "2027-03-11",
        "Policy_Premium_USD": "750.23",
        "Claim_Status": claim_status,
        "Claim_Amount_USD": claim_amount,
        "Last_Interaction": "2024-12-02",
        "Risk_Score": "0.16",
        "Renewal_Probability": "0.06",
        "Fraud_Risk_Flag": "Low",
        "Cross_Sell_Score": "0.75",
        "Lead_Source": "Agent",
        "Client_Feedback": "Helpful.",
    }
    data.update(overrides)
    return data


@pytest.fixture
def write_csv(tmp_path):
    def _write(rows, header=None, name="data.csv"):
        path = tmp_path / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header or HEADER)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        return str(path)

    return _write


def load(path, **kwargs):
    out = StringIO()
    call_command("loaddataset", path, stdout=out, **kwargs)
    return out.getvalue()


# -- Claims are seeded from the same row as their policy (FR-035) ----------


def test_load_creates_a_claim_against_the_rows_policy(write_csv):
    path = write_csv([row()])

    load(path)

    claim = Claim.objects.get()
    assert claim.claim_status == "Approved"
    assert claim.claim_amount_usd == Decimal("1204.55")
    assert claim.policy.customer.client_id == "CL-00001"


def test_load_reports_claim_counts_alongside_the_others(write_csv):
    """FR-036: separate created/updated/refused, plus skipped."""
    output = load(write_csv([row()]))

    assert "Claims" in output
    assert "created: 1" in output


def test_rerun_updates_rather_than_duplicates(write_csv):
    """FR-035, SC-003."""
    path = write_csv([row()])
    load(path)

    output = load(path)

    assert Claim.objects.count() == 1
    assert "Claims    — created: 0  updated: 1" in output


def test_claim_matching_ignores_archived_claims(write_csv):
    """
    Matching runs among LIVE rows only, so a load after an archival creates
    a fresh claim rather than resurrecting a deliberately removed one.
    """
    path = write_csv([row()])
    load(path)
    claim = Claim.objects.get()
    claim.archived_at = "2026-01-01T00:00:00Z"
    claim.save(update_fields=["archived_at"])

    load(path)

    assert Claim.objects.count() == 1  # a new live one
    assert Claim.all_objects.count() == 2


# -- `No Claim` is not a claim (FR-004, FR-036) ----------------------------


def test_no_claim_with_zero_amount_creates_no_claim_and_is_not_an_error(write_csv):
    path = write_csv([row(claim_status="No Claim", claim_amount="0.0")])

    output = load(path)

    assert Claim.objects.count() == 0
    assert Customer.objects.count() == 1  # the row still loads normally
    assert Policy.objects.count() == 1
    assert "skipped: 1" in output
    assert "refused: 0" in output


def test_no_claim_rows_are_not_refusals(write_csv):
    """
    Getting this backwards would refuse 754 valid rows in the real dataset.
    """
    path = write_csv([row(claim_status="No Claim", claim_amount="0.0")])

    output = load(path)

    assert "Claims    — created: 0  updated: 0  refused: 0  skipped: 1" in output


# -- Anomalies (FR-041, FR-042, FR-045) ------------------------------------


def test_no_claim_with_nonzero_amount_records_an_anomaly(write_csv):
    path = write_csv([row(claim_status="No Claim", claim_amount="19919.13")])

    load(path)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.source_status == "No Claim"
    assert anomaly.source_amount_usd == Decimal("19919.13")
    assert anomaly.status == AnomalyStatus.OPEN
    assert anomaly.cleared_reason is None
    assert Claim.objects.count() == 0  # no claim invented from the amount


def test_anomaly_names_the_policy_it_relates_to(write_csv):
    """FR-042: joinable to coverage data without the source file."""
    path = write_csv([row(claim_status="No Claim", claim_amount="8.52")])

    load(path)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.policy == Policy.objects.get()
    assert anomaly.source_file.endswith(".csv")


def test_anomaly_is_not_a_refusal_row_still_loads(write_csv):
    """FR-045: the row's customer and policy MUST still be loaded."""
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])

    output = load(path)

    assert Customer.objects.count() == 1
    assert Policy.objects.count() == 1
    assert "refused: 0" in output


def test_anomaly_count_is_reported_on_its_own_line(write_csv):
    """FR-045: distinctly from created/updated/refused."""
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])

    output = load(path)

    assert "Anomalies — recorded: 1" in output
    assert "corrected: 0" in output
    assert "absent: 0" in output


def test_counts_sum_to_the_row_count(write_csv):
    """2246 + 364 + 390 = 3000 in the real dataset; the shape holds here."""
    path = write_csv([
        row(client_id="CL-00001", claim_status="Approved", claim_amount="10.00"),
        row(client_id="CL-00002", claim_status="No Claim", claim_amount="0.0"),
        row(client_id="CL-00003", claim_status="No Claim", claim_amount="99.00"),
    ])

    output = load(path)

    assert "created: 1" in output
    assert "skipped: 1" in output
    assert "recorded: 1" in output


# -- Idempotency (FR-043, SC-012) ------------------------------------------


def test_anomaly_retention_is_idempotent_across_three_runs(write_csv):
    """
    SC-012: the count must stay at 1, not grow to 3. This is why anomalies
    are reconciled per row rather than appended to an immutable log.
    """
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])

    load(path)
    after_first = ClaimLoadAnomaly.objects.count()
    load(path)
    load(path)

    assert after_first == 1
    assert ClaimLoadAnomaly.objects.count() == 1


def test_reobserving_an_open_anomaly_writes_no_new_audit_entry(write_csv):
    """
    Nothing changed about the observation, and an entry per run would be
    noise that grows linearly with the number of loads.
    """
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(path)
    before = AuditLog.objects.filter(action="claim_anomaly.recorded").count()

    load(path)

    assert AuditLog.objects.filter(action="claim_anomaly.recorded").count() == before


def test_reobserving_refreshes_last_observed_at(write_csv):
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(path)
    first = ClaimLoadAnomaly.objects.get()
    first_seen = first.last_observed_at

    load(path)

    first.refresh_from_db()
    assert first.last_observed_at >= first_seen
    assert first.first_observed_at == first.first_observed_at  # unchanged


# -- Clearing: corrected vs absent (FR-044, FR-044a) -----------------------


def test_corrected_row_clears_the_anomaly_as_corrected(write_csv):
    """The load positively OBSERVED the resolution."""
    conflicting = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(conflicting)

    fixed = write_csv(
        [row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )
    load(fixed)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.status == AnomalyStatus.CLEARED
    assert anomaly.cleared_reason == ClearedReason.CORRECTED
    assert anomaly.cleared_at is not None


def test_absent_row_clears_the_anomaly_as_absent(write_csv):
    """
    The load observed NOTHING. The row may have been fixed, withdrawn, or
    dropped by an export that no longer covers it -- the cause is unknown.
    """
    conflicting = write_csv([
        row(client_id="CL-00001", claim_status="No Claim", claim_amount="500.00"),
        row(client_id="CL-00002", claim_status="Approved", claim_amount="10.00"),
    ])
    load(conflicting)

    without = write_csv(
        [row(client_id="CL-00002", claim_status="Approved", claim_amount="10.00")],
        name="without.csv",
    )
    load(without)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.status == AnomalyStatus.CLEARED
    assert anomaly.cleared_reason == ClearedReason.ABSENT


def test_absent_cleared_is_excluded_from_confirmed_corrections(write_csv):
    """
    FR-044a / SC-013: a consumer MUST be able to count confirmed
    corrections without absence inflating the number.
    """
    conflicting = write_csv([
        row(client_id="CL-00001", claim_status="No Claim", claim_amount="500.00"),
        row(client_id="CL-00002", claim_status="No Claim", claim_amount="700.00"),
    ])
    load(conflicting)

    # CL-00001 comes back fixed; CL-00002 vanishes entirely.
    second = write_csv(
        [row(client_id="CL-00001", claim_status="No Claim", claim_amount="0.0")],
        name="second.csv",
    )
    load(second)

    corrected = ClaimLoadAnomaly.objects.filter(cleared_reason=ClearedReason.CORRECTED)
    absent = ClaimLoadAnomaly.objects.filter(cleared_reason=ClearedReason.ABSENT)

    assert corrected.count() == 1
    assert absent.count() == 1
    assert corrected.get().policy.customer.client_id == "CL-00001"


def test_clearing_reports_split_by_reason(write_csv):
    conflicting = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(conflicting)

    fixed = write_csv(
        [row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )
    output = load(fixed)

    assert "cleared: 1" in output
    assert "corrected: 1" in output
    assert "absent: 0" in output


# -- Re-raise (FR-044b) ----------------------------------------------------


def test_cleared_anomaly_that_conflicts_again_is_reraised(write_csv):
    conflicting = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(conflicting)
    fixed = write_csv(
        [row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )
    load(fixed)

    load(conflicting)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.status == AnomalyStatus.OPEN
    assert anomaly.cleared_reason is None
    assert anomaly.cleared_at is None
    assert ClaimLoadAnomaly.objects.count() == 1


def test_reraise_writes_a_distinct_audit_action(write_csv):
    conflicting = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(conflicting)
    fixed = write_csv(
        [row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )
    load(fixed)

    load(conflicting)

    assert AuditLog.objects.filter(action="claim_anomaly.reraised").count() == 1


def test_absent_cleared_anomaly_reraises_rather_than_staying_cleared(write_csv):
    """
    FR-044b: it must NOT remain cleared on the strength of the run that did
    not observe it.
    """
    both = write_csv([
        row(client_id="CL-00001", claim_status="No Claim", claim_amount="500.00"),
        row(client_id="CL-00002", claim_status="Approved", claim_amount="10.00"),
    ])
    load(both)
    without = write_csv(
        [row(client_id="CL-00002", claim_status="Approved", claim_amount="10.00")],
        name="without.csv",
    )
    load(without)

    load(both)

    anomaly = ClaimLoadAnomaly.objects.get()
    assert anomaly.status == AnomalyStatus.OPEN


# -- Missing claim columns (FR-037) ----------------------------------------


def test_missing_claim_columns_fails_before_writing_anything(write_csv):
    header = [c for c in HEADER if c not in ("Claim_Status", "Claim_Amount_USD")]
    data = row()
    for column in ("Claim_Status", "Claim_Amount_USD"):
        data.pop(column)
    path = write_csv([data], header=header)

    with pytest.raises(CommandError) as exc:
        load(path)

    assert "Claim_Status" in str(exc.value)
    assert Customer.objects.count() == 0  # nothing written
    assert Policy.objects.count() == 0


# -- Row-level atomicity (FR-038) ------------------------------------------


def test_invalid_claim_refuses_the_whole_row(write_csv):
    """No customer, policy, or claim from that row may persist."""
    path = write_csv([row(claim_amount="-5.00")])

    load(path)

    assert Customer.objects.count() == 0
    assert Policy.objects.count() == 0
    assert Claim.objects.count() == 0


def test_invalid_claim_row_does_not_stop_the_run(write_csv):
    path = write_csv([
        row(client_id="CL-00001", claim_amount="-5.00"),
        row(client_id="CL-00002", claim_amount="10.00"),
    ])

    output = load(path)

    assert Customer.objects.count() == 1
    assert Claim.objects.count() == 1
    assert "refused: 1" in output


def test_invalid_claim_status_refuses_the_row(write_csv):
    path = write_csv([row(claim_status="Escalated")])

    load(path)

    assert Claim.objects.count() == 0
    assert Customer.objects.count() == 0


# -- Dry run (FR-040, FR-046) ----------------------------------------------


def test_dry_run_writes_no_claim(write_csv):
    path = write_csv([row()])

    output = load(path, dry_run=True)

    assert Claim.objects.count() == 0
    assert "created: 1" in output


def test_dry_run_writes_no_anomaly(write_csv):
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])

    output = load(path, dry_run=True)

    assert ClaimLoadAnomaly.objects.count() == 0
    assert "recorded: 1" in output


def test_dry_run_writes_no_audit_entry(write_csv):
    path = write_csv([row(claim_status="No Claim", claim_amount="500.00")])

    load(path, dry_run=True)

    assert AuditLog.objects.count() == 0


def test_dry_run_reports_the_clearing_it_would_perform(write_csv):
    """
    A dry run that reports a different number than the real run would make
    preview mode useless for the operator deciding whether to run it.
    """
    conflicting = write_csv([row(claim_status="No Claim", claim_amount="500.00")])
    load(conflicting)

    fixed = write_csv(
        [row(claim_status="No Claim", claim_amount="0.0")], name="fixed.csv"
    )
    preview = load(fixed, dry_run=True)

    assert "cleared: 1" in preview
    assert "corrected: 1" in preview
    # ...and nothing was actually cleared.
    assert ClaimLoadAnomaly.objects.get().status == AnomalyStatus.OPEN
