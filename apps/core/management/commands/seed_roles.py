"""Management command to seed or verify built-in zero-trust RBAC roles."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.core.models import Role
from apps.core.rbac import BUILTIN_ROLES


class Command(BaseCommand):
    help = (
        "Seed or verify built-in RBAC roles (Owner, Manager, Cashier, "
        "Warehouse, Accountant, Support)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        created_count = 0
        existing_count = 0

        for role_name, config in BUILTIN_ROLES.items():
            role = Role.objects.filter(name=role_name).first()
            if not role:
                Role.objects.create(
                    name=role_name,
                    description=config["description"],
                    permissions=config["permissions"],
                    is_builtin=True,
                    modified_by_merchant=False,
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created role: {role_name}"))
            else:
                existing_count += 1

        msg = (
            f"RBAC roles verification complete. Created: {created_count}, "
            f"Existing: {existing_count}."
        )
        self.stdout.write(self.style.SUCCESS(msg))
