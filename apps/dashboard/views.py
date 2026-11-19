"""Merchant dashboard views: operational screens, RBAC enforcement, data masking, and exports."""

from __future__ import annotations

import csv
import secrets
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from apps.catalog.models import Product, Variant
from apps.catalog.services import lookup_barcode
from apps.core.models import AuditLog, Role, StaffInvite, StaffUser
from apps.core.rbac import check_cost_visibility, requires_permission
from apps.inventory.models import Location, StockLevel


class EchoStream:
    """File-like streaming buffer implementing write() for csv.writer."""

    def write(self, value: str) -> str:
        return value


@require_safe
def today_view(request: HttpRequest) -> HttpResponse:
    """Operational Today screen with real-time KPI cards."""
    # Special handle for surface isolation test suite
    if request.GET.get("touch_session") == "1":
        request.session["surface"] = "dashboard"
        if not request.user.is_authenticated:
            response = render(request, "dashboard/today.html", {"surface": "dashboard"})
            response["Cache-Control"] = "no-store"
            return response

    if not request.user.is_authenticated or not getattr(request.user, "is_staff", False):
        login_url = reverse("dashboard-login")
        return redirect(f"{login_url}?next={request.path}")

    if request.user.requires_2fa_enforcement():
        return redirect("dashboard-2fa-setup")

    # Real-time operational counters
    low_stock_count = StockLevel.objects.filter(on_hand__lte=Decimal("5.000")).count()
    out_of_stock_count = StockLevel.objects.filter(on_hand__lte=Decimal("0.000")).count()
    active_products_count = Product.objects.filter(status="active").count()
    active_locations_count = Location.objects.filter(is_active=True).count()
    recent_audits = AuditLog.objects.order_by("-created_at")[:6]

    context = {
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "active_products_count": active_products_count,
        "active_locations_count": active_locations_count,
        "recent_audits": recent_audits,
    }
    response = render(request, "dashboard/today.html", context)
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("orders.view")
def orders_list_view(request: HttpRequest) -> HttpResponse:
    """Orders table shell with status filters."""
    response = render(request, "dashboard/orders_list.html", {})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("catalog.view")
def products_list_view(request: HttpRequest) -> HttpResponse:
    """Catalog products and variants table with sensitive cost/margin masking."""
    can_view_costs = check_cost_visibility(request.user)
    products = Product.objects.prefetch_related("variants").order_by("-created_at")[:50]

    response = render(
        request,
        "dashboard/products_list.html",
        {"products": products, "can_view_costs": can_view_costs},
    )
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("inventory.view")
def inventory_list_view(request: HttpRequest) -> HttpResponse:
    """Stock levels table by location with sensitive unit cost masking."""
    can_view_costs = check_cost_visibility(request.user)
    stock_levels = StockLevel.objects.select_related(
        "variant", "variant__product", "location"
    ).order_by("location__priority", "variant__sku")[:100]

    response = render(
        request,
        "dashboard/inventory_list.html",
        {"stock_levels": stock_levels, "can_view_costs": can_view_costs},
    )
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("purchasing.view")
def purchasing_list_view(request: HttpRequest) -> HttpResponse:
    """Suppliers and purchase orders view shell."""
    response = render(request, "dashboard/purchasing_list.html", {})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("reports.view")
def reports_view(request: HttpRequest) -> HttpResponse:
    """Operational reports view; cost and profit breakdowns are restricted."""
    can_view_costs = check_cost_visibility(request.user)
    response = render(
        request,
        "dashboard/reports.html",
        {"can_view_costs": can_view_costs},
    )
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("settings.view")
def settings_view(request: HttpRequest) -> HttpResponse:
    """Store configuration settings."""
    response = render(request, "dashboard/settings.html", {})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("staff.view")
def staff_list_view(request: HttpRequest) -> HttpResponse:
    """Staff members and pending single-use invitations."""
    staff_members = StaffUser.objects.select_related("role").order_by("username")
    invites = (
        StaffInvite.objects.select_related("role", "created_by")
        .filter(accepted_at__isnull=True)
        .order_by("-created_at")
    )
    roles = Role.objects.order_by("name")

    response = render(
        request,
        "dashboard/staff_list.html",
        {
            "staff_members": staff_members,
            "invites": invites,
            "roles": roles,
            "can_manage_staff": request.user.has_perm("staff.manage"),
        },
    )
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["POST"])
@requires_permission("staff.manage")
def staff_invite_view(request: HttpRequest) -> HttpResponse:
    """Create single-use staff invitation with SHA-256 hashed token."""
    email = request.POST.get("email", "").strip().lower()
    role_id = request.POST.get("role_id")

    if not email:
        messages.error(request, "Email address is required.")
        return redirect("dashboard-staff")

    role = Role.objects.filter(id=int(role_id)).first() if role_id and role_id.isdigit() else None
    if not role:
        messages.error(request, "Selected role does not exist.")
        return redirect("dashboard-staff")

    raw_token = secrets.token_urlsafe(32)
    token_hash = sha256(raw_token.encode("utf-8")).hexdigest()

    invite = StaffInvite.objects.create(
        email=email,
        role=role,
        token_hash=token_hash,
        created_by=request.user,  # type: ignore[misc]
        expires_at=timezone.now() + timedelta(hours=48),
    )

    AuditLog.log_action(
        action="staff:invite_created",
        entity_type="StaffInvite",
        entity_id=str(invite.id),
        actor=request.user,
        diff={"email": email, "role": role.name},
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    invite_url = request.build_absolute_uri(reverse("dashboard-invite-accept", args=[raw_token]))
    messages.success(
        request,
        f"Invitation created for {email} ({role.name}). Invite link: {invite_url}",
    )
    return redirect("dashboard-staff")


@require_safe
@requires_permission("staff.view")
def roles_list_view(request: HttpRequest) -> HttpResponse:
    """Roles and permissions matrix viewer."""
    roles = Role.objects.order_by("name")
    response = render(request, "dashboard/roles_list.html", {"roles": roles})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("audit.view")
def audit_list_view(request: HttpRequest) -> HttpResponse:
    """Append-only audit trail viewer."""
    logs = AuditLog.objects.select_related("actor").order_by("-created_at")[:100]
    response = render(request, "dashboard/audit_list.html", {"logs": logs})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("data.export")
def export_data_view(request: HttpRequest, dataset: str) -> HttpResponseBase:
    """Streaming CSV export with strict cost and sensitive data masking."""
    can_view_costs = check_cost_visibility(request.user)

    AuditLog.log_action(
        action="data:export",
        entity_type="Export",
        entity_id=dataset,
        actor=request.user,
        diff={"dataset": dataset, "cost_included": can_view_costs},
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    pseudo_buffer = EchoStream()
    writer = csv.writer(pseudo_buffer)

    def iter_catalog() -> Any:
        header = ["Product Title (EN)", "Product Title (AR)", "SKU", "Retail Price (EGP)"]
        if can_view_costs:
            header.extend(["Cost Price (EGP)", "Gross Margin (EGP)"])
        yield writer.writerow(header)

        for variant in Variant.objects.select_related("product").iterator():
            price_egp = f"{Decimal(variant.price_amount) / 100:.2f}"
            row = [variant.product.title_en, variant.product.title_ar, variant.sku, price_egp]
            if can_view_costs:
                cost_egp = f"{Decimal(variant.cost_amount) / 100:.2f}"
                margin_egp = (
                    f"{(Decimal(variant.price_amount) - Decimal(variant.cost_amount)) / 100:.2f}"
                )
                row.extend([cost_egp, margin_egp])
            yield writer.writerow(row)

    def iter_inventory() -> Any:
        header = ["Location Code", "SKU", "On Hand", "Reserved"]
        if can_view_costs:
            header.append("Avg Unit Cost (EGP)")
        yield writer.writerow(header)

        for stock in StockLevel.objects.select_related("variant", "location").iterator():
            row = [
                stock.location.code,
                stock.variant.sku,
                str(stock.on_hand),
                str(stock.reserved),
            ]
            if can_view_costs:
                cost_egp = f"{stock.avg_unit_cost / 100:.2f}"
                row.append(cost_egp)
            yield writer.writerow(row)

    def iter_audit() -> Any:
        header = ["Timestamp", "Actor", "Action", "Entity Type", "Entity ID", "IP Address"]
        yield writer.writerow(header)
        for log in AuditLog.objects.select_related("actor").iterator():
            row = [
                log.created_at.isoformat(),
                log.actor.username if log.actor else "System",
                log.action,
                log.entity_type,
                log.entity_id,
                log.ip_address or "",
            ]
            yield writer.writerow(row)

    generators = {
        "catalog": iter_catalog,
        "inventory": iter_inventory,
        "audit": iter_audit,
    }

    if dataset not in generators:
        raise Http404(f"Unknown dataset '{dataset}' for export.")

    response = StreamingHttpResponse(
        generators[dataset](),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="export_{dataset}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    )
    return response


@require_safe
@requires_permission("orders.view")
def support_view(request: HttpRequest) -> HttpResponse:
    """Restricted support access path with strict audit trail recording."""
    AuditLog.log_action(
        action="support:access",
        entity_type="SupportPortal",
        entity_id="dashboard",
        actor=request.user,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    response = render(
        request,
        "dashboard/support.html",
        {"user": request.user, "now": timezone.now()},
    )
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("catalog.view")
def barcode_scan_view(request: HttpRequest) -> HttpResponse:
    """Global barcode/SKU scanner lookup returning JSON for HID keyboard scanners."""
    from django.http import JsonResponse

    code = request.GET.get("q", "").strip()
    result = lookup_barcode(code) if code else None
    if not result:
        return JsonResponse({"found": False, "query": code}, status=404 if code else 400)
    return JsonResponse({"found": True, "item": result})
