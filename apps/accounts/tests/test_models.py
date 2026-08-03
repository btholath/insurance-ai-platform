import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection

from apps.accounts.factories import UserFactory
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_full_clean_rejects_role_outside_the_nine_values():
    user = UserFactory.build(role="auditor")

    with pytest.raises(ValidationError):
        user.full_clean()


def test_db_check_constraint_rejects_invalid_role_on_raw_insert():
    user = UserFactory(role="claims_adjuster")

    with pytest.raises(IntegrityError):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE accounts_user SET role = %s WHERE id = %s",
                ["auditor", user.id],
            )


def test_db_check_constraint_rejects_invalid_role_via_queryset_update():
    user = UserFactory(role="claims_adjuster")

    with pytest.raises(IntegrityError):
        User.objects.filter(pk=user.pk).update(role="auditor")
