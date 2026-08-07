from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from .models import Customer


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer
        django_get_or_create = ("client_id",)
        skip_postgeneration_save = True

    # Starts at CL-90000 so factory-made references never collide with
    # loaded dataset rows (CL-00001..CL-03000) in a test that uses both.
    client_id = factory.Sequence(lambda n: f"CL-{n + 90000:05d}")
    name = factory.Faker("name")
    email = factory.Sequence(lambda n: f"customer{n}@example.com")
    phone = factory.Faker("phone_number")
    age = factory.Faker("random_int", min=18, max=75)
    gender = "Other"
    location = factory.Faker("city")
    lead_source = "Agent"

    # Default to absent, matching an API-created customer. Keeps the
    # FR-006 absent-vs-zero distinction visible by default rather than
    # papered over by the fixture.
    risk_score = None
    fraud_risk_flag = None
    cross_sell_score = None
    archived_at = None

    class Params:
        archived = factory.Trait(archived_at=factory.LazyFunction(timezone.now))
        scored = factory.Trait(
            risk_score=Decimal("0.42"),
            fraud_risk_flag="Low",
            cross_sell_score=Decimal("0.75"),
        )

    @classmethod
    def _get_manager(cls, model_class):
        # Must use all_objects: django_get_or_create looks the instance up
        # before creating, and the default manager hides archived rows.
        # Without this, building an archived customer twice would attempt a
        # duplicate insert against a row it cannot see.
        return model_class.all_objects
