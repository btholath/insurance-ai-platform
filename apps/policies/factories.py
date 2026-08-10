from datetime import date, timedelta
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.customers.factories import CustomerFactory

from .models import Policy


class PolicyFactory(DjangoModelFactory):
    class Meta:
        model = Policy
        skip_postgeneration_save = True

    # SubFactory: a test needing several policies for ONE customer must
    # pass customer= explicitly, otherwise each policy gets its own
    # customer and the FR-003 multi-policy case is never exercised.
    customer = factory.SubFactory(CustomerFactory)

    policy_type = "Auto"

    # Defaults produce a currently-in-force policy: started a year ago,
    # ends a year from now. Without this, every factory-made policy would
    # be in force *by accident* and the FR-020 expiry filter would pass
    # vacuously -- the `expired` trait is what actually exercises it.
    start_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    end_date = factory.LazyFunction(lambda: date.today() + timedelta(days=365))

    premium_usd = Decimal("750.23")

    # Absent by default, matching an API-created policy, so the FR-004
    # absent-vs-zero distinction stays visible rather than papered over.
    renewal_probability = None
    archived_at = None

    class Params:
        archived = factory.Trait(archived_at=factory.LazyFunction(timezone.now))
        expired = factory.Trait(
            start_date=factory.LazyFunction(lambda: date.today() - timedelta(days=730)),
            end_date=factory.LazyFunction(lambda: date.today() - timedelta(days=1)),
        )
        scored = factory.Trait(renewal_probability=Decimal("0.06"))

    @classmethod
    def _get_manager(cls, model_class):
        # all_objects so archived policies can be built directly; the
        # default manager would hide them from any get_or_create path.
        return model_class.all_objects
