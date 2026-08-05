"""
Bounded-timeout probes for the health endpoint (FR-026, FR-027, research.md §8).

Both functions catch every exception and return "error" rather than raising
— an unhandled exception here would surface as a 500, which FR-027
explicitly forbids ("a distinct machine-detectable outcome rather than an
unhandled error").
"""
import psycopg
import redis
from django.conf import settings

PROBE_TIMEOUT_SECONDS = 2


def check_database():
    # A fresh, short-lived connection with its own connect_timeout — not
    # Django's pooled connections["default"], which has no timeout configured
    # and would hang indefinitely against a network-partitioned (rather than
    # simply refused) database, violating the 2-second-per-probe bound.
    db = settings.DATABASES["default"]
    try:
        with psycopg.connect(
            host=db["HOST"],
            port=db["PORT"],
            dbname=db["NAME"],
            user=db["USER"],
            password=db["PASSWORD"],
            connect_timeout=PROBE_TIMEOUT_SECONDS,
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return "ok"
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
