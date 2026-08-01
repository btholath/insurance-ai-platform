from .base import *  # noqa: F401,F403

# Password hashing dominates runtime in a suite that creates users heavily.
# MD5 is intentionally weak — this settings module is never used outside tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
