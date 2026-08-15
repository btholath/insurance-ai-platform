"""
Dataset loader tests -- the policy half (T030 - T038).

The customer half is covered by test_loadcustomers.py, which now exercises
the same command through its backward-compatible alias.

Three tests here are deliberately the subtle ones:

- test_two_policy_types_for_one_customer_reconcile_separately (T032) is
  the only thing that catches the loader matching on customer alone. That
  failure is silent: one policy overwrites the other on every re-run, and
  only for customers this particular export cannot produce.
- test_archived_customer_reconciles_its_policy_in_place (T033) catches
  the customer lookup going through `objects` instead of `all_objects`.
- test_refused_policy_leaves_no_customer_behind (T034) catches the row
  transaction not spanning both records -- the half-landed row an operator
  cannot reason about.
"""
import csv
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.claims.models import Claim, ClaimLoadAnomaly
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


def row(client_id="CL-00001", name="Patrick Hart", email="patrick@example.com",
        policy_type="Auto", start="2023-01-13", end="2027-03-11",
        premium="750.23", renewal="0.06"):
    return {
        "Client_ID": client_id, "Client_Name": name, "Client_Email": email,
        "Client_Phone": "588-240-1527", "Client_Age": "25",
        "Client_Gender": "Other", "Client_Location": "New Steven",
        "Policy_Type": policy_type, "Policy_Start_Date": start,
        "Policy_End_Date": end, "Policy_Premium_USD": premium,
        "Claim_Status": "Approved", "Claim_Amount_USD": "0.0",
        "Last_Interaction": "2024-12-02", "Risk_Score": "0.16",
        "Renewal_Probability": renewal, "Fraud_Risk_Flag": "Low",
        "Cross_Sell_Score": "0.75", "Lead_Source": "Agent",
        "Client_Feedback": "Very helpful.",
    }


def write_csv(tmp_path, rows, header=HEADER, name="data.csv"):
    path = tmp_path / name
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in header})
    return str(path)


# ---------------------------------------------------------------------------
# T030: happy path (FR-037)
# ---------------------------------------------------------------------------


def test_creates_one_policy_per_row(tmp_path):
    path = write_csv(tmp_path, [row(client_id="CL-00001"),
                                row(client_id="CL-00002", email="b@example.com")])

    call_command("loaddataset", path)

    assert Customer.objects.count() == 2
    assert Policy.objects.count() == 2


def test_policy_fields_map_from_the_contract_columns(tmp_path):
    path = write_csv(tmp_path, [row(
        policy_type="Health", start="2024-02-01", end="2028-02-01",
        premium="1234.56", renewal="0.42",
    )])

    call_command("loaddataset", path)

    policy = Policy.objects.get()
    assert policy.policy_type == "Health"
    assert policy.start_date.isoformat() == "2024-02-01"
    assert policy.end_date.isoformat() == "2028-02-01"
    assert policy.premium_usd == Decimal("1234.56")
    assert policy.renewal_probability == Decimal("0.42")


def test_each_policy_attaches_to_the_customer_named_on_its_row(tmp_path):
    """FR-037."""
    path = write_csv(tmp_path, [
        row(client_id="CL-00001", policy_type="Auto"),
        row(client_id="CL-00002", email="b@example.com", policy_type="Life"),
    ])

    call_command("loaddataset", path)

    assert Policy.objects.get(policy_type="Auto").customer.client_id == "CL-00001"
    assert Policy.objects.get(policy_type="Life").customer.client_id == "CL-00002"


def test_zero_renewal_probability_loads_as_zero_not_null(tmp_path):
    """
    FR-004. 13 rows in the real dataset carry a genuine 0.0; a truthiness
    check anywhere in the path would reclassify all 13 as "not recorded".
    """
    path = write_csv(tmp_path, [row(renewal="0.0")])

    call_command("loaddataset", path)

    policy = Policy.objects.get()
    assert policy.renewal_probability == Decimal("0.00")
    assert policy.renewal_probability is not None


# ---------------------------------------------------------------------------
# T031: idempotency (FR-038, FR-040, SC-002)
# ---------------------------------------------------------------------------


def test_rerun_leaves_the_policy_count_identical(tmp_path, capsys):
    path = write_csv(tmp_path, [row(client_id="CL-00001"),
                                row(client_id="CL-00002", email="b@example.com")])
    call_command("loaddataset", path)
    capsys.readouterr()

    call_command("loaddataset", path)

    out = capsys.readouterr().out
    assert Policy.objects.count() == 2
    assert "Policies  — created: 0  updated: 2  refused: 0" in out


def test_rerun_creates_no_duplicate_type_pairs(tmp_path):
    """SC-002."""
    path = write_csv(tmp_path, [row()])
    call_command("loaddataset", path)
    call_command("loaddataset", path)

    customer = Customer.objects.get(client_id="CL-00001")
    assert Policy.objects.filter(customer=customer, policy_type="Auto").count() == 1


def test_changed_source_row_updates_the_policy_in_place(tmp_path):
    """FR-040."""
    path = write_csv(tmp_path, [row(premium="750.23")])
    call_command("loaddataset", path)
    original_id = Policy.objects.get().id

    changed = write_csv(tmp_path, [row(premium="999.99")], name="changed.csv")
    call_command("loaddataset", changed)

    policy = Policy.objects.get()
    assert policy.id == original_id
    assert policy.premium_usd == Decimal("999.99")


# ---------------------------------------------------------------------------
# T032: the match key (FR-039) -- the silent-overwrite guard
# ---------------------------------------------------------------------------


def test_two_policy_types_for_one_customer_reconcile_separately(tmp_path):
    """
    FR-039. Matching on customer alone would overwrite one policy with the
    other on every run, silently. The real export happens to carry one
    policy per customer, so nothing else in this suite would catch it.
    """
    path = write_csv(tmp_path, [
        row(client_id="CL-00001", policy_type="Auto", premium="100.00"),
        row(client_id="CL-00001", policy_type="Health", premium="200.00"),
    ])

    call_command("loaddataset", path)

    customer = Customer.objects.get(client_id="CL-00001")
    assert Policy.objects.filter(customer=customer).count() == 2

    call_command("loaddataset", path)

    assert Policy.objects.filter(customer=customer).count() == 2
    assert Policy.objects.get(customer=customer, policy_type="Auto").premium_usd == Decimal("100.00")
    assert Policy.objects.get(customer=customer, policy_type="Health").premium_usd == Decimal("200.00")


# ---------------------------------------------------------------------------
# T033: archived-customer reconciliation (FR-041)
# ---------------------------------------------------------------------------


def test_archived_customer_reconciles_its_policy_in_place(tmp_path):
    """
    FR-041. The archived customer must be found through all_objects and
    reused -- not duplicated, and not left with an unattached policy.
    """
    path = write_csv(tmp_path, [row()])
    call_command("loaddataset", path)

    customer = Customer.objects.get(client_id="CL-00001")
    customer.archived_at = timezone.now()
    customer.save(update_fields=["archived_at"])

    call_command("loaddataset", path)

    assert Customer.all_objects.filter(client_id="CL-00001").count() == 1
    assert Policy.objects.count() == 1
    assert Policy.objects.get().customer_id == customer.id


# ---------------------------------------------------------------------------
# T034: row atomicity (FR-045) -- both records or neither
# ---------------------------------------------------------------------------


def test_refused_policy_leaves_no_customer_behind(tmp_path, capsys):
    """
    FR-045. A half-landed row is the state an operator cannot reason
    about: re-running would create the policy while reporting the customer
    as "updated", making the counts lie.
    """
    path = write_csv(tmp_path, [row(client_id="CL-00009", policy_type="Motor")])

    call_command("loaddataset", path)

    assert not Customer.all_objects.filter(client_id="CL-00009").exists()
    assert Policy.all_objects.count() == 0

    out = capsys.readouterr().out
    assert "Row 1" in out
    assert "policy_type" in out
    assert "Customers — created: 0  updated: 0  refused: 1" in out
    assert "Policies  — created: 0  updated: 0  refused: 1" in out


def test_incoherent_dates_refuse_the_whole_row(tmp_path, capsys):
    path = write_csv(tmp_path, [row(start="2027-01-01", end="2023-01-01")])

    call_command("loaddataset", path)

    assert Customer.all_objects.count() == 0
    assert Policy.all_objects.count() == 0
    assert "end_date" in capsys.readouterr().out


def test_negative_premium_refuses_the_whole_row(tmp_path, capsys):
    path = write_csv(tmp_path, [row(premium="-1.00")])

    call_command("loaddataset", path)

    assert Customer.all_objects.count() == 0
    assert Policy.all_objects.count() == 0
    assert "premium_usd" in capsys.readouterr().out


def test_valid_rows_persist_alongside_a_refused_row(tmp_path):
    """Row-level atomicity, not file-level: one bad row must not sink the load."""
    path = write_csv(tmp_path, [
        row(client_id="CL-00001"),
        row(client_id="CL-00002", email="b@example.com", premium="0.00"),
        row(client_id="CL-00003", email="c@example.com"),
    ])

    call_command("loaddataset", path)

    assert Customer.objects.count() == 2
    assert Policy.objects.count() == 2
    assert not Customer.all_objects.filter(client_id="CL-00002").exists()


# ---------------------------------------------------------------------------
# T035: archived policies are not resurrected
# ---------------------------------------------------------------------------


def test_load_after_archival_creates_a_fresh_policy(tmp_path):
    """
    Silently undoing a deliberate removal would be worse than creating a
    new record, so matching filters to live rows only.
    """
    path = write_csv(tmp_path, [row()])
    call_command("loaddataset", path)

    archived = Policy.objects.get()
    archived.archived_at = timezone.now()
    archived.save(update_fields=["archived_at"])

    call_command("loaddataset", path)

    assert Policy.all_objects.count() == 2
    assert Policy.objects.count() == 1

    fresh = Policy.objects.get()
    assert fresh.id != archived.id

    archived.refresh_from_db()
    assert archived.archived_at is not None


# ---------------------------------------------------------------------------
# T036: failure modes (FR-046)
# ---------------------------------------------------------------------------


def test_missing_policy_columns_fails_before_writing_any_customer(tmp_path):
    """
    A behaviour change from Phase 2a, where such a file loaded customers
    successfully. The required-column check now covers both sets and runs
    before the row loop.
    """
    header = [c for c in HEADER if c != "Policy_Type"]
    path = write_csv(tmp_path, [row()], header=header)

    with pytest.raises(CommandError, match="Missing required columns"):
        call_command("loaddataset", path)

    assert Customer.all_objects.count() == 0
    assert Policy.all_objects.count() == 0


def test_missing_policy_column_is_named_in_the_error(tmp_path):
    header = [c for c in HEADER if c not in ("Policy_Premium_USD", "Client_Age")]
    path = write_csv(tmp_path, [row()], header=header)

    with pytest.raises(CommandError) as exc:
        call_command("loaddataset", path)

    assert "Client_Age" in str(exc.value)
    assert "Policy_Premium_USD" in str(exc.value)


def test_missing_file_creates_nothing(tmp_path):
    with pytest.raises(CommandError, match="File not found"):
        call_command("loaddataset", str(tmp_path / "nope.csv"))

    assert Policy.all_objects.count() == 0


def test_headerless_file_creates_nothing(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")

    with pytest.raises(CommandError, match="no header row"):
        call_command("loaddataset", str(path))

    assert Policy.all_objects.count() == 0


def test_directory_path_creates_nothing(tmp_path):
    with pytest.raises(CommandError, match="Not a file"):
        call_command("loaddataset", str(tmp_path))

    assert Policy.all_objects.count() == 0


# ---------------------------------------------------------------------------
# T037: loader audit (FR-048)
# ---------------------------------------------------------------------------


def test_each_created_policy_writes_an_audit_entry(tmp_path):
    path = write_csv(tmp_path, [row()])

    call_command("loaddataset", path)

    entry = AuditLog.objects.get(target_type="policies.Policy")
    assert entry.action == "policy.created"
    assert entry.actor is None
    assert entry.outcome == "succeeded"
    assert entry.context["source"] == "loaddataset"
    assert entry.context["file"] == path


def test_policy_audit_after_carries_the_loaded_values(tmp_path):
    path = write_csv(tmp_path, [row(policy_type="Life", premium="321.00")])

    call_command("loaddataset", path)

    entry = AuditLog.objects.get(target_type="policies.Policy")
    assert entry.after["policy_type"] == "Life"
    assert entry.after["premium_usd"] == "321.00"


def test_rerun_writes_updated_policy_entries(tmp_path):
    path = write_csv(tmp_path, [row()])
    call_command("loaddataset", path)
    call_command("loaddataset", path)

    actions = list(
        AuditLog.objects.filter(target_type="policies.Policy")
        .order_by("id")
        .values_list("action", flat=True)
    )
    assert actions == ["policy.created", "policy.updated"]


def test_refused_row_writes_no_audit_entry_for_either_record(tmp_path):
    """The row rolled back, so its audit writes must roll back with it."""
    path = write_csv(tmp_path, [row(policy_type="Motor")])

    call_command("loaddataset", path)

    assert AuditLog.objects.filter(target_type="policies.Policy").count() == 0
    assert AuditLog.objects.filter(target_type="customers.Customer").count() == 0


# ---------------------------------------------------------------------------
# T038: the loadcustomers alias
# ---------------------------------------------------------------------------


def test_loadcustomers_alias_still_runs_and_loads_policies(tmp_path):
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path)

    assert Customer.objects.count() == 1
    assert Policy.objects.count() == 1


def test_alias_produces_identical_output_to_loaddataset(tmp_path, capsys):
    path = write_csv(tmp_path, [row()])

    call_command("loaddataset", path)
    via_loaddataset = capsys.readouterr().out

    # Claims and anomalies must go first: both hold a PROTECT reference to
    # Policy (FR-009 in spec 004), so deleting policies out from under them
    # raises ProtectedError. That protection is the point -- no claim may
    # be left referring to a policy that no longer exists -- so the reset
    # follows the dependency order rather than working around it.
    ClaimLoadAnomaly.objects.all().delete()
    Claim.all_objects.all().delete()
    Policy.all_objects.all().delete()
    Customer.all_objects.all().delete()

    call_command("loadcustomers", path)
    via_alias = capsys.readouterr().out

    assert via_alias == via_loaddataset


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_writes_no_policy(tmp_path, capsys):
    path = write_csv(tmp_path, [row()])

    call_command("loaddataset", path, "--dry-run")

    assert Policy.all_objects.count() == 0
    assert "Policies  — created: 1  updated: 0  refused: 0" in capsys.readouterr().out
