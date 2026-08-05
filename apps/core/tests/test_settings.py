"""
FR-005: a missing required setting must abort startup, naming the setting,
rather than starting partially or failing later with an unrelated error.

The check in config/settings/base.py runs at *module import time*, so it
can't be exercised via override_settings() (settings have already been
imported and validated once for the whole test process). A real subprocess
with a stripped environment is the only way to re-trigger it.

Setting the target var to "" (rather than deleting it) matters: base.py
calls environ.Env.read_env(BASE_DIR / ".env"), and that call does not
overwrite a key already present in os.environ, even an empty one — but it
WOULD fill in a genuinely absent key from the .env file baked into this
image, silently defeating the test.
"""
import subprocess
import sys

import pytest

REQUIRED_ENV_VARS = [
    "SECRET_KEY",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "REDIS_URL",
]


def _run_check_with_missing(var_name, base_env):
    env = dict(base_env)
    env[var_name] = ""

    return subprocess.run(
        [sys.executable, "manage.py", "check", "--settings=config.settings.test"],
        env=env,
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=30,
    )


@pytest.fixture
def base_env():
    import os

    return dict(os.environ)


@pytest.mark.parametrize("var_name", REQUIRED_ENV_VARS)
def test_missing_required_setting_raises_improperly_configured_naming_it(var_name, base_env):
    result = _run_check_with_missing(var_name, base_env)

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert var_name in result.stderr


def test_missing_multiple_settings_names_all_of_them_at_once():
    import os

    env = dict(os.environ)
    env["SECRET_KEY"] = ""
    env["REDIS_URL"] = ""

    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--settings=config.settings.test"],
        env=env,
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=30,
    )

    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr
    assert "REDIS_URL" in result.stderr


def test_all_settings_present_check_passes(base_env):
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--settings=config.settings.test"],
        env=base_env,
        capture_output=True,
        text=True,
        cwd="/app",
        timeout=30,
    )

    assert result.returncode == 0
    assert "ImproperlyConfigured" not in result.stderr
