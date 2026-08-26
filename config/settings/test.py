from .base import *  # noqa: F401,F403

# Password hashing dominates runtime in a suite that creates users heavily.
# MD5 is intentionally weak — this settings module is never used outside tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Runs Celery tasks synchronously in-process for the happy-path/idempotency
# suite — no worker or Redis needed. Retry/backoff/exhaustion tests override
# this per-test via Celery's own apply()/task_always_eager mechanics.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
