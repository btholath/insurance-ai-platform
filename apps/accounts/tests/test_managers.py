import pytest

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="", password="a-strong-password-123", role=Role.CLAIMS_ADJUSTER)


def test_create_user_requires_role():
    with pytest.raises(ValueError, match="role"):
        User.objects.create_user(email="user@example.com", password="a-strong-password-123", role=None)


def test_create_superuser_creates_valid_admin_account():
    user = User.objects.create_superuser(
        email="admin@example.com", password="a-strong-password-123", role=Role.SYSTEM_ADMINISTRATOR
    )

    assert user.pk is not None
    assert user.email == "admin@example.com"
    assert user.role == Role.SYSTEM_ADMINISTRATOR
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("a-strong-password-123")


def test_create_superuser_rejects_is_staff_false():
    with pytest.raises(ValueError, match="is_staff"):
        User.objects.create_superuser(
            email="admin2@example.com", password="a-strong-password-123", role=Role.SYSTEM_ADMINISTRATOR, is_staff=False
        )


def test_create_superuser_rejects_is_superuser_false():
    with pytest.raises(ValueError, match="is_superuser"):
        User.objects.create_superuser(
            email="admin3@example.com",
            password="a-strong-password-123",
            role=Role.SYSTEM_ADMINISTRATOR,
            is_superuser=False,
        )
