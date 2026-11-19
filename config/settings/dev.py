"""Local development settings."""

from .base import *  # noqa: F403
from .env import get_bool, get_env, get_list

DEBUG = True
DJET_ENV = "dev"

SECRET_KEY = get_env(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-secret-key-do-not-use-in-prod-0123456789",
)

ALLOWED_HOSTS = get_list(
    "ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "shop.djet.localhost", "admin.djet.localhost"],
)

SESSION_COOKIE_SECURE = get_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = get_bool("CSRF_COOKIE_SECURE", False)
