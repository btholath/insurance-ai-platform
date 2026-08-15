"""
Shared Django settings for the insurance-ai-platform project.

Required environment variables are validated at the bottom of this file:
any missing name raises ImproperlyConfigured naming every missing key at
once, at import time, per FR-005.
"""
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY", default=None)
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.health",
    "apps.customers",
    "apps.policies",
    "apps.claims",
]

# ClaimLoadAnomaly.policy is a ForeignKey(unique=True) rather than a
# OneToOneField, deliberately: the DB constraint is identical, but the
# plural reverse accessor stays a queryset, so relaxing the one-per-policy
# rule for a future export is a migration rather than an API change for
# every caller. See apps/claims/models.py.
SILENCED_SYSTEM_CHECKS = ["fields.W342"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default=None),
        "USER": env("POSTGRES_USER", default=None),
        "PASSWORD": env("POSTGRES_PASSWORD", default=None),
        "HOST": env("POSTGRES_HOST", default=None),
        "PORT": env("POSTGRES_PORT", default=None),
    }
}

REDIS_URL = env("REDIS_URL", default=None)

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Records permission refusals to the audit log (FR-030). Delegates the
    # response itself to DRF, so non-disclosure behaviour is unchanged.
    "EXCEPTION_HANDLER": "apps.core.exception_handlers.audited_exception_handler",
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Fail-fast required configuration check (FR-004, FR-005).
#
# Reading env("KEY") without a default already raises when a value is
# missing, but only one at a time and only when that key is first read
# (which can be at request time for a rarely-touched setting). This
# up-front pass instead names every missing required key at once, at
# settings-import time.
# ---------------------------------------------------------------------------
REQUIRED_SETTINGS = {
    "SECRET_KEY": SECRET_KEY,
    "POSTGRES_DB": DATABASES["default"]["NAME"],
    "POSTGRES_USER": DATABASES["default"]["USER"],
    "POSTGRES_PASSWORD": DATABASES["default"]["PASSWORD"],
    "POSTGRES_HOST": DATABASES["default"]["HOST"],
    "POSTGRES_PORT": DATABASES["default"]["PORT"],
    "REDIS_URL": REDIS_URL,
}

_missing = [name for name, value in REQUIRED_SETTINGS.items() if value in (None, "")]
if _missing:
    raise ImproperlyConfigured(
        "Missing required environment variable(s): " + ", ".join(sorted(_missing))
    )
