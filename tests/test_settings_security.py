"""Tests for fail-closed environment parsing and production security checks."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.core.checks import check_prod_security_settings
from config.settings.env import get_bool, get_env, get_list, parse_database_url


def test_env_helpers_fail_closed() -> None:
    """Missing required env vars or invalid schemes raise ImproperlyConfigured."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ImproperlyConfigured):
            get_env("MISSING_SECRET", required=True)
        with pytest.raises(ImproperlyConfigured):
            get_list("MISSING_HOSTS", required=True)

    with (
        patch.dict(os.environ, {"BAD_BOOL": "maybe"}, clear=False),
        pytest.raises(ImproperlyConfigured),
    ):
        get_bool("BAD_BOOL")

    with pytest.raises(ImproperlyConfigured):
        parse_database_url("sqlite:///tmp/bad.db")


def test_prod_security_check_passes_with_hardened_settings() -> None:
    """Hardened production settings yield zero security check errors."""
    with override_settings(
        DJET_ENV="prod",
        DEBUG=False,
        SECRET_KEY="x" * 64,
        ALLOWED_HOSTS=["shop.example.com"],
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        DJET_SURFACE="dashboard",
        SESSION_COOKIE_NAME="__Host-djet_admin_sid",
        INSTALLED_APPS=["apps.core"],
    ):
        assert check_prod_security_settings() == []


def test_prod_security_check_rejects_insecure_flags() -> None:
    """Insecure prod flags emit distinct check errors."""
    with override_settings(
        DJET_ENV="prod",
        DEBUG=True,
        SECRET_KEY="dev-only-short",
        ALLOWED_HOSTS=["*"],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        DJET_SURFACE="dashboard",
        SESSION_COOKIE_NAME="sessionid",
        INSTALLED_APPS=["django.contrib.admin", "apps.core"],
    ):
        ids = {err.id for err in check_prod_security_settings()}

    assert ids == {
        "djet.E001",
        "djet.E002",
        "djet.E003",
        "djet.E004",
        "djet.E005",
        "djet.E006",
        "djet.E007",
    }
