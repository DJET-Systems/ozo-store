"""Idempotent command to apply least-privilege PostgreSQL grants."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection

_APPEND_ONLY_TABLES = frozenset({"inventory_stock_movement", "stock_movement", "core_audit_log"})


class Command(BaseCommand):
    """Apply least-privilege grants to djet_app and djet_ro roles when present."""

    help = "Apply idempotent PostgreSQL role grants for djet_app and djet_ro."

    def handle(self, *args: Any, **options: Any) -> None:
        """Grant runtime privileges on existing tables and sequences."""
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("Skipping grants: non-PostgreSQL backend."))
            return

        with connection.cursor() as cursor:
            cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('djet_app', 'djet_ro')")
            present_roles = {row[0] for row in cursor.fetchall()}

            if "djet_app" in present_roles:
                cursor.execute("GRANT USAGE ON SCHEMA public TO djet_app")
                cursor.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON ALL TABLES IN SCHEMA public TO djet_app"
                )
                cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO djet_app")
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                existing_tables = {row[0] for row in cursor.fetchall()}
                for table in sorted(_APPEND_ONLY_TABLES & existing_tables):
                    quoted = connection.ops.quote_name(table)
                    cursor.execute(
                        f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {quoted} FROM djet_app"
                    )
                self.stdout.write(self.style.SUCCESS("Applied grants for role djet_app."))
            else:
                self.stdout.write("Role djet_app not present; skipping.")

            if "djet_ro" in present_roles:
                cursor.execute("GRANT USAGE ON SCHEMA public TO djet_ro")
                cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO djet_ro")
                self.stdout.write(self.style.SUCCESS("Applied grants for role djet_ro."))
            else:
                self.stdout.write("Role djet_ro not present; skipping.")
