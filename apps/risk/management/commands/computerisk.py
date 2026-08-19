"""
Batch scoring across the customer book (T055-T059;
contracts/computerisk-command.md).

Follows loaddataset's shape: same reporting discipline, same per-record
atomicity, same "continue past a failure and report it" posture. Each
customer is scored and persisted inside its OWN transaction
(engine.persist already wraps itself in transaction.atomic()), so a
failure on one customer never aborts the run and never leaves a customer
with a score whose factors are missing (FR-032, FR-035).
"""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import record_action
from apps.customers.models import Customer

from ... import engine, rules
from ...models import RiskAssessment


class Command(BaseCommand):
    help = "Compute risk scores for the customer book."

    def add_arguments(self, parser):
        parser.add_argument("--customer", help="Score one customer, by client_id")
        parser.add_argument("--tier", help="Rescore only customers currently in this tier")
        parser.add_argument(
            "--dry-run", action="store_true", help="Compute and report, write nothing"
        )
        parser.add_argument("--limit", type=int, help="Stop after N customers")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        queryset = self._build_queryset(options)
        if queryset is None:
            raise CommandError("this should not happen")  # pragma: no cover

        customers = list(queryset)
        if options.get("limit"):
            customers = customers[: options["limit"]]

        self.stdout.write(f"Computing risk scores (rule set {rules.RULE_SET_VERSION})...\n")

        scored = 0
        skipped = []
        failed = []
        tier_counts = {}

        for customer in customers:
            if not customer.policies.exists():
                skipped.append((customer, "no live policy, so premium and coverage type are unknown"))
                continue

            try:
                result = engine.score_customer(customer)
                if not dry_run:
                    engine.persist(customer, result, actor=None)
                scored += 1
                tier_counts[result.tier] = tier_counts.get(result.tier, 0) + 1
            except Exception as exc:  # noqa: BLE001 -- must not abort the batch
                failed.append((customer, str(exc)))

        if not dry_run:
            record_action(
                actor=None,
                action="risk.batch_computed",
                target_type="risk.RiskAssessment",
                target_id="batch",
                outcome="succeeded",
                context={
                    "scored": scored,
                    "skipped": len(skipped),
                    "failed": len(failed),
                    "rule_set_version": rules.RULE_SET_VERSION,
                    "dry_run": dry_run,
                },
            )

        self._report(scored, skipped, failed, tier_counts)

        if failed:
            raise SystemExit(2)

    def _build_queryset(self, options):
        queryset = Customer.objects.prefetch_related("policies__claims")

        if options.get("customer"):
            queryset = queryset.filter(client_id=options["customer"])
            if not queryset.exists():
                self.stderr.write(f"Unknown customer: {options['customer']}\n")
                raise SystemExit(1)

        if options.get("tier"):
            tier = options["tier"]
            valid_tiers = {t for t, _label in RiskAssessment._meta.get_field("tier").choices}
            if tier not in valid_tiers:
                self.stderr.write(f"Unknown tier: {tier}\n")
                raise SystemExit(1)
            queryset = queryset.filter(risk_assessment__tier=tier)

        return queryset.order_by("id")

    def _report(self, scored, skipped, failed, tier_counts):
        self.stdout.write(
            f"\n  scored:   {scored}\n  skipped:  {len(skipped)}\n  failed:   {len(failed)}\n"
        )

        if skipped:
            self.stdout.write("\nSkipped:\n")
            for customer, reason in skipped:
                self.stdout.write(f"  {customer.client_id}  {reason}\n")

        if failed:
            self.stdout.write("\nFailed:\n")
            for customer, reason in failed:
                self.stdout.write(f"  {customer.client_id}  {reason}\n")

        if scored:
            self.stdout.write("\nTier distribution:\n")
            for tier in ("low", "moderate", "elevated", "high"):
                count = tier_counts.get(tier, 0)
                pct = count / scored * 100
                self.stdout.write(f"  {tier:<12}{count:>5}  ({pct:.1f}%)\n")
