"""Tests verifying storefront and dashboard surface, cookie, and URL isolation."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from django.test import Client, override_settings


def test_storefront_and_dashboard_settings_isolate_cookies() -> None:
    """Dashboard uses __Host- session cookie, Strict SameSite, and session-backed CSRF."""
    with patch.dict(
        os.environ,
        {
            "DJET_ENV": "test",
            "STORE_DOMAIN": "shop.djet.localhost",
            "ADMIN_DOMAIN": "admin.djet.localhost",
        },
        clear=False,
    ):
        store_settings = importlib.import_module("config.settings.storefront")
        dash_settings = importlib.import_module("config.settings.dashboard")
        importlib.reload(store_settings)
        importlib.reload(dash_settings)

    assert store_settings.DJET_SURFACE == "storefront"
    assert store_settings.ROOT_URLCONF == "config.urls_storefront"
    assert store_settings.SESSION_COOKIE_NAME == "djet_store_sid"
    assert store_settings.SESSION_COOKIE_SAMESITE == "Lax"

    assert dash_settings.DJET_SURFACE == "dashboard"
    assert dash_settings.ROOT_URLCONF == "config.urls_dashboard"
    assert dash_settings.SESSION_COOKIE_NAME == "__Host-djet_admin_sid"
    assert dash_settings.SESSION_COOKIE_DOMAIN is None
    assert dash_settings.SESSION_COOKIE_PATH == "/"
    assert dash_settings.SESSION_COOKIE_SECURE is True
    assert dash_settings.SESSION_COOKIE_HTTPONLY is True
    assert dash_settings.SESSION_COOKIE_SAMESITE == "Strict"
    assert dash_settings.CSRF_USE_SESSIONS is True
    assert dash_settings.CSRF_TRUSTED_ORIGINS == ["https://admin.djet.localhost"]


@pytest.mark.django_db
def test_surface_cookie_names_on_live_requests() -> None:
    """Touching session on each surface issues its isolated cookie name and flags."""
    with override_settings(
        ROOT_URLCONF="config.urls_storefront",
        SESSION_COOKIE_NAME="djet_store_sid",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
    ):
        store_resp = Client().get("/?touch_session=1")
    assert store_resp.status_code == 200
    assert "djet_store_sid" in store_resp.cookies
    assert store_resp.cookies["djet_store_sid"]["httponly"] is True
    assert store_resp.cookies["djet_store_sid"]["samesite"] == "Lax"

    with override_settings(
        ROOT_URLCONF="config.urls_dashboard",
        SESSION_COOKIE_NAME="__Host-djet_admin_sid",
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_DOMAIN=None,
    ):
        dash_resp = Client().get("/?touch_session=1", secure=True)
    assert dash_resp.status_code == 200
    assert "__Host-djet_admin_sid" in dash_resp.cookies
    cookie = dash_resp.cookies["__Host-djet_admin_sid"]
    assert cookie["secure"] is True
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Strict"
    assert cookie["path"] == "/"


@pytest.mark.django_db
@pytest.mark.parametrize("urlconf", ["config.urls_storefront", "config.urls_dashboard"])
def test_builtin_django_admin_is_not_mounted(urlconf: str) -> None:
    """Built-in /admin is disabled on merchant surfaces."""
    with override_settings(ROOT_URLCONF=urlconf):
        resp = Client().get("/admin/")
    assert resp.status_code == 404
