"""
Load customers from the source dataset CSV (FR-034 through FR-042).

Two decisions worth stating plainly:

1. Rows are matched through `Customer.all_objects`, not `objects`. Archival
   reserves a reference (FR-021), so an archived row must reconcile in
   place. Matching through the default manager would hide that row, the
   loader would treat its reference as free, and the insert would die on
   the unique constraint for a record it cannot see.

2. Each row gets its own transaction, not the file. FR-039 requires
   separate created/updated/refused counts, which is only meaningful if
   valid rows persist while invalid ones are refused. A file-wide
   transaction would make one bad row discard every good one.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import record_action

from ...models import Customer
from ...serializers import CustomerSerializer

# CSV column -> Customer field. Columns absent from this map are ignored
# (FR-037), so the same file later serves the Policy and Claims loaders.
COLUMN_MAP = {
    "Client_ID": "client_id",
    "Client_Name": "name",
    "Client_Email": "email",
    "Client_Phone": "phone",
    "Client_Age": "age",
    "Client_Gender": "gender",
    "Client_Location": "location",
    "Lead_Source": "lead_source",
    "Risk_Score": "risk_score",
    "Fraud_Risk_Flag": "fraud_risk_flag",
    "Cross_Sell_Score": "cross_sell_score",
}

REQUIRED_COLUMNS = set(COLUMN_MAP)


class Command(BaseCommand):
    help = "Load customers from the source dataset CSV. Idempotent on client_id."

    def add_arguments(self, parser):
        # Positional and required: FR-034 forbids a default that assumes a
        # committed file.
        parser.add_argument("csv_path", help="Path to the source CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report counts without writing anything",
        )

    def handle(self, *args, **options):
        path = Path(options["csv_path"])
        dry_run = options["dry_run"]

        rows = self._read_rows(path)

        created = updated = refused = 0
        for index, raw in enumerate(rows, start=1):
            outcome = self._process_row(raw, index, str(path), dry_run)
            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            else:
                refused += 1

        self.stdout.write(f"Created: {created}  Updated: {updated}  Refused: {refused}")

    # -- reading -----------------------------------------------------------

    def _read_rows(self, path):
        """
        Validate the file's existence and structure before any write, so a
        structurally wrong file cannot leave a partial load (FR-040).
        """
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        if path.is_dir():
            raise CommandError(f"Not a file: {path}")

        try:
            handle = path.open(newline="", encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"Cannot read file: {path} ({exc})")

        with handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise CommandError(f"File has no header row: {path}")

            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise CommandError(f"Missing required columns: {', '.join(sorted(missing))}")

            return list(reader)

    # -- per-row processing ------------------------------------------------

    def _process_row(self, raw, index, source_path, dry_run):
        data = {field: raw.get(column) for column, field in COLUMN_MAP.items()}

        client_id = data.get("client_id")
        existing = (
            Customer.all_objects.filter(client_id=client_id).first() if client_id else None
        )

        # partial=False on create, but an update must not require every
        # field; the source always supplies all of them, so the shapes match.
        serializer = CustomerSerializer(instance=existing, data=data)
        if not serializer.is_valid():
            self._report_refusal(index, serializer.errors)
            return "refused"

        if dry_run:
            return "updated" if existing else "created"

        # One transaction per row, with the audit write inside it (FR-031).
        with transaction.atomic():
            customer = serializer.save()
            action = "customer.updated" if existing else "customer.created"
            record_action(
                actor=None,  # system load, not a person (FR-042)
                action=action,
                target_type="customers.Customer",
                target_id=customer.id,
                outcome="succeeded",
                before=None,
                after=_snapshot(customer),
                context={"source": "loadcustomers", "file": source_path},
            )

        return "updated" if existing else "created"

    def _report_refusal(self, index, errors):
        for field, messages in errors.items():
            detail = messages[0] if isinstance(messages, list) else messages
            self.stdout.write(f"Row {index}: {field} — {detail}")


def _snapshot(customer):
    return {
        "client_id": customer.client_id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "age": customer.age,
        "gender": customer.gender,
        "location": customer.location,
        "lead_source": customer.lead_source,
        "risk_score": str(customer.risk_score) if customer.risk_score is not None else None,
        "fraud_risk_flag": customer.fraud_risk_flag,
        "cross_sell_score": (
            str(customer.cross_sell_score) if customer.cross_sell_score is not None else None
        ),
    }
