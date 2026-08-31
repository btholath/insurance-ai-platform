"""
Phase 3b, US4 (T037-T040): `loaddataset` at realistic reload volume never
corrupts the risk book, even though every row's Customer/Policy/Claim
saves fire `post_save` and enqueue a recompute (FR-004's unconditional
trigger) -- the redundant task volume is an accepted tradeoff (FR-017),
not something this feature suppresses. These tests exercise the loader's
actual serializer-backed writes, not RiskAssessmentFactory shortcuts, so
the same post_save/on_commit path production traffic uses is what's under
test here (research.md §1; apps/risk/signals.py).
"""
import csv
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.customers.models import Customer
from apps.risk.models import RiskAssessment
from apps.risk.tasks import recompute_customer_risk

from .. import engine

pytestmark = pytest.mark.django_db

HEADER = [
    "Client_ID", "Client_Name", "Client_Email", "Client_Phone", "Client_Age",
    "Client_Gender", "Client_Location", "Policy_Type", "Policy_Start_Date",
    "Policy_End_Date", "Policy_Premium_USD", "Claim_Status", "Claim_Amount_USD",
    "Last_Interaction", "Risk_Score", "Renewal_Probability", "Fraud_Risk_Flag",
    "Cross_Sell_Score", "Lead_Source", "Client_Feedback",
]


def row(client_id, name="Patrick Hart", email=None, age="22"):
    return {
        "Client_ID": client_id, "Client_Name": name,
        "Client_Email": email or f"{client_id.lower()}@example.com",
        "Client_Phone": "588-240-1527", "Client_Age": age,
        "Client_Gender": "Other", "Client_Location": "New Steven",
        "Policy_Type": "Auto", "Policy_Start_Date": "2023-01-13",
        "Policy_End_Date": "2027-03-11", "Policy_Premium_USD": "1000.00",
        "Claim_Status": "Approved", "Claim_Amount_USD": "500.00",
        "Last_Interaction": "2024-12-02", "Risk_Score": "0.16",
        "Renewal_Probability": "0.06", "Fraud_Risk_Flag": "Low",
        "Cross_Sell_Score": "0.75", "Lead_Source": "Agent",
        "Client_Feedback": "Very helpful.",
    }


def write_csv(tmp_path, rows, name="data.csv"):
    path = tmp_path / name
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return str(path)


def assessed_population(tmp_path, n, django_capture_on_commit_callbacks):
    """
    Load n customers via the real loader, then run the real engine over
    each -- production's own compute path, not a factory shortcut -- so
    the "before" snapshot this module compares against is exactly what a
    prior real load-and-score cycle would have produced.
    """
    rows = [row(f"CL-{i:05d}") for i in range(n)]
    path = write_csv(tmp_path, rows)
    with django_capture_on_commit_callbacks(execute=True):
        call_command("loaddataset", path)

    customers = list(Customer.objects.order_by("client_id"))
    for customer in customers:
        engine.persist(customer, engine.score_customer(customer), actor=None)

    return path, customers, rows


class TestReloadReproducesIdenticalAssessment:
    """FR-016, Acceptance Scenario 1: re-running the loader against
    unchanged source data for already-assessed customers must not change
    any customer's score, tier, or factor rows."""

    def test_reload_of_unchanged_rows_reproduces_identical_assessments(
        self, tmp_path, django_capture_on_commit_callbacks
    ):
        path, customers, _ = assessed_population(
            tmp_path, 5, django_capture_on_commit_callbacks
        )

        before = {
            c.id: {
                "score": c.risk_assessment.score,
                "tier": c.risk_assessment.tier,
                "factors": sorted(
                    (f.factor, f.points, f.band_label)
                    for f in c.risk_assessment.factors.all()
                ),
            }
            for c in customers
        }

        with django_capture_on_commit_callbacks(execute=True):
            call_command("loaddataset", path)

        for c in customers:
            c.risk_assessment.refresh_from_db()
            after_factors = sorted(
                (f.factor, f.points, f.band_label)
                for f in c.risk_assessment.factors.all()
            )
            assert c.risk_assessment.score == before[c.id]["score"]
            assert c.risk_assessment.tier == before[c.id]["tier"]
            assert after_factors == before[c.id]["factors"]


class TestReloadCreatesNoDuplicateAssessments:
    """Acceptance Scenario 2, SC-006: N already-assessed customers reloaded
    must still leave exactly N RiskAssessment rows -- no duplicates from
    the N redundant recompute enqueues each row's saves produce."""

    def test_reload_leaves_exactly_n_assessments_for_n_customers(
        self, tmp_path, django_capture_on_commit_callbacks
    ):
        _, customers, _ = assessed_population(
            tmp_path, 5, django_capture_on_commit_callbacks
        )
        assert RiskAssessment.objects.count() == 5

        path = write_csv(tmp_path, [row(f"CL-{i:05d}") for i in range(5)])
        with django_capture_on_commit_callbacks(execute=True):
            call_command("loaddataset", path)

        assert RiskAssessment.objects.count() == 5
        assert RiskAssessment.objects.filter(
            customer__in=customers
        ).values("customer").distinct().count() == 5


class TestReloadEnqueuesProportionalRedundantTasks:
    """FR-017: assert the redundant-but-correct behavior directly -- the
    NUMBER of recompute enqueues a reload produces, not deduplicated below
    the number of records the loader wrote, per the user description's
    explicit instruction to test this rather than only the happy-path end
    state."""

    def test_enqueue_count_is_proportional_to_records_written(
        self, tmp_path, django_capture_on_commit_callbacks
    ):
        path, customers, _ = assessed_population(
            tmp_path, 4, django_capture_on_commit_callbacks
        )

        with patch.object(recompute_customer_risk, "delay") as delay, \
                django_capture_on_commit_callbacks(execute=True):
            call_command("loaddataset", path)

        # Each row rewrites customer + policy + claim (all fields
        # unchanged, but the loader's serializer .save() still fires
        # post_save unconditionally per FR-004) -- three saves per
        # customer, three enqueues per customer, none coalesced.
        assert delay.call_count == 3 * len(customers)

        enqueued_customer_ids = [call.args[0] for call in delay.call_args_list]
        for customer in customers:
            assert enqueued_customer_ids.count(customer.id) == 3


class TestReloadPreservesSumInvariant:
    """SC-002, SC-006: every assessment's factors must still sum to its
    score after a full reload-and-drain cycle, reusing Phase 3a's
    sum-invariant assertion pattern (test_engine.py)."""

    def test_every_assessment_satisfies_sum_invariant_after_reload(
        self, tmp_path, django_capture_on_commit_callbacks
    ):
        path, customers, _ = assessed_population(
            tmp_path, 5, django_capture_on_commit_callbacks
        )

        with django_capture_on_commit_callbacks(execute=True):
            call_command("loaddataset", path)

        assessments = RiskAssessment.objects.filter(customer__in=customers)
        assert assessments.count() == 5
        for assessment in assessments:
            factor_total = sum(f.points for f in assessment.factors.all())
            assert factor_total == assessment.score
