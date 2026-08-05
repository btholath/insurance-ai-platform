import time
from unittest.mock import patch

import pytest

from apps.health.checks import PROBE_TIMEOUT_SECONDS, check_cache, check_database

pytestmark = pytest.mark.django_db


def test_check_database_returns_ok_when_reachable():
    assert check_database() == "ok"


def test_check_database_returns_error_never_raises_when_unreachable():
    with patch("apps.health.checks.psycopg.connect") as mock_connect:
        mock_connect.side_effect = OSError("simulated unreachable database")

        result = check_database()

    assert result == "error"


def test_check_database_against_unroutable_host_returns_error_within_timeout():
    with patch("apps.health.checks.settings") as mock_settings:
        mock_settings.DATABASES = {
            "default": {
                "HOST": "10.255.255.1",
                "PORT": "5432",
                "NAME": "unreachable",
                "USER": "unreachable",
                "PASSWORD": "unreachable",
            }
        }

        start = time.monotonic()
        result = check_database()
        elapsed = time.monotonic() - start

    assert result == "error"
    assert elapsed < PROBE_TIMEOUT_SECONDS + 3


def test_check_cache_returns_ok_when_reachable():
    assert check_cache() == "ok"


def test_check_cache_returns_error_never_raises_when_unreachable():
    with patch("apps.health.checks.redis.from_url") as mock_from_url:
        mock_from_url.return_value.ping.side_effect = ConnectionError("simulated unreachable cache")

        result = check_cache()

    assert result == "error"


def test_check_cache_returns_error_when_ping_returns_falsy_without_raising():
    with patch("apps.health.checks.redis.from_url") as mock_from_url:
        mock_from_url.return_value.ping.return_value = False

        result = check_cache()

    assert result == "error"


def test_check_cache_against_unroutable_host_returns_error_within_timeout():
    with patch("apps.health.checks.settings") as mock_settings:
        mock_settings.REDIS_URL = "redis://10.255.255.1:6379/0"

        start = time.monotonic()
        result = check_cache()
        elapsed = time.monotonic() - start

    assert result == "error"
    assert elapsed < PROBE_TIMEOUT_SECONDS + 1
