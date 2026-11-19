"""Automated test settings (uses real PostgreSQL)."""

from .dev import *  # noqa: F403
from .env import get_env, parse_database_url

DJET_ENV = "test"
DEBUG = False

SECRET_KEY = get_env(
    "DJANGO_SECRET_KEY",
    "test-only-secret-key-not-for-production-use-0123456789abcdef",
)

DATABASES = {
    "default": parse_database_url(
        get_env(
            "TEST_DATABASE_URL",
            get_env(
                "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/djet_store_test"
            ),
        )
    ),
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
