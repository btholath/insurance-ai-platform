import time
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.django_db

URL = "/health/"


def test_returns_200_and_healthy_body_when_both_dependencies_ok(api_client):
    response = api_client.get(URL)

    assert response.status_code == 200
    assert response.data == {
        "status": "healthy",
        "checks": {
            "database": {"status": "ok"},
            "cache": {"status": "ok"},
        },
    }


def test_returns_503_identifying_database_failure_while_cache_stays_ok(api_client):
    with patch("apps.health.views.check_database", return_value="error"):
        response = api_client.get(URL)

    assert response.status_code == 503
    assert response.data == {
        "status": "unhealthy",
        "checks": {
            "database": {"status": "error"},
            "cache": {"status": "ok"},
        },
    }


def test_returns_503_identifying_cache_failure_while_database_stays_ok(api_client):
    with patch("apps.health.views.check_cache", return_value="error"):
        response = api_client.get(URL)

    assert response.status_code == 503
    assert response.data == {
        "status": "unhealthy",
        "checks": {
            "database": {"status": "ok"},
            "cache": {"status": "error"},
        },
    }


def test_returns_503_when_both_dependencies_fail(api_client):
    with patch("apps.health.views.check_database", return_value="error"), patch(
        "apps.health.views.check_cache", return_value="error"
    ):
        response = api_client.get(URL)

    assert response.status_code == 503
    assert response.data == {
        "status": "unhealthy",
        "checks": {
            "database": {"status": "error"},
            "cache": {"status": "error"},
        },
    }


def test_response_body_contains_only_documented_keys_no_disclosure(api_client):
    response = api_client.get(URL)

    assert set(response.data.keys()) == {"status", "checks"}
    assert set(response.data["checks"].keys()) == {"database", "cache"}
    assert set(response.data["checks"]["database"].keys()) == {"status"}
    assert set(response.data["checks"]["cache"].keys()) == {"status"}

    body_text = str(response.data).lower()
    forbidden_substrings = [
        "host", "port", "password", "secret", "traceback", "exception",
        "django", "python", "postgres", "redis", "5432", "6379",
    ]
    for substring in forbidden_substrings:
        assert substring not in body_text, f"disclosed forbidden substring: {substring}"


def test_no_authentication_required(api_client):
    response = api_client.get(URL)

    assert response.status_code in (200, 503)


def test_response_returns_within_bounded_time_when_a_dependency_is_unresponsive(api_client):
    # Each probe carries its own 2-second connect/socket timeout (checks.py) —
    # the view relies on that bound composing into SC-006's overall 5-second
    # budget, rather than imposing an external hard-kill on an arbitrary
    # blocking call. Pointing the DB probe at a real unroutable host (instead
    # of mocking the probe to ignore its own timeout) exercises that actual
    # documented guarantee end-to-end.
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
        response = api_client.get(URL)
        elapsed = time.monotonic() - start

    assert elapsed < 5
    assert response.status_code == 503
    assert response.data["checks"]["database"]["status"] == "error"
