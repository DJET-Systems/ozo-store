"""Base 12-factor Django settings shared across all surfaces and environments."""

from __future__ import annotations

import os
from pathlib import Path

from .env import get_env, parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DJET_ENV = get_env("DJET_ENV", "dev").lower()
DJET_SURFACE = get_env("DJET_SURFACE", "storefront").lower()
# Client brand overlay from apps/presets/brands/<code>.json.
# Defaults to "ozo" in the OZO Shop client repository; set DJET_BRAND_PROFILE="" to disable.
DJET_BRAND_PROFILE = get_env("DJET_BRAND_PROFILE", "ozo").strip().lower()

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "procrastinate.contrib.django",
    # DJET Store domain apps
    "apps.core",
    "apps.catalog",
    "apps.inventory",
    "apps.customers",
    "apps.orders",
    "apps.payments",
    "apps.shipping",
    "apps.purchasing",
    "apps.notifications",
    "apps.reports",
    "apps.storefront",
    "apps.dashboard",
    "apps.presets",
    "apps.addons",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls_storefront"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

_default_db_url = get_env(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/djet_store",
)
DATABASES = {
    "default": parse_database_url(_default_db_url),
}

_migration_db_url = os.environ.get("MIGRATION_DATABASE_URL", "")
if _migration_db_url:
    DATABASES["migrator"] = parse_database_url(_migration_db_url)

AUTH_USER_MODEL = "core.StaffUser"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar"
LANGUAGES = [
    ("ar", "العربية"),
    ("en", "English"),
]
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": (
                '{"ts":"%(asctime)s","level":"%(levelname)s",'
                '"logger":"%(name)s","msg":"%(message)s"}'
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": get_env("DJANGO_LOG_LEVEL", "INFO"),
    },
}
