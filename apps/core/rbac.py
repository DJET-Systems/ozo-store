"""Role-Based Access Control (RBAC) registry, permissions, and authorization helpers."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.urls import reverse

P = ParamSpec("P")
R = TypeVar("R")

# Explicit permission strings (007 §3)
PERMISSIONS: dict[str, str] = {
    # Orders
    "orders.view": "View orders and fulfillment status",
    "orders.create": "Create draft and manual orders",
    "orders.cancel": "Cancel orders and release stock",
    "orders.edit": "Edit order items and shipping details",
    # Catalog
    "catalog.view": "View products, variants, and categories",
    "catalog.edit": "Create, edit, or archive products and variants",
    "catalog.edit_price": "Change product retail prices and discounts",
    # Inventory
    "inventory.view": "View stock levels and locations",
    "inventory.adjust": "Adjust stock balances and write off damages",
    "inventory.count": "Conduct physical count sessions",
    "inventory.transfer": "Transfer stock between locations",
    # Purchasing
    "purchasing.view": "View suppliers and purchase orders",
    "purchasing.create": "Create draft purchase orders",
    "purchasing.approve": "Approve purchase orders for goods receipt",
    # Reports & Finance (Sensitive fields)
    "reports.view": "View sales, orders, and operational reports",
    "reports.view_costs": "View purchase costs, supplier costs, and margins",
    # Settings & Staff (Sensitive administration)
    "settings.view": "View store settings and configuration",
    "settings.edit": "Modify store settings, payment gateways, and policies",
    "staff.view": "View staff member list and roles",
    "staff.manage": "Invite, edit, or deactivate staff members and assign roles",
    "audit.view": "View append-only audit trail logs",
    "data.export": "Export customers, orders, inventory, or audit data to CSV",
}

# Built-in role definitions (007 §3)
BUILTIN_ROLES: dict[str, dict[str, Any]] = {
    "Owner": {
        "description": "Full access to all operations, staff management, settings, and exports.",
        "permissions": ["*"],
    },
    "Manager": {
        "description": "Operational lead managing orders, catalog, stock, and costs.",
        "permissions": [
            "orders.view",
            "orders.create",
            "orders.cancel",
            "orders.edit",
            "catalog.view",
            "catalog.edit",
            "catalog.edit_price",
            "inventory.view",
            "inventory.adjust",
            "inventory.count",
            "inventory.transfer",
            "purchasing.view",
            "purchasing.create",
            "purchasing.approve",
            "reports.view",
            "reports.view_costs",
            "settings.view",
            "staff.view",
            "audit.view",
        ],
    },
    "Cashier": {
        "description": "Front-desk sales: create and view orders, no costs or margins.",
        "permissions": [
            "orders.view",
            "orders.create",
            "catalog.view",
            "inventory.view",
        ],
    },
    "Warehouse": {
        "description": "Stock handling: pick/pack, receive, count, transfer; no price edits.",
        "permissions": [
            "orders.view",
            "inventory.view",
            "inventory.adjust",
            "inventory.count",
            "inventory.transfer",
        ],
    },
    "Accountant": {
        "description": "Finance: read orders, payouts, costs, reconciliations, and data exports.",
        "permissions": [
            "orders.view",
            "reports.view",
            "reports.view_costs",
            "data.export",
            "audit.view",
        ],
    },
    "Support": {
        "description": "Customer care: view orders, initiate customer returns.",
        "permissions": [
            "orders.view",
            "orders.edit",
        ],
    },
}


def sync_builtin_roles() -> None:
    """Idempotently seed or update built-in roles without overwriting merchant modifications."""
    from apps.core.models import Role

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
        elif not role.modified_by_merchant:
            # Re-apply updated built-in definitions if merchant hasn't customized it
            role.description = config["description"]
            role.permissions = config["permissions"]
            role.is_builtin = True
            role.save(update_fields=["description", "permissions", "is_builtin"])


def user_has_permission(user: Any, perm: str) -> bool:
    """Check whether a user possesses a given permission string."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_active", False) or not getattr(user, "is_staff", False):
        return False

    role = getattr(user, "role", None)
    if not role:
        return False

    role_perms: list[str] = getattr(role, "permissions", [])
    if "*" in role_perms:
        return True
    return perm in role_perms


def authorize(actor: Any, perm: str) -> None:
    """Service-level authorization guard (deny by default)."""
    if not user_has_permission(actor, perm):
        actor_name = getattr(actor, "username", "Anonymous")
        raise PermissionDenied(f"Actor '{actor_name}' lacks required permission '{perm}'.")


def check_cost_visibility(user: Any) -> bool:
    """Check whether costs, margins, and supplier purchase prices are visible to the user."""
    return user_has_permission(user, "reports.view_costs")


def requires_permission(
    perm: str,
) -> Callable[[Callable[P, HttpResponseBase]], Callable[P, HttpResponseBase]]:
    """View decorator enforcing staff authentication, 2FA compliance, and required permission."""

    def decorator(view_func: Callable[P, HttpResponseBase]) -> Callable[P, HttpResponseBase]:
        @wraps(view_func)
        def _wrapped_view(*args: P.args, **kwargs: P.kwargs) -> HttpResponseBase:
            # First argument of a view is always HttpRequest
            request: HttpRequest = args[0]  # type: ignore[assignment]
            user = getattr(request, "user", None)

            if not user or not user.is_authenticated or not getattr(user, "is_staff", False):
                login_url = reverse("dashboard-login")
                return redirect(f"{login_url}?next={request.path}")

            # Enforce 2FA for Owner and Manager roles before dashboard access
            if getattr(user, "requires_2fa_enforcement", lambda: False)():
                setup_url = reverse("dashboard-2fa-setup")
                if request.path != setup_url and not request.path.startswith("/auth/"):
                    return redirect(setup_url)

            if not user_has_permission(user, perm):
                raise PermissionDenied(f"Access denied: missing '{perm}' permission.")

            return view_func(*args, **kwargs)

        return _wrapped_view

    return decorator
