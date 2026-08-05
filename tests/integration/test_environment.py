"""
Proves the Django app's own configuration (not the bounded health probes in
apps.health.checks) actually reaches both PostgreSQL and Redis, per FR-001/
FR-002 and Story 1's "the whole system runs locally" acceptance criteria.
"""
import pytest
import redis
from django.conf import settings
from django.db import connections

pytestmark = pytest.mark.django_db


def test_django_reaches_the_configured_database():
    conn = connections["default"]
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()

    assert result == (1,)


def test_django_reaches_the_configured_cache():
    client = redis.from_url(settings.REDIS_URL)

    assert client.ping() is True
