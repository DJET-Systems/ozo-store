"""Tests for /healthz and /readyz endpoints across both surfaces."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("urlconf", "expected_surface"),
    [
        ("config.urls_storefront", "storefront"),
        ("config.urls_dashboard", "dashboard"),
    ],
)
def test_healthz_returns_200_with_structured_json(urlconf: str, expected_surface: str) -> None:
    """/healthz checks DB + migrations and reports surface name without caching."""
    with override_settings(ROOT_URLCONF=urlconf, DJET_SURFACE=expected_surface):
        client = Client()
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.json() == {
        "status": "ok",
        "surface": expected_surface,
        "database": "ok",
        "migrations": "ok",
    }


@pytest.mark.django_db
def test_healthz_returns_503_when_migrations_pending() -> None:
    """/healthz fails closed (503) if unapplied migrations exist."""
    with patch(
        "apps.core.views.MigrationExecutor.migration_plan",
        return_value=[("fake_migration", False)],
    ):
        response = Client().get("/healthz")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["migrations"] == "pending"
    assert data["pending_migrations"] == 1


@pytest.mark.django_db
def test_readyz_verifies_procrastinate_queue_tables() -> None:
    """/readyz confirms PostgreSQL and procrastinate_jobs are reachable."""
    response = Client().get("/readyz")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.json()["worker_ready"] is True
