"""
CSV loader tests (T017 - T022).

The single most important test here is
test_archived_record_reconciles_rather_than_duplicating (T019): it is the
only thing that catches the loader looking rows up through `objects`
instead of `all_objects`. That failure is invisible in ordinary use -- the
loader simply cannot see an archived row, concludes the reference is free,
attempts an insert, and dies on the unique constraint for a record it
cannot query.
"""
import csv
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.customers.factories import CustomerFactory
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db

# Mirrors the real dataset's 20 columns. The nine policy/claim columns are
# present precisely so the "extra columns ignored" requirement (FR-037) is
# exercised against a realistic header rather than a trimmed one.
HEADER = [
    "Client_ID", "Client_Name", "Client_Email", "Client_Phone", "Client_Age",
    "Client_Gender", "Client_Location", "Policy_Type", "Policy_Start_Date",
    "Policy_End_Date", "Policy_Premium_USD", "Claim_Status", "Claim_Amount_USD",
    "Last_Interaction", "Risk_Score", "Renewal_Probability", "Fraud_Risk_Flag",
    "Cross_Sell_Score", "Lead_Source", "Client_Feedback",
]


def row(client_id="CL-00001", name="Patrick Hart", email="patrick@example.com",
        phone="588-240-1527", age="25", gender="Other", location="New Steven",
        risk="0.16", fraud="Low", cross="0.75", lead="Agent"):
    return {
        "Client_ID": client_id, "Client_Name": name, "Client_Email": email,
        "Client_Phone": phone, "Client_Age": age, "Client_Gender": gender,
        "Client_Location": location, "Policy_Type": "Auto",
        "Policy_Start_Date": "2023-01-13", "Policy_End_Date": "2027-03-11",
        "Policy_Premium_USD": "750.23", "Claim_Status": "Approved",
        "Claim_Amount_USD": "0.0", "Last_Interaction": "2024-12-02",
        "Risk_Score": risk, "Renewal_Probability": "0.06",
        "Fraud_Risk_Flag": fraud, "Cross_Sell_Score": cross,
        "Lead_Source": lead, "Client_Feedback": "Very helpful.",
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
# T017: happy path and field mapping
# ---------------------------------------------------------------------------


def test_loads_one_customer_per_row(tmp_path):
    path = write_csv(tmp_path, [row(client_id="CL-00001"), row(client_id="CL-00002", email="b@example.com")])

    call_command("loadcustomers", path)

    assert Customer.objects.count() == 2


def test_maps_every_used_column(tmp_path):
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path)

    customer = Customer.objects.get(client_id="CL-00001")
    assert customer.name == "Patrick Hart"
    assert customer.email == "patrick@example.com"
    assert customer.phone == "588-240-1527"
    assert customer.age == 25
    assert customer.gender == "Other"
    assert customer.location == "New Steven"
    assert customer.lead_source == "Agent"
    assert customer.risk_score == Decimal("0.16")
    assert customer.fraud_risk_flag == "Low"
    assert customer.cross_sell_score == Decimal("0.75")


def test_reports_created_count(tmp_path, capsys):
    """FR-039."""
    path = write_csv(tmp_path, [row(client_id="CL-00001"), row(client_id="CL-00002", email="b@example.com")])

    call_command("loadcustomers", path)

    out = capsys.readouterr().out
    assert "Created: 2" in out
    assert "Updated: 0" in out
    assert "Refused: 0" in out


def test_zero_cross_sell_score_loads_as_zero_not_null(tmp_path):
    """
    FR-006. The real dataset's Cross_Sell_Score minimum is exactly 0.0, so
    this is a real row shape, not a synthetic edge case.
    """
    path = write_csv(tmp_path, [row(cross="0.0")])

    call_command("loadcustomers", path)

    customer = Customer.objects.get(client_id="CL-00001")
    assert customer.cross_sell_score == Decimal("0.00")
    assert customer.cross_sell_score is not None


# ---------------------------------------------------------------------------
# T018: idempotency (FR-035, FR-036, SC-002)
# ---------------------------------------------------------------------------


def test_rerun_on_unchanged_input_creates_nothing(tmp_path, capsys):
    path = write_csv(tmp_path, [row(client_id="CL-00001"), row(client_id="CL-00002", email="b@example.com")])
    call_command("loadcustomers", path)
    capsys.readouterr()

    call_command("loadcustomers", path)

    out = capsys.readouterr().out
    assert Customer.objects.count() == 2
    assert "Created: 0" in out
    assert "Updated: 2" in out


def test_rerun_leaves_no_duplicate_references(tmp_path):
    """SC-002."""
    path = write_csv(tmp_path, [row(client_id="CL-00001")])
    call_command("loadcustomers", path)
    call_command("loadcustomers", path)

    assert Customer.all_objects.filter(client_id="CL-00001").count() == 1


def test_changed_source_row_updates_in_place(tmp_path):
    """FR-036."""
    path = write_csv(tmp_path, [row(client_id="CL-00001", phone="111-1111")])
    call_command("loadcustomers", path)
    original_pk = Customer.objects.get(client_id="CL-00001").pk

    updated_path = write_csv(tmp_path, [row(client_id="CL-00001", phone="999-9999")], name="updated.csv")
    call_command("loadcustomers", updated_path)

    customer = Customer.objects.get(client_id="CL-00001")
    assert customer.pk == original_pk
    assert customer.phone == "999-9999"
    assert Customer.objects.count() == 1


# ---------------------------------------------------------------------------
# T019: archived reconciliation -- the load-bearing test (FR-021, SC-011)
# ---------------------------------------------------------------------------


def test_archived_record_reconciles_rather_than_duplicating(tmp_path):
    """
    FR-021. Archive a loaded customer, then re-run the load.

    If the loader matches through `objects`, it cannot see the archived row,
    treats CL-00001 as unused, attempts an INSERT, and raises IntegrityError
    on the unique constraint. This test is the only place that failure
    surfaces.
    """
    path = write_csv(tmp_path, [row(client_id="CL-00001")])
    call_command("loadcustomers", path)

    customer = Customer.objects.get(client_id="CL-00001")
    customer.archived_at = timezone.now()
    customer.save()

    call_command("loadcustomers", path)

    assert Customer.all_objects.filter(client_id="CL-00001").count() == 1
    assert Customer.all_objects.count() == 1


def test_archived_record_reference_stays_reserved(tmp_path):
    path = write_csv(tmp_path, [row(client_id="CL-00001")])
    call_command("loadcustomers", path)
    Customer.objects.filter(client_id="CL-00001").update(archived_at=timezone.now())

    call_command("loadcustomers", path)

    assert Customer.all_objects.filter(client_id="CL-00001").count() == 1


# ---------------------------------------------------------------------------
# T020: failure modes (FR-040)
# ---------------------------------------------------------------------------


def test_missing_file_fails_clearly_and_creates_nothing(tmp_path):
    with pytest.raises(CommandError, match="File not found"):
        call_command("loadcustomers", str(tmp_path / "nope.csv"))

    assert Customer.all_objects.count() == 0


def test_missing_required_columns_fails_before_writing(tmp_path):
    """FR-040: the column check runs before the row loop."""
    trimmed = ["Client_ID", "Client_Name"]
    path = write_csv(tmp_path, [{"Client_ID": "CL-00001", "Client_Name": "X"}], header=trimmed)

    with pytest.raises(CommandError, match="Missing required columns"):
        call_command("loadcustomers", path)

    assert Customer.all_objects.count() == 0


def test_empty_file_fails_clearly(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")

    with pytest.raises(CommandError, match="no header"):
        call_command("loadcustomers", str(path))

    assert Customer.all_objects.count() == 0


def test_directory_path_fails_clearly(tmp_path):
    with pytest.raises(CommandError):
        call_command("loadcustomers", str(tmp_path))

    assert Customer.all_objects.count() == 0


def test_unreadable_file_fails_clearly(tmp_path):
    """FR-040: an OSError on open must be a clear CommandError, not a crash."""
    path = write_csv(tmp_path, [row()])

    with mock.patch("pathlib.Path.open", side_effect=OSError("permission denied")):
        with pytest.raises(CommandError, match="Cannot read file"):
            call_command("loadcustomers", path)

    assert Customer.all_objects.count() == 0


def test_blank_client_id_row_is_refused_naming_the_field(tmp_path, capsys):
    """
    A source row with an empty Client_ID is refused, not silently assigned
    a generated reference.

    FR-005's generation covers a reference not being *supplied* -- the API
    create path. In the dataset, Client_ID is the record's defining
    external key and is populated on all 3,000 rows, so a blank cell means
    a corrupt export. Generating a reference there would mask the
    corruption and produce a record that reconciles against nothing on the
    next load. Refusing it with the field named is the FR-038/FR-014
    behaviour.
    """
    path = write_csv(tmp_path, [row(client_id="")])

    call_command("loadcustomers", path)

    out = capsys.readouterr().out
    assert Customer.all_objects.count() == 0
    assert "Row 1" in out
    assert "client_id" in out
    assert "Refused: 1" in out


# ---------------------------------------------------------------------------
# T021: row validation and per-row atomicity (FR-037, FR-038, FR-039)
# ---------------------------------------------------------------------------


def test_invalid_row_refused_with_row_number_and_field(tmp_path, capsys):
    """FR-038."""
    path = write_csv(tmp_path, [row(client_id="CL-00001"), row(client_id="CL-00002", age="7", email="b@example.com")])

    call_command("loadcustomers", path)

    out = capsys.readouterr().out
    assert "Row 2" in out
    assert "age" in out


def test_valid_rows_persist_alongside_refused_rows(tmp_path, capsys):
    """
    Per-row atomicity: FR-039's separate created and refused counts are only
    meaningful if valid rows survive a neighbouring bad row.
    """
    path = write_csv(tmp_path, [
        row(client_id="CL-00001"),
        row(client_id="CL-00002", gender="Unknown", email="b@example.com"),
        row(client_id="CL-00003", email="c@example.com"),
    ])

    call_command("loadcustomers", path)

    out = capsys.readouterr().out
    assert Customer.objects.count() == 2
    assert not Customer.all_objects.filter(client_id="CL-00002").exists()
    assert "Created: 2" in out
    assert "Refused: 1" in out


def test_extra_columns_ignored(tmp_path):
    """FR-037: the same file later serves Policy and Claims loaders."""
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path)

    assert Customer.objects.filter(client_id="CL-00001").exists()


def test_dry_run_writes_nothing(tmp_path, capsys):
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path, "--dry-run")

    assert Customer.all_objects.count() == 0
    assert "Created: 1" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# T022: audit attribution (FR-042)
# ---------------------------------------------------------------------------


def test_load_writes_audit_entry_per_created_row(tmp_path):
    """FR-027 / FR-042."""
    path = write_csv(tmp_path, [row(client_id="CL-00001"), row(client_id="CL-00002", email="b@example.com")])

    call_command("loadcustomers", path)

    entries = AuditLog.objects.filter(target_type="customers.Customer", action="customer.created")
    assert entries.count() == 2


def test_load_audit_entries_have_no_human_actor(tmp_path):
    """
    FR-042: attributing 3,000 imported records to a person who did not
    enter them would corrupt the compliance record.
    """
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path)

    entry = AuditLog.objects.get(target_type="customers.Customer")
    assert entry.actor is None
    assert entry.context["source"] == "loadcustomers"


def test_load_audit_context_records_file(tmp_path):
    path = write_csv(tmp_path, [row()])

    call_command("loadcustomers", path)

    entry = AuditLog.objects.get(target_type="customers.Customer")
    assert entry.context["file"] == path


def test_rerun_writes_updated_audit_entries(tmp_path):
    path = write_csv(tmp_path, [row()])
    call_command("loadcustomers", path)

    call_command("loadcustomers", path)

    assert AuditLog.objects.filter(action="customer.updated").count() == 1
