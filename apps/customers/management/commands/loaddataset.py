"""
Load customers, their policies, AND their claims from the source dataset
CSV (Phase 2a FR-036 through FR-048; Phase 2c FR-035 through FR-046).

DOCUMENTED LIMITATION -- claim reconciliation matches on the POLICY.

The file carries no claim identifier, so a row's claim is matched to an
existing one by its policy alone. That is sound for this export and
verified against it: all 3,000 (Client_ID, Policy_Type) pairs are
distinct, so the file carries at most one claim per policy. A FUTURE
export with two claims against one policy would reconcile both onto the
first record, silently. No better key exists without a claim identifier
in the source; this is recorded here rather than left to tribal memory.
The same limitation applies to ClaimLoadAnomaly, which is keyed
one-per-policy for the same reason.

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
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_action
from apps.claims.models import (
    AnomalyStatus,
    Claim,
    ClaimLoadAnomaly,
    ClearedReason,
)
from apps.claims.serializers import ClaimSerializer
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

# CSV column -> Claim field. The policy FK is resolved per row rather than
# mapped, since a claim is filed against the policy this same row produced.
CLAIM_COLUMN_MAP = {
    "Claim_Status": "claim_status",
    "Claim_Amount_USD": "claim_amount_usd",
}

# Still ignored: Last_Interaction and Client_Feedback. Last_Interaction is
# a customer-level field and is deliberately NOT repurposed as a claim
# date -- doing so would assert a filing date the source never recorded.
# All three claim-bearing modules now consume their columns.

# All three sets are required, and the check runs before the row loop -- so
# a file missing claim columns fails before writing any customer or policy
# (FR-037), rather than loading them and silently skipping claims. This
# mirrors the deliberate behaviour change Phase 2b made for policy columns.
REQUIRED_COLUMNS = set(COLUMN_MAP) | set(POLICY_COLUMN_MAP) | set(CLAIM_COLUMN_MAP)

SOURCE = "loaddataset"

# The source's fourth claim status. A VALID value in the file, but never a
# valid claim: it describes the ABSENCE of a claim, so it is not in
# ClaimStatus at all. The loader must branch on it BEFORE constructing a
# ClaimSerializer -- feeding it in would report a validation error for a
# row that is not invalid, refusing 754 valid rows in the real dataset.
NO_CLAIM = "No Claim"


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
            "claims": {"created": 0, "updated": 0, "refused": 0, "skipped": 0},
            "anomalies": {"recorded": 0, "cleared": 0, "corrected": 0, "absent": 0},
        }

        # Two sets tracked across the whole run. `policies_seen` is every
        # policy the file produced a row for; `policies_conflicting` is
        # those whose row was No Claim with a non-zero amount. The
        # difference between them is what decides an anomaly's clearing
        # reason after the loop.
        policies_seen = set()
        policies_conflicting = set()

        for index, raw in enumerate(rows, start=1):
            outcomes = self._process_row(
                raw, index, str(path), dry_run, policies_seen, policies_conflicting
            )
            customer_outcome, policy_outcome, claim_outcome = outcomes
            counts["customers"][customer_outcome] += 1
            counts["policies"][policy_outcome] += 1
            if claim_outcome == "anomaly":
                counts["anomalies"]["recorded"] += 1
            else:
                counts["claims"][claim_outcome] += 1

        # Clearing runs AFTER the row loop, in its own transaction. It is a
        # whole-file conclusion -- "not seen in this run" cannot be known
        # until the run ends -- and a per-row transaction cannot express it.
        self._clear_stale_anomalies(
            policies_seen, policies_conflicting, str(path), dry_run, counts
        )

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

    def _process_row(
        self, raw, index, source_path, dry_run, policies_seen, policies_conflicting
    ):
        """
        Returns (customer_outcome, policy_outcome, claim_outcome).

        All three records land or none does, so a refused claim reports the
        row as refused on ALL counts rather than leaving a customer and
        policy behind. That is truthful under row-level atomicity: the row
        was refused, not partly applied.

        The claim outcome has two values the others do not: `skipped` (a
        No Claim row with a zero amount) and `anomaly` (a No Claim row with
        a non-zero amount). Neither is an error -- FR-045 is explicit that
        an anomaly is not a refusal, and the row's customer and policy load
        normally in both cases.
        """
        customer_data = {field: raw.get(column) for column, field in COLUMN_MAP.items()}

        client_id = customer_data.get("client_id")
        existing_customer = (
            Customer.all_objects.filter(client_id=client_id).first() if client_id else None
        )

        customer_serializer = CustomerSerializer(instance=existing_customer, data=customer_data)
        if not customer_serializer.is_valid():
            self._report_refusal(index, customer_serializer.errors)
            return "refused", "refused", "refused"

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
            return "refused", "refused", "refused"

        # The No Claim branch is taken BEFORE any serializer is built --
        # see the NO_CLAIM comment above. Getting this backwards would
        # refuse 754 valid rows.
        claim_data = {field: raw.get(column) for column, field in CLAIM_COLUMN_MAP.items()}
        claim_kind, claim_errors = self._classify_claim(claim_data)
        if claim_errors:
            self._report_refusal(index, claim_errors)
            return "refused", "refused", "refused"

        if dry_run:
            existing_policy = self._existing_policy(existing_customer, policy_data)
            if claim_kind == "anomaly":
                # A dry run must still record what it SAW, so the clearing
                # decision it previews matches the real run's.
                if existing_policy is not None:
                    policies_seen.add(existing_policy.pk)
                    policies_conflicting.add(existing_policy.pk)
                claim_outcome = "anomaly"
            elif claim_kind == "skipped":
                if existing_policy is not None:
                    policies_seen.add(existing_policy.pk)
                claim_outcome = "skipped"
            else:
                if existing_policy is not None:
                    policies_seen.add(existing_policy.pk)
                claim_outcome = (
                    "updated"
                    if existing_policy is not None
                    and self._existing_claim(existing_policy) is not None
                    else "created"
                )
            return (
                "updated" if existing_customer else "created",
                "updated" if existing_policy else "created",
                claim_outcome,
            )

        # One transaction spanning ALL THREE records, with every audit
        # write inside it (FR-034, FR-038).
        existing_policy = None
        existing_claim = None
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

                policies_seen.add(policy.pk)

                if claim_kind == "anomaly":
                    policies_conflicting.add(policy.pk)
                    self._record_anomaly(policy, claim_data, source_path)
                    claim_outcome = "anomaly"
                elif claim_kind == "skipped":
                    claim_outcome = "skipped"
                else:
                    existing_claim = self._existing_claim(policy)
                    claim_serializer = ClaimSerializer(
                        instance=existing_claim,
                        data={**claim_data, "policy": policy.pk},
                    )
                    if not claim_serializer.is_valid():
                        raise _RowRefused(claim_serializer.errors)

                    claim = claim_serializer.save()
                    self._record(
                        "claim",
                        "claims.Claim",
                        claim.id,
                        _claim_snapshot(claim),
                        existing_claim,
                        source_path,
                    )
                    claim_outcome = "updated" if existing_claim else "created"
        except _RowRefused as refusal:
            self._report_refusal(index, refusal.errors)
            return "refused", "refused", "refused"

        return (
            "updated" if existing_customer else "created",
            "updated" if existing_policy else "created",
            claim_outcome,
        )

    def _classify_claim(self, claim_data):
        """
        Decide what kind of claim row this is, BEFORE any serializer runs.

        Returns (kind, errors) where kind is "claim", "skipped", or
        "anomaly". Only the amount is parsed here, and only when the status
        is No Claim -- everything else is left to ClaimSerializer so there
        stays exactly one definition of claim validity.
        """
        status = (claim_data.get("claim_status") or "").strip()

        if status != NO_CLAIM:
            return "claim", None

        raw_amount = claim_data.get("claim_amount_usd")
        try:
            amount = Decimal(str(raw_amount).strip() or "0")
        except (InvalidOperation, ValueError, AttributeError):
            return None, {"claim_amount_usd": [f"Cannot parse claim amount: {raw_amount!r}"]}

        # A No Claim row carrying money contradicts itself. The status is
        # authoritative (no claim is invented from an uncorroborated
        # amount), but the contradiction is retained rather than dropped.
        return ("anomaly" if amount != 0 else "skipped"), None

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

    def _existing_claim(self, policy):
        """
        Match a row's claim on its POLICY, among LIVE rows only (FR-035).

        Claim.objects excludes archived rows, so a load after an archival
        creates a fresh claim rather than resurrecting a deliberately
        removed one -- the same rule the policy matcher uses, and
        deliberately the opposite of the customer matcher, which resolves
        through all_objects because an archived client_id stays reserved.

        See the module docstring for why matching on the policy alone is
        sound for this export, and where it would break for another.
        """
        if policy is None or policy.pk is None:
            return None
        return Claim.objects.filter(policy=policy).first()

    # -- anomalies ---------------------------------------------------------

    def _record_anomaly(self, policy, claim_data, source_path):
        """
        Record, refresh, or re-raise the anomaly for this policy (FR-041,
        FR-043, FR-044b).

        update_or_create on a unique policy is what makes SC-012 hold: the
        count stays at 390 across any number of runs rather than growing by
        390 each time.
        """
        now = timezone.now()
        existing = ClaimLoadAnomaly.objects.filter(policy=policy).first()

        observed = {
            "source_status": (claim_data.get("claim_status") or "").strip(),
            "source_amount_usd": Decimal(str(claim_data.get("claim_amount_usd")).strip()),
            "last_observed_at": now,
            "source_file": source_path,
        }

        if existing is None:
            anomaly = ClaimLoadAnomaly.objects.create(
                policy=policy,
                status=AnomalyStatus.OPEN,
                first_observed_at=now,
                **observed,
            )
            self._record_anomaly_action("recorded", anomaly, source_path)
            return

        if existing.status == AnomalyStatus.CLEARED:
            # FR-044b: it conflicts again, so it is current again. The
            # clearing reason and timestamp reset -- this row now has no
            # memory of having been cleared, which is precisely why the
            # append-only audit trail is load-bearing rather than
            # decorative (FR-048a).
            for field, value in observed.items():
                setattr(existing, field, value)
            existing.status = AnomalyStatus.OPEN
            existing.cleared_reason = None
            existing.cleared_at = None
            existing.save()
            self._record_anomaly_action("reraised", existing, source_path)
            return

        # Already open: refresh the observation. Deliberately NO audit
        # entry -- nothing changed about the observation, and one entry per
        # run would be noise that grows linearly with the number of loads.
        for field, value in observed.items():
            setattr(existing, field, value)
        existing.save(update_fields=list(observed))

    def _clear_stale_anomalies(
        self, policies_seen, policies_conflicting, source_path, dry_run, counts
    ):
        """
        Clear every still-open anomaly that did NOT conflict in this run,
        with the reason decided by one question: did we see the row at all?

        - policy IN policies_seen      -> corrected (resolution OBSERVED)
        - policy NOT in policies_seen  -> absent    (nothing observed)

        Collapsing these would let a later phase count unexplained
        disappearances as verified corrections (FR-044, FR-044a).

        Runs in its own transaction after the row loop: "not seen in this
        run" is a whole-file conclusion a per-row transaction cannot
        express.
        """
        stale = ClaimLoadAnomaly.objects.filter(status=AnomalyStatus.OPEN).exclude(
            policy_id__in=policies_conflicting
        )

        if dry_run:
            # Report what WOULD be cleared without writing. A preview that
            # reports a different number than the real run would make dry
            # run useless for the operator deciding whether to proceed.
            for anomaly in stale:
                reason = (
                    ClearedReason.CORRECTED
                    if anomaly.policy_id in policies_seen
                    else ClearedReason.ABSENT
                )
                counts["anomalies"]["cleared"] += 1
                counts["anomalies"][reason] += 1
            return

        now = timezone.now()
        with transaction.atomic():
            for anomaly in stale:
                reason = (
                    ClearedReason.CORRECTED
                    if anomaly.policy_id in policies_seen
                    else ClearedReason.ABSENT
                )
                anomaly.status = AnomalyStatus.CLEARED
                anomaly.cleared_reason = reason
                anomaly.cleared_at = now
                anomaly.save(update_fields=["status", "cleared_reason", "cleared_at"])

                self._record_anomaly_action(f"cleared_{reason}", anomaly, source_path)

                counts["anomalies"]["cleared"] += 1
                counts["anomalies"][reason] += 1

    def _record_anomaly_action(self, action, anomaly, source_path):
        """
        FR-048a: the clearing reason is a DISTINCT ACTION NAME, not prose in
        a context blob a reader must interpret.

        `action` is indexed on AuditLog whereas a JSON context key is not,
        so "every confirmed correction, ever" stays a single indexed query
        even for anomalies cleared and re-raised more than once.
        """
        record_action(
            actor=None,  # system load, not a person (FR-048)
            action=f"claim_anomaly.{action}",
            target_type="claims.ClaimLoadAnomaly",
            target_id=anomaly.id,
            outcome="succeeded",
            before=None,
            after={
                "policy_id": anomaly.policy_id,
                "source_status": anomaly.source_status,
                "source_amount_usd": str(anomaly.source_amount_usd),
                "status": anomaly.status,
                "cleared_reason": anomaly.cleared_reason,
            },
            context={"source": SOURCE, "file": source_path},
        )

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
        self.stdout.write(
            "Customers — created: {created}  updated: {updated}  refused: {refused}".format(
                **counts["customers"]
            )
        )
        self.stdout.write(
            "Policies  — created: {created}  updated: {updated}  refused: {refused}".format(
                **counts["policies"]
            )
        )
        # Claims report on one line WITH the other entities (FR-036), with
        # a fourth count the others do not have.
        self.stdout.write(
            "Claims    — created: {created}  updated: {updated}  "
            "refused: {refused}  skipped: {skipped}".format(**counts["claims"])
        )
        # Anomalies report on their OWN line (FR-045): they are not a claim
        # outcome, and folding them in would suggest they are. The clearing
        # breakdown is always shown split by reason, even at zero -- an
        # operator who never sees the two numbers separated has no reason
        # to learn that they differ.
        self.stdout.write(
            "Anomalies — recorded: {recorded}  cleared: {cleared}  "
            "(corrected: {corrected}  absent: {absent})".format(**counts["anomalies"])
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


def _claim_snapshot(claim):
    return {
        "policy_id": claim.policy_id,
        "claim_status": claim.claim_status,
        "claim_amount_usd": str(claim.claim_amount_usd),
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
