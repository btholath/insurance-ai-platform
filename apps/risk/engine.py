"""
The pure-evaluation/persistence split (T032-T033, research §6).

`score_customer()` reads and evaluates; `persist()` writes. Nothing in
between calls out to the ORM on the read side and nothing on the write side
recomputes -- the split is what lets Phase 3b call `persist()` from a
Celery task without rewriting this module, since the expensive read/evaluate
work and the atomic write are already two separate calls.

This is why the boundary matters: a background task only needs to call
`score_customer()` off the request thread and hand the result to
`persist()` exactly as this module's own callers already do (the
`RiskAssessmentViewSet.recompute` action, `computerisk`). Nothing about
scoring, persistence, or the transaction changes to support that --
Phase 3b becomes additive on top of this file, not a rewrite of it.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_action

from . import rules
from .models import RiskAssessment, RiskFactor


@dataclass(frozen=True)
class AssessmentResult:
    """The output of evaluation, before anything is written."""

    score: int
    tier: str
    rule_set_version: str
    factors: list  # list[rules.FactorResult]


def score_customer(customer) -> AssessmentResult:
    """
    FR-016: reads the customer's live policies and claims through their
    default managers, so archival exclusion falls out of the existing
    dual-manager design rather than needing a filter here. Read-only -- no
    writes (research §6).
    """
    policies = list(customer.policies.all())
    claims = [claim for policy in policies for claim in policy.claims.all()]

    claim_inputs = [
        rules.ClaimInput(amount=c.claim_amount_usd, status=c.claim_status) for c in claims
    ]

    total_premium = sum((p.premium_usd for p in policies), Decimal("0"))
    total_claimed = sum(
        (Decimal(str(c.amount)) for c in claim_inputs if float(c.amount) > 0), Decimal("0")
    )
    claims_ratio = (total_claimed / total_premium) if total_premium > 0 else None

    factors = rules.evaluate(
        age=customer.age,
        policy_types=[p.policy_type for p in policies],
        claims=claim_inputs,
        claims_ratio=claims_ratio,
    )

    score = sum(f.points for f in factors)
    tier = rules.tier_for(score)

    return AssessmentResult(
        score=score,
        tier=tier,
        rule_set_version=rules.RULE_SET_VERSION,
        factors=factors,
    )


def persist(customer, result: AssessmentResult, *, actor) -> RiskAssessment:
    """
    FR-035, FR-037, FR-048, FR-052, FR-053, FR-054: one transaction,
    all-or-nothing. Upserts the RiskAssessment, fully replaces its factor
    rows, mirrors Customer.risk_score, and writes the risk.computed audit
    entry -- inside this same transaction because this is the sole write
    path for scores (see engine.py's module docstring at T092 and D1 in
    the analyze remediation).
    """
    with transaction.atomic():
        locked_customer = type(customer).objects.select_for_update().get(pk=customer.pk)

        previous = RiskAssessment.objects.filter(customer=locked_customer).first()
        previous_score = previous.score if previous else None

        # Mirror the score onto the customer via a raw update(), not
        # .save(): the post_save signal that drives automatic recompute
        # (apps/customers/apps.py) is connected unconditionally, so a
        # .save() here would re-enqueue recompute_customer_risk from
        # inside its own persist() call -- an unbounded loop under eager
        # execution (each recompute re-saves the customer, which
        # re-enqueues another recompute). update() doesn't fire post_save.
        #
        # update() also skips auto_now, so updated_at is set explicitly
        # here -- using the same timestamp as computed_at, computed once,
        # so customer.updated_at is never fractionally ahead of
        # computed_at (staleness (T070) compares the two; see T033).
        computed_at = timezone.now()
        new_risk_score = round(Decimal(result.score) / 100, 2)
        type(locked_customer).objects.filter(pk=locked_customer.pk).update(
            risk_score=new_risk_score,
            updated_at=computed_at,
        )
        # update() bypasses the ORM instance, so keep it in sync in Python
        # for any caller that reads customer/locked_customer after persist().
        locked_customer.risk_score = new_risk_score
        locked_customer.updated_at = computed_at
        assessment, _created = RiskAssessment.objects.update_or_create(
            customer=locked_customer,
            defaults={
                "score": result.score,
                "tier": result.tier,
                "rule_set_version": result.rule_set_version,
                "computed_at": computed_at,
                "computed_by": actor,
            },
        )

        # Fully replace, never merge (data-model.md "Lifecycle") -- a merge
        # could leave a factor row from an earlier rule version beside
        # newer ones, breaking the sum invariant.
        RiskFactor.objects.filter(assessment=assessment).delete()
        RiskFactor.objects.bulk_create(
            RiskFactor(
                assessment=assessment,
                factor=f.factor,
                status=f.status,
                observed_value=f.observed_value,
                band_label=f.band_label,
                points=f.points,
                unevaluable_reason=f.unevaluable_reason,
            )
            for f in result.factors
        )

        record_action(
            actor=actor,
            action="risk.computed",
            target_type="risk.RiskAssessment",
            target_id=assessment.id,
            outcome="succeeded",
            before={"score": previous_score},
            after={
                "score": result.score,
                "tier": result.tier,
                "rule_set_version": result.rule_set_version,
            },
            context={"rule_set_version": result.rule_set_version},
        )

    return assessment
