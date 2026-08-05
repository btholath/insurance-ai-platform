"""
FR-032: running the test suite must never touch the development database.
pytest-django creates and drops a separate test database per run; these
tests prove that separation is real, not merely configured.
"""
import os
import subprocess
import sys

import pytest

DEV_DB_COMMAND = [
    sys.executable,
    "manage.py",
    "shell",
    "--settings=config.settings.dev",
    "-c",
    "from apps.accounts.models import User; print(User.objects.count())",
]


def _dev_user_count():
    result = subprocess.run(
        DEV_DB_COMMAND,
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


def test_pytest_django_test_database_name_differs_from_configured_dev_database():
    # Reading settings.DATABASES["default"]["NAME"] from *inside* a running
    # pytest-django process would be comparing the mutated test-DB name
    # against itself — pytest-django patches that dict in place at session
    # setup, it does not leave a separate "dev" copy around. The real
    # configured dev database name has to come from the raw environment,
    # the same value config.settings.dev (not .test) would resolve to.
    configured_dev_db_name = os.environ["POSTGRES_DB"]

    from django.db import connection

    actual_test_db_name = connection.settings_dict["NAME"]

    assert actual_test_db_name != configured_dev_db_name
    assert configured_dev_db_name in actual_test_db_name or actual_test_db_name.startswith("test_")


@pytest.mark.django_db
def test_writing_a_user_during_the_test_run_does_not_touch_the_dev_database():
    from apps.accounts.factories import UserFactory

    dev_count_before = _dev_user_count()

    UserFactory()
    UserFactory()

    dev_count_after = _dev_user_count()

    assert dev_count_after == dev_count_before
