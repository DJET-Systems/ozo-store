"""Django startup security checks for production environments."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register

_INSECURE_SECRET_MARKERS = ("dev-only", "changeme", "insecure", "test-only")


@register(Tags.security)
def check_prod_security_settings(
    app_configs: Sequence[Any] | None = None,
    **kwargs: Any,
) -> list[CheckMessage]:
    """Fail closed when insecure settings are active in production."""
    if getattr(settings, "DJET_ENV", "dev") != "prod":
        return []

    errors: list[CheckMessage] = []

    if settings.DEBUG:
        errors.append(
            Error(
                "DEBUG must be False when DJET_ENV=prod.",
                id="djet.E001",
            )
        )

    secret_key = str(getattr(settings, "SECRET_KEY", ""))
    lower_key = secret_key.lower()
    if len(secret_key) < 32 or any(marker in lower_key for marker in _INSECURE_SECRET_MARKERS):
        errors.append(
            Error(
                "SECRET_KEY must be at least 32 characters and not a default/dev key in prod.",
                id="djet.E002",
            )
        )

    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
    if not allowed_hosts or "*" in allowed_hosts:
        errors.append(
            Error(
                "ALLOWED_HOSTS must be non-empty and must not contain '*' when DJET_ENV=prod.",
                id="djet.E003",
            )
        )

    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        errors.append(
            Error(
                "SESSION_COOKIE_SECURE must be True when DJET_ENV=prod.",
                id="djet.E004",
            )
        )

    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        errors.append(
            Error(
                "CSRF_COOKIE_SECURE must be True when DJET_ENV=prod.",
                id="djet.E005",
            )
        )

    if getattr(settings, "DJET_SURFACE", "") == "dashboard" and not str(
        getattr(settings, "SESSION_COOKIE_NAME", "")
    ).startswith("__Host-"):
        errors.append(
            Error(
                "Dashboard session cookie must use the __Host- prefix.",
                id="djet.E006",
            )
        )

    if "django.contrib.admin" in getattr(settings, "INSTALLED_APPS", []):
        errors.append(
            Error(
                "django.contrib.admin must not be enabled in production.",
                id="djet.E007",
            )
        )

    return errors
