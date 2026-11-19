"""Health and worker readiness endpoints."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@require_safe
def healthz(request: HttpRequest) -> JsonResponse:
    """Verify PostgreSQL connectivity and that all migrations are applied."""
    surface = str(getattr(settings, "DJET_SURFACE", "unknown"))
    payload: dict[str, Any] = {
        "status": "ok",
        "surface": surface,
        "database": "ok",
        "migrations": "ok",
    }
    status_code = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            payload["status"] = "unhealthy"
            payload["migrations"] = "pending"
            payload["pending_migrations"] = len(plan)
            status_code = 503
    except DatabaseError:
        logger.exception("Healthcheck database failure")
        payload["status"] = "unhealthy"
        payload["database"] = "error"
        payload["migrations"] = "unknown"
        status_code = 503

    response = JsonResponse(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def readyz(request: HttpRequest) -> JsonResponse:
    """Verify database and Procrastinate queue tables are ready for jobs."""
    surface = str(getattr(settings, "DJET_SURFACE", "unknown"))
    payload: dict[str, Any] = {
        "status": "ok",
        "surface": surface,
        "worker_ready": True,
    }
    status_code = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM procrastinate_jobs LIMIT 0")
    except DatabaseError:
        logger.exception("Readiness check failed on procrastinate_jobs")
        payload["status"] = "not_ready"
        payload["worker_ready"] = False
        status_code = 503

    response = JsonResponse(payload, status=status_code)
    response["Cache-Control"] = "no-store"
    return response
