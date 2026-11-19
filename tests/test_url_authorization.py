"""Tests for URL authorization and anonymous/underprivileged request rejection across dashboard."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Role, StaffUser
from apps.core.rbac import sync_builtin_roles

DASHBOARD_ROUTES = [
    ("dashboard-today", {}, "orders.view"),
    ("dashboard-orders", {}, "orders.view"),
    ("dashboard-products", {}, "catalog.view"),
    ("dashboard-inventory", {}, "inventory.view"),
    ("dashboard-purchasing", {}, "purchasing.view"),
    ("dashboard-reports", {}, "reports.view"),
    ("dashboard-settings", {}, "settings.view"),
    ("dashboard-staff", {}, "staff.view"),
    ("dashboard-roles", {}, "staff.view"),
    ("dashboard-audit", {}, "audit.view"),
    ("dashboard-export", {"dataset": "catalog"}, "data.export"),
    ("dashboard-support", {}, "orders.view"),
]


@pytest.fixture(autouse=True)
def setup_roles_and_urls(db: None, settings: Any) -> None:
    settings.ROOT_URLCONF = "config.urls_dashboard"
    sync_builtin_roles()


@pytest.mark.django_db
@pytest.mark.parametrize("route_name,kwargs,_perm", DASHBOARD_ROUTES)
def test_anonymous_requests_are_redirected_to_login(
    route_name: str, kwargs: dict[str, Any], _perm: str
) -> None:
    """Every dashboard route requires staff authentication and redirects anonymous users."""
    url = reverse(route_name, kwargs=kwargs)
    client = Client()
    resp = client.get(url)

    assert resp.status_code == 302
    resp_url = getattr(resp, "url", "")
    assert resp_url.startswith(reverse("dashboard-login"))
    assert f"next={url}" in resp_url


@pytest.mark.django_db
def test_underprivileged_staff_cannot_access_sensitive_routes() -> None:
    """Cashier lacks 'staff.view', 'reports.view', 'settings.view', and 'data.export'."""
    cashier_role = Role.objects.get(name="Cashier")
    cashier = StaffUser.objects.create_user(
        username="basic_cashier",
        email="cashier@example.com",
        password="ValidPassword123!",
        role=cashier_role,
        is_staff=True,
    )

    client = Client()
    client.force_login(cashier)

    # Allowed routes for Cashier
    assert client.get(reverse("dashboard-today")).status_code == 200
    assert client.get(reverse("dashboard-orders")).status_code == 200
    assert client.get(reverse("dashboard-products")).status_code == 200
    assert client.get(reverse("dashboard-inventory")).status_code == 200

    # Denied routes for Cashier (must raise 403 Forbidden)
    assert client.get(reverse("dashboard-staff")).status_code == 403
    assert client.get(reverse("dashboard-reports")).status_code == 403
    assert client.get(reverse("dashboard-settings")).status_code == 403
    assert client.get(reverse("dashboard-audit")).status_code == 403
    assert client.get(reverse("dashboard-export", kwargs={"dataset": "catalog"})).status_code == 403


@pytest.mark.django_db
def test_privileged_owner_can_access_all_routes() -> None:
    """Owner with 2FA enabled has access to every operational dashboard endpoint."""
    owner_role = Role.objects.get(name="Owner")
    owner = StaffUser.objects.create_user(
        username="super_owner",
        email="owner@example.com",
        password="ValidPassword123!",
        role=owner_role,
        is_staff=True,
        totp_enabled=True,
    )

    client = Client()
    client.force_login(owner)

    for route_name, kwargs, _ in DASHBOARD_ROUTES:
        url = reverse(route_name, kwargs=kwargs)
        resp = client.get(url)
        assert resp.status_code == 200, f"Owner should have access to {url}"
