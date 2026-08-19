"""
Null every source-derived risk_score (T089; FR-056, SC-013).

Phase 3a makes RiskAssessment.score the record of truth and
Customer.risk_score a denormalised mirror written only by the risk
engine (data-model.md). A score carried over from the CSV load has no
assessment and no explanation behind it, so it cannot be allowed to
survive alongside the new contract -- the risk engine must be what wrote
every value in this column going forward.

The reverse is a deliberate no-op: nulling is a one-way trip. Source
values are not recorded anywhere the reverse could restore them from
(loaddataset.py no longer maps the column, and even if it did, the source
CSV is supplied at run time and not committed), so a reverse migration
that pretended to restore data would be lying. Re-running the forward
loader after a reversal would leave the column null again, which is the
same outcome as never reversing at all.
"""
from django.db import migrations


def null_risk_scores(apps, schema_editor):
    """
    `apps.get_model` returns a historical model whose `objects` is a
    plain, unfiltered `Manager()` regardless of the real model's manager
    name or behaviour (Django does not carry custom manager logic into
    migration state without `use_in_migrations = True`, which
    CustomerManager does not set). That plain manager already sees every
    row, archived or not, so there is no `all_objects` here to reach for
    and none is needed.
    """
    Customer = apps.get_model("customers", "Customer")
    Customer.objects.update(risk_score=None)


def noop_reverse(apps, schema_editor):
    """No-op: see the module docstring for why this cannot restore data."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(null_risk_scores, noop_reverse),
    ]
