"""Production settings — fails closed when required secrets or hosts are missing."""

from .base import *  # noqa: F403
from .env import get_bool, get_env, get_int, get_list, parse_database_url

DJET_ENV = "prod"
DEBUG = get_bool("DJANGO_DEBUG", False)

SECRET_KEY = get_env("DJANGO_SECRET_KEY", required=True)
ALLOWED_HOSTS = get_list("ALLOWED_HOSTS", required=True)

DATABASES = {
    "default": parse_database_url(get_env("DATABASE_URL", required=True)),
}
if _mig := get_env("MIGRATION_DATABASE_URL", ""):
    DATABASES["migrator"] = parse_database_url(_mig)

SESSION_COOKIE_SECURE = get_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = get_bool("CSRF_COOKIE_SECURE", True)
SECURE_SSL_REDIRECT = get_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = get_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = get_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = get_bool("SECURE_HSTS_PRELOAD", False)
