"""Data migration to seed built-in roles (Owner, Manager, Cashier, Warehouse, Accountant, Support)."""

from typing import Any

from django.db import migrations

from apps.core.rbac import BUILTIN_ROLES


def seed_roles(apps: Any, schema_editor: Any) -> None:
    Role = apps.get_model("core", "Role")
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


def reverse_roles(apps: Any, schema_editor: Any) -> None:
    Role = apps.get_model("core", "Role")
    # Only remove builtins that have not been modified by merchant
    Role.objects.filter(name__in=list(BUILTIN_ROLES.keys()), modified_by_merchant=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_role_staffuser_failed_login_attempts_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=reverse_roles),
    ]
