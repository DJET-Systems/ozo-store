"""Typed environment variable and database URL parsing helpers."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

_UNSET = object()


def get_env(name: str, default: str | object = _UNSET, *, required: bool = False) -> str:
    """Read an environment variable and fail closed when required and missing."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        if required or default is _UNSET:
            raise ImproperlyConfigured(f"Missing required environment variable: {name}")
        return str(default)
    return raw


def get_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"Invalid boolean value for {name}: {raw!r}")


def get_int(name: str, default: int) -> int:
    """Parse an integer environment variable."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ImproperlyConfigured(f"Invalid integer value for {name}: {raw!r}") from exc


def get_list(
    name: str,
    default: list[str] | object = _UNSET,
    *,
    required: bool = False,
) -> list[str]:
    """Parse a comma-separated environment variable into a list of strings."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        if required or default is _UNSET:
            raise ImproperlyConfigured(f"Missing required list environment variable: {name}")
        return list(default) if isinstance(default, list) else []
    items = [part.strip() for part in raw.split(",") if part.strip()]
    if required and not items:
        raise ImproperlyConfigured(f"Environment variable {name} cannot be empty")
    return items


def parse_database_url(url: str) -> dict[str, Any]:
    """Parse a PostgreSQL connection URL into a Django DATABASES dict entry."""
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            f"Unsupported database scheme {parsed.scheme!r}; only PostgreSQL is supported."
        )
    db_name = unquote(parsed.path.lstrip("/"))
    if not db_name:
        raise ImproperlyConfigured("Database URL must include a database name.")

    options: dict[str, Any] = {}
    query = parse_qs(parsed.query)
    if sslmode := query.get("sslmode"):
        options["sslmode"] = sslmode[0]
    if connect_timeout := query.get("connect_timeout"):
        options["connect_timeout"] = int(connect_timeout[0])

    config: dict[str, Any] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "127.0.0.1",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": get_int("DB_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
    }
    if options:
        config["OPTIONS"] = options
    return config
