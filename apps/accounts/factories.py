import factory
from factory.django import DjangoModelFactory

from .models import Role, User


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    role = Role.CUSTOMER_SERVICE
    is_active = True
    password = factory.PostGenerationMethodCall("set_password", "test-pass-12345")

    class Params:
        fraud_analyst = factory.Trait(role=Role.FRAUD_ANALYST)
        claims_adjuster = factory.Trait(role=Role.CLAIMS_ADJUSTER)
        customer_service = factory.Trait(role=Role.CUSTOMER_SERVICE)
        underwriter = factory.Trait(role=Role.UNDERWRITER)
        compliance_officer = factory.Trait(role=Role.COMPLIANCE_OFFICER)
        risk_manager = factory.Trait(role=Role.RISK_MANAGER)
        product_manager = factory.Trait(role=Role.PRODUCT_MANAGER)
        executive_leadership = factory.Trait(role=Role.EXECUTIVE_LEADERSHIP)
        system_administrator = factory.Trait(role=Role.SYSTEM_ADMINISTRATOR)
