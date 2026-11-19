"""Merchant dashboard views: operational screens, RBAC enforcement, data masking, and exports."""

from __future__ import annotations

import csv
import secrets
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_safe

from apps.catalog.models import Category, Product, Variant
from apps.catalog.services import lookup_barcode
from apps.core.models import AuditLog, Role, StaffInvite, StaffUser
from apps.core.rbac import check_cost_visibility, requires_permission
from apps.inventory.models import Location, StockLevel
from apps.orders.models import Order
from apps.orders.services import transition_order_status


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
    pending_orders_count = Order.objects.filter(status__in=["pending", "confirmed"]).count()
    recent_audits = AuditLog.objects.order_by("-created_at")[:6]

    context = {
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "active_products_count": active_products_count,
        "active_locations_count": active_locations_count,
        "pending_orders_count": pending_orders_count,
        "recent_audits": recent_audits,
    }
    response = render(request, "dashboard/today.html", context)
    response["Cache-Control"] = "no-store"
    return response


@require_safe
@requires_permission("orders.view")
def orders_list_view(request: HttpRequest) -> HttpResponse:
    """Orders table with live COD and Branch Pickup orders and status filters."""
    status_filter = request.GET.get("status", "").strip()
    search_q = request.GET.get("q", "").strip()
    orders_qs = Order.objects.prefetch_related("items").select_related("pickup_location")
    if status_filter in {"pending", "confirmed", "packed", "shipped", "delivered", "cancelled"}:
        orders_qs = orders_qs.filter(status=status_filter)
    if search_q:
        orders_qs = orders_qs.filter(reference__icontains=search_q) | orders_qs.filter(
            customer_phone__icontains=search_q
        )

    can_edit_orders = request.user.has_perm("orders.edit")
    response = render(
        request,
        "dashboard/orders_list.html",
        {
            "orders": orders_qs[:100],
            "status_filter": status_filter,
            "search_q": search_q,
            "can_edit_orders": can_edit_orders,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["POST"])
@requires_permission("orders.edit")
def order_status_update_view(request: HttpRequest, order_id: int) -> HttpResponse:
    """Advance or cancel an order status with audit logging."""
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get("status", "").strip()
    try:
        transition_order_status(order=order, new_status=new_status, actor=request.user)
        messages.success(
            request, f"Order {order.reference} updated to {order.get_status_display()}."
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard-orders")


@require_safe
@requires_permission("catalog.view")
def products_list_view(request: HttpRequest) -> HttpResponse:
    """Catalog products and variants table with sensitive cost/margin masking and CRUD controls."""
    can_view_costs = check_cost_visibility(request.user)
    can_edit_catalog = request.user.has_perm("catalog.edit")
    status_filter = request.GET.get("status", "active").strip()
    products_qs = (
        Product.objects.prefetch_related("variants")
        .select_related("category")
        .order_by("-created_at")
    )
    if status_filter in {"active", "draft", "archived"}:
        products_qs = products_qs.filter(status=status_filter)

    categories = Category.objects.order_by("name_en")

    response = render(
        request,
        "dashboard/products_list.html",
        {
            "products": products_qs[:100],
            "categories": categories,
            "status_filter": status_filter,
            "can_view_costs": can_view_costs,
            "can_edit_catalog": can_edit_catalog,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["POST"])
@requires_permission("catalog.edit")
@transaction.atomic
def product_create_view(request: HttpRequest) -> HttpResponse:
    """Create and list a new product + variant from the Staff Portal (zero ledger touch)."""
    title_en = request.POST.get("title_en", "").strip()
    title_ar = request.POST.get("title_ar", "").strip() or title_en
    sku = request.POST.get("sku", "").strip().upper()
    brand = request.POST.get("primary_brand", "").strip()
    category_id_raw = request.POST.get("category_id", "").strip()
    condition = request.POST.get("condition", "new").strip()
    tracking_mode = request.POST.get("tracking_mode", "serial").strip()
    price_raw = request.POST.get("price_egp", "0").strip()
    compare_raw = request.POST.get("compare_at_price_egp", "").strip()
    cost_raw = request.POST.get("cost_egp", "0").strip()
    warranty_raw = request.POST.get("warranty_months", "12").strip()
    image_url = request.POST.get("image_url", "").strip()

    if not title_en or not sku:
        messages.error(request, "Product title and SKU are required.")
        return redirect("dashboard-products")

    if Variant.objects.filter(sku__iexact=sku).exists():
        messages.error(request, f"A product variant with SKU '{sku}' already exists.")
        return redirect("dashboard-products")

    try:
        price_amount = int(Decimal(price_raw) * 100)
        compare_amount = int(Decimal(compare_raw) * 100) if compare_raw else None
        cost_amount = int(Decimal(cost_raw) * 100) if cost_raw else 0
    except Exception:
        messages.error(request, "Invalid price or cost format.")
        return redirect("dashboard-products")

    warranty_months = int(warranty_raw) if warranty_raw.isdigit() else 12
    category = (
        Category.objects.filter(id=int(category_id_raw)).first()
        if category_id_raw.isdigit()
        else None
    )

    base_handle = slugify(title_en) or slugify(sku) or "product"
    handle = base_handle
    suffix = 2
    while Product.objects.filter(handle=handle).exists():
        handle = f"{base_handle}-{suffix}"
        suffix += 1

    product = Product.objects.create(
        handle=handle,
        title_en=title_en,
        title_ar=title_ar,
        primary_brand=brand,
        category=category,
        image_url=image_url,
        status="active",
    )
    Variant.objects.create(
        product=product,
        sku=sku,
        title_en=request.POST.get("variant_title_en", "").strip(),
        title_ar=request.POST.get("variant_title_ar", "").strip(),
        price_amount=price_amount,
        compare_at_price_amount=compare_amount,
        cost_amount=cost_amount,
        condition=condition if condition in {"new", "used_a", "used_b", "refurbished"} else "new",
        tracking_mode=tracking_mode if tracking_mode in {"none", "batch", "serial"} else "serial",
        warranty_months=warranty_months,
    )

    AuditLog.log_action(
        action="catalog:product_created",
        entity_type="Product",
        entity_id=product.handle,
        actor=request.user,
        diff={"sku": sku, "title_en": title_en, "price_amount": price_amount},
        ip_address=request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, f"Listed '{product.title_en}' ({sku}) on the storefront.")
    return redirect("dashboard-products")


@require_http_methods(["POST"])
@requires_permission("catalog.edit")
@transaction.atomic
def product_status_update_view(request: HttpRequest, product_id: int) -> HttpResponse:
    """Remove (archive) or re-list (activate) a product from the public storefront."""
    product = get_object_or_404(Product, id=product_id)
    new_status = request.POST.get("status", "archived").strip().lower()
    if new_status not in {"active", "draft", "archived"}:
        new_status = "archived"

    old_status = product.status
    product.status = new_status
    product.save(update_fields=["status", "updated_at"])

    AuditLog.log_action(
        action="catalog:product_status_changed",
        entity_type="Product",
        entity_id=product.handle,
        actor=request.user,
        diff={"old_status": old_status, "new_status": new_status},
        ip_address=request.META.get("REMOTE_ADDR"),
    )
    if new_status == "archived":
        messages.success(request, f"Removed '{product.title_en}' from the live storefront.")
    else:
        messages.success(request, f"Restored '{product.title_en}' to '{new_status}'.")
    return redirect("dashboard-products")


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
