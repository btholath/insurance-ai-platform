"""
Load customers AND their policies from the source dataset CSV
(FR-036 through FR-048).

Renamed from `loadcustomers`, which became misleading once the command
also loads policies. The old name survives as a thin alias so the Phase 2a
quickstart, README, and operator habits keep working.

Four decisions worth stating plainly:

1. Rows are matched through `Customer.all_objects`, not `objects`. Archival
   reserves a reference (FR-021), so an archived row must reconcile in
   place. Matching through the default manager would hide that row, the
   loader would treat its reference as free, and the insert would die on
   the unique constraint for a record it cannot see.

2. Policies match on `(customer, policy_type)` among LIVE rows only
   (FR-039). Matching on the customer alone would be wrong: a customer
   holding auto and home cover would have one policy repeatedly overwritten
   by the other on every re-run -- silently, and only for customers this
   export cannot produce. Restricting to live rows also means a load after
   an archival creates a fresh policy rather than resurrecting a
   deliberately removed one.

3. Each row gets ONE transaction spanning both records, and the policy is
   validated BEFORE either is written (FR-045). A half-landed row
   (customer present, policy missing) is precisely the state an operator
   cannot reason about, and re-running would then create the policy while
   reporting the customer as "updated" -- making the counts lie.

4. Each row gets its own transaction, not the file. FR-044 requires
   separate created/updated/refused counts, which is only meaningful if
   valid rows persist while invalid ones are refused. A file-wide
   transaction would make one bad row discard every good one.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.services import record_action
from apps.policies.models import Policy
from apps.policies.serializers import PolicySerializer

from ...models import Customer
from ...serializers import CustomerSerializer

# CSV column -> Customer field. Columns absent from these maps are ignored
# (FR-042), so the same file later serves the Claims loader.
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

# CSV column -> Policy field. The customer FK is resolved per row rather
# than mapped, since it comes from Client_ID (FR-037).
POLICY_COLUMN_MAP = {
    "Policy_Type": "policy_type",
    "Policy_Start_Date": "start_date",
    "Policy_End_Date": "end_date",
    "Policy_Premium_USD": "premium_usd",
    "Renewal_Probability": "renewal_probability",
}

# Still ignored, reserved for Claims: Claim_Status, Claim_Amount_USD,
# Last_Interaction, Client_Feedback.

# Both sets are required, and the check runs before the row loop -- so a
# file missing policy columns fails before writing any customer. This is a
# deliberate behaviour change from Phase 2a, where such a file would have
# loaded customers successfully.
REQUIRED_COLUMNS = set(COLUMN_MAP) | set(POLICY_COLUMN_MAP)

SOURCE = "loaddataset"


class Command(BaseCommand):
    help = "Load customers and their policies from the source dataset CSV. Idempotent on both."

    def add_arguments(self, parser):
        # Positional and required: FR-036 forbids a default that assumes a
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

        counts = {
            "customers": {"created": 0, "updated": 0, "refused": 0},
            "policies": {"created": 0, "updated": 0, "refused": 0},
        }

        for index, raw in enumerate(rows, start=1):
            customer_outcome, policy_outcome = self._process_row(
                raw, index, str(path), dry_run
            )
            counts["customers"][customer_outcome] += 1
            counts["policies"][policy_outcome] += 1

        self._report_counts(counts)

    # -- reading -----------------------------------------------------------

    def _read_rows(self, path):
        """
        Validate the file's existence and structure before any write, so a
        structurally wrong file cannot leave a partial load (FR-046).
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
        """
        Returns (customer_outcome, policy_outcome).

        Both records land or neither does, so a refused policy reports the
        row as refused on BOTH counts rather than leaving a customer
        behind. That is truthful under row-level atomicity: the row was
        refused, not half-applied.
        """
        customer_data = {field: raw.get(column) for column, field in COLUMN_MAP.items()}

        client_id = customer_data.get("client_id")
        existing_customer = (
            Customer.all_objects.filter(client_id=client_id).first() if client_id else None
        )

        customer_serializer = CustomerSerializer(instance=existing_customer, data=customer_data)
        if not customer_serializer.is_valid():
            self._report_refusal(index, customer_serializer.errors)
            return "refused", "refused"

        # The policy is validated BEFORE anything is written. Its customer
        # may not exist yet on a first load, so validation of the policy's
        # own fields runs standalone and the FK is attached after the
        # customer is saved, inside the same transaction.
        policy_data = {
            field: raw.get(column) for column, field in POLICY_COLUMN_MAP.items()
        }
        policy_errors = self._validate_policy_fields(policy_data)
        if policy_errors:
            self._report_refusal(index, policy_errors)
            return "refused", "refused"

        if dry_run:
            return (
                "updated" if existing_customer else "created",
                "updated" if self._existing_policy(existing_customer, policy_data) else "created",
            )

        # One transaction spanning both records, with both audit writes
        # inside it (FR-033, FR-048).
        existing_policy = None
        try:
            with transaction.atomic():
                customer = customer_serializer.save()
                self._record(
                    "customer",
                    "customers.Customer",
                    customer.id,
                    _customer_snapshot(customer),
                    existing_customer,
                    source_path,
                )

                existing_policy = self._existing_policy(customer, policy_data)
                policy_serializer = PolicySerializer(
                    instance=existing_policy,
                    data={**policy_data, "customer": customer.pk},
                )
                if not policy_serializer.is_valid():
                    raise _RowRefused(policy_serializer.errors)

                policy = policy_serializer.save()
                self._record(
                    "policy",
                    "policies.Policy",
                    policy.id,
                    _policy_snapshot(policy),
                    existing_policy,
                    source_path,
                )
        except _RowRefused as refusal:
            self._report_refusal(index, refusal.errors)
            return "refused", "refused"

        return (
            "updated" if existing_customer else "created",
            "updated" if existing_policy else "created",
        )

    def _validate_policy_fields(self, policy_data):
        """
        Validate everything about the policy that does not depend on the
        customer FK, before any write. Returns an error dict, or None.

        The FK itself cannot be checked here on a first load -- the
        customer does not exist yet -- so it is validated inside the
        transaction, where a failure rolls the customer back.
        """
        serializer = PolicySerializer(data=policy_data, partial=True)
        serializer.is_valid()
        errors = {
            field: messages
            for field, messages in serializer.errors.items()
            if field != "customer"
        }
        return errors or None

    def _existing_policy(self, customer, policy_data):
        """
        Match on (customer, policy_type) among LIVE rows only (FR-039).

        Policy.objects already excludes archived rows, which is what stops
        a load from resurrecting a deliberately archived policy.
        """
        if customer is None or customer.pk is None:
            return None
        return Policy.objects.filter(
            customer=customer, policy_type=policy_data.get("policy_type")
        ).first()

    def _record(self, prefix, target_type, target_id, after, existing, source_path):
        record_action(
            actor=None,  # system load, not a person (FR-048)
            action=f"{prefix}.updated" if existing else f"{prefix}.created",
            target_type=target_type,
            target_id=target_id,
            outcome="succeeded",
            before=None,
            after=after,
            context={"source": SOURCE, "file": source_path},
        )

    # -- reporting ---------------------------------------------------------

    def _report_refusal(self, index, errors):
        for field, messages in errors.items():
            detail = messages[0] if isinstance(messages, list) else messages
            self.stdout.write(f"Row {index}: {field} — {detail}")

    def _report_counts(self, counts):
        customers = counts["customers"]
        policies = counts["policies"]
        self.stdout.write(
            "Customers — created: {created}  updated: {updated}  refused: {refused}".format(
                **customers
            )
        )
        self.stdout.write(
            "Policies  — created: {created}  updated: {updated}  refused: {refused}".format(
                **policies
            )
        )


class _RowRefused(Exception):
    """Rolls the row's transaction back so neither record survives."""

    def __init__(self, errors):
        super().__init__("row refused")
        self.errors = errors


def _customer_snapshot(customer):
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


def _policy_snapshot(policy):
    return {
        "customer_id": policy.customer_id,
        "policy_type": policy.policy_type,
        "start_date": policy.start_date.isoformat(),
        "end_date": policy.end_date.isoformat(),
        "premium_usd": str(policy.premium_usd),
        "renewal_probability": (
            str(policy.renewal_probability)
            if policy.renewal_probability is not None
            else None
        ),
    }
