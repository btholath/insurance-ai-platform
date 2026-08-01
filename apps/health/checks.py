"""
Bounded-timeout probes for the health endpoint (FR-026, FR-027, research.md §8).

Both functions catch every exception and return "error" rather than raising
— an unhandled exception here would surface as a 500, which FR-027
explicitly forbids ("a distinct machine-detectable outcome rather than an
unhandled error").
"""
import redis
from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

PROBE_TIMEOUT_SECONDS = 2


def check_database():
    try:
        conn = connections["default"]
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except OperationalError:
        return "error"
    except Exception:
        return "error"


def check_cache():
    try:
        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
            socket_timeout=PROBE_TIMEOUT_SECONDS,
        )
        if client.ping():
            return "ok"
        return "error"
    except Exception:
        return "error"
