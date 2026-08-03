import pytest

from apps.accounts.factories import UserFactory
from apps.accounts.models import Role

pytestmark = pytest.mark.django_db

ALL_ROLES = [
    Role.FRAUD_ANALYST,
    Role.CLAIMS_ADJUSTER,
    Role.CUSTOMER_SERVICE,
    Role.UNDERWRITER,
    Role.COMPLIANCE_OFFICER,
    Role.RISK_MANAGER,
    Role.PRODUCT_MANAGER,
    Role.EXECUTIVE_LEADERSHIP,
    Role.SYSTEM_ADMINISTRATOR,
]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_user_factory_produces_valid_user_for_each_role(role):
    user = UserFactory(role=role)
    user.full_clean()

    assert user.role == role
    assert user.pk is not None


TRAIT_NAMES = [
    "fraud_analyst",
    "claims_adjuster",
    "customer_service",
    "underwriter",
    "compliance_officer",
    "risk_manager",
    "product_manager",
    "executive_leadership",
    "system_administrator",
]


@pytest.mark.parametrize("trait,role", zip(TRAIT_NAMES, ALL_ROLES))
def test_user_factory_role_traits_require_no_extra_field_setup(trait, role):
    user = UserFactory(**{trait: True})
    user.full_clean()

    assert user.role == role
