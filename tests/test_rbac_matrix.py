"""Role-Based Access Control (RBAC) matrix and service guard tests."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied

from apps.core.models import Role, StaffUser
from apps.core.rbac import (
    PERMISSIONS,
    authorize,
    check_cost_visibility,
    sync_builtin_roles,
    user_has_permission,
)


@pytest.fixture(autouse=True)
def seed_roles(db: None) -> None:
    sync_builtin_roles()


@pytest.mark.django_db
def test_all_permissions_registered_have_descriptions() -> None:
    """Every registered permission string has an explanatory label."""
    assert len(PERMISSIONS) >= 22
    for perm_key, desc in PERMISSIONS.items():
        assert "." in perm_key
        assert isinstance(desc, str) and len(desc) > 5


@pytest.mark.django_db
def test_sync_builtin_roles_idempotency_and_customization() -> None:
    """sync_builtin_roles creates all 6 built-in roles and respects merchant customization."""
    assert Role.objects.count() >= 6

    cashier_role = Role.objects.get(name="Cashier")
    assert "orders.view" in cashier_role.permissions
    assert "reports.view_costs" not in cashier_role.permissions
    assert cashier_role.is_builtin is True
    assert cashier_role.modified_by_merchant is False

    # Simulate merchant customizing the Cashier role
    cashier_role.permissions.append("reports.view")
    cashier_role.modified_by_merchant = True
    cashier_role.save()

    # Re-sync built-in roles
    sync_builtin_roles()
    cashier_role.refresh_from_db()
    assert "reports.view" in cashier_role.permissions  # Customization preserved!


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role_name,allowed_perms,forbidden_perms",
    [
        (
            "Owner",
            [
                "orders.view",
                "orders.cancel",
                "catalog.edit_price",
                "reports.view_costs",
                "staff.manage",
                "data.export",
            ],
            [],
        ),
        (
            "Manager",
            [
                "orders.view",
                "orders.cancel",
                "catalog.edit_price",
                "reports.view_costs",
                "inventory.adjust",
            ],
            ["staff.manage", "settings.edit", "data.export"],
        ),
        (
            "Cashier",
            ["orders.view", "orders.create", "catalog.view", "inventory.view"],
            [
                "orders.cancel",
                "catalog.edit_price",
                "reports.view_costs",
                "inventory.adjust",
                "data.export",
                "staff.manage",
            ],
        ),
        (
            "Warehouse",
            ["inventory.view", "inventory.adjust", "inventory.transfer", "orders.view"],
            ["catalog.edit_price", "reports.view_costs", "staff.manage", "data.export"],
        ),
        (
            "Accountant",
            ["orders.view", "reports.view", "reports.view_costs", "data.export", "audit.view"],
            ["inventory.adjust", "catalog.edit", "catalog.edit_price", "staff.manage"],
        ),
        (
            "Support",
            ["orders.view", "orders.edit"],
            [
                "inventory.adjust",
                "reports.view_costs",
                "catalog.edit_price",
                "data.export",
                "staff.manage",
            ],
        ),
    ],
)
def test_builtin_role_permission_matrix(
    role_name: str,
    allowed_perms: list[str],
    forbidden_perms: list[str],
) -> None:
    """Verify each built-in role against key actions (allowed vs forbidden)."""
    role = Role.objects.get(name=role_name)
    user = StaffUser.objects.create_user(
        username=f"user_{role_name.lower()}",
        email=f"{role_name.lower()}@example.com",
        password="ValidStaffPassword123!",
        role=role,
        is_staff=True,
    )

    for perm in allowed_perms:
        assert user_has_permission(user, perm) is True, f"{role_name} should have {perm}"
        assert user.has_perm(perm) is True
        # Service guard succeeds without raising
        authorize(user, perm)

    for perm in forbidden_perms:
        assert user_has_permission(user, perm) is False, f"{role_name} should NOT have {perm}"
        assert user.has_perm(perm) is False
        with pytest.raises(PermissionDenied):
            authorize(user, perm)


@pytest.mark.django_db
def test_deny_by_default_for_anonymous_or_inactive_users() -> None:
    """Unauthenticated or deactivated users are denied all permissions by default."""
    assert user_has_permission(None, "orders.view") is False
    with pytest.raises(PermissionDenied):
        authorize(None, "orders.view")

    role = Role.objects.get(name="Cashier")
    user = StaffUser.objects.create_user(
        username="inactive_cashier",
        email="inactive@example.com",
        password="ValidStaffPassword123!",
        role=role,
        is_staff=True,
        is_active=False,
    )
    assert user_has_permission(user, "orders.view") is False
    with pytest.raises(PermissionDenied):
        authorize(user, "orders.view")


@pytest.mark.django_db
def test_cost_visibility_helper() -> None:
    """check_cost_visibility correctly gates sensitive pricing and margins."""
    owner_role = Role.objects.get(name="Owner")
    cashier_role = Role.objects.get(name="Cashier")

    owner = StaffUser.objects.create_user(
        username="owner_user",
        email="owner@example.com",
        password="ValidStaffPassword123!",
        role=owner_role,
        is_staff=True,
    )
    cashier = StaffUser.objects.create_user(
        username="cashier_user",
        email="cashier@example.com",
        password="ValidStaffPassword123!",
        role=cashier_role,
        is_staff=True,
    )

    assert check_cost_visibility(owner) is True
    assert check_cost_visibility(cashier) is False
