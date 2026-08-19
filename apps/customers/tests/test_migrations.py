"""
Data migration tests (T089; FR-056, SC-013).

Customer.risk_score becomes a denormalised mirror of RiskAssessment.score
in Phase 3a, written only by the risk engine. This migration nulls every
row so no customer carries a source-derived score once the new contract
takes effect.
"""
import importlib
from decimal import Decimal

import pytest
from django.apps import apps as real_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.customers.factories import CustomerFactory

pytestmark = pytest.mark.django_db

_migration_module = importlib.import_module(
    "apps.customers.migrations.0002_null_source_risk_score"
)


def test_historical_model_has_no_all_objects_manager():
    """
    The regression this migration's implementation had to route around:
    apps.get_model's historical model carries only `objects`, a plain
    unfiltered Manager -- not the real CustomerManager, and no
    `all_objects` at all (Django does not carry custom manager names into
    migration state without use_in_migrations=True, which CustomerManager
    does not set). null_risk_scores() must work with what history
    actually offers.
    """
    executor = MigrationExecutor(connection)
    state = executor.loader.project_state(("customers", "0002_null_source_risk_score"))
    HistoricalCustomer = state.apps.get_model("customers", "Customer")

    assert hasattr(HistoricalCustomer, "objects")
    assert not hasattr(HistoricalCustomer, "all_objects")


def test_null_risk_scores_nulls_both_live_and_archived_customers():
    """
    Exercised against REAL historical state (via project_state()), not
    the live app registry -- passing real_apps here would route through
    CustomerManager's archival filter and silently skip the archived row,
    which is exactly the bug this migration must not have.
    """
    live = CustomerFactory(risk_score=Decimal("0.42"))
    archived = CustomerFactory(risk_score=Decimal("0.77"))
    archived.archived_at = timezone.now()
    archived.save()

    executor = MigrationExecutor(connection)
    state = executor.loader.project_state(("customers", "0002_null_source_risk_score"))

    _migration_module.null_risk_scores(state.apps, None)

    live.refresh_from_db()
    archived.refresh_from_db()
    assert live.risk_score is None
    assert archived.risk_score is None


def test_reverse_is_a_documented_noop():
    """The reverse cannot restore source values and must not pretend to."""
    result = _migration_module.noop_reverse(real_apps, None)
    assert result is None
