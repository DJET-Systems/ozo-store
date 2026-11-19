"""Storefront views: dynamic section engine, category catalog, cart, and warranty lookup."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_safe

from apps.catalog.models import Category, Product, Variant
from apps.core.models import StoreSettings
from apps.inventory.models import Location, SerialUnit
from apps.presets.services import get_preset_definition, normalize_preset_code


def get_storefront_context(request: HttpRequest) -> dict[str, Any]:
    """Compile shared storefront context including active preset tokens and session cart count."""
    settings = StoreSettings.get_settings()

    # Allow query parameter preview (e.g. ?preset=electronics or ?preset=food) for sales demos
    preview_code = request.GET.get("preset") or request.GET.get("preview_preset")
    active_code = preview_code if preview_code else settings.active_preset
    active_code = normalize_preset_code(active_code)

    preset_def = get_preset_definition(active_code)
    cart = request.session.get("cart", {})
    cart_count = sum(int(qty) for qty in cart.values())

    return {
        "settings": settings,
        "preset": preset_def,
        "tokens": preset_def.get("tokens", {}),
        "card_flags": preset_def.get("card_flags", {}),
        "cart_count": cart_count,
        "active_preset_code": active_code,
    }


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """Render dynamic storefront home according to the active vertical preset."""
    if request.GET.get("touch_session") == "1":
        request.session["surface"] = "storefront"

    context = get_storefront_context(request)
    sections = context["preset"].get("home_sections", [])

    categories = Category.objects.filter(parent__isnull=True).order_by("name_en")[:12]
    featured_products = (
        Product.objects.filter(status="active")
        .prefetch_related("variants")
        .order_by("-created_at")[:12]
    )
    branches = Location.objects.filter(is_active=True, is_public_branch=True).order_by("priority")

    context.update(
        {
            "sections": sections,
            "categories": categories,
            "products": featured_products,
            "branches": branches,
        }
    )

    return render(request, "storefront/home.html", context)


@require_safe
def category_view(request: HttpRequest, slug: str) -> HttpResponse:
    """Category products listing with sorting and polymorphic cards."""
    category = get_object_or_404(Category, slug=slug)
    context = get_storefront_context(request)

    # Include descendants
    cat_ids = [category.id, *list(category.children.values_list("id", flat=True))]
    products_qs = (
        Product.objects.filter(category_id__in=cat_ids, status="active")
        .prefetch_related("variants")
        .order_by("-created_at")
    )

    paginator = Paginator(products_qs, 16)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context.update(
        {
            "category": category,
            "products": page_obj,
            "page_obj": page_obj,
        }
    )
    return render(request, "storefront/category.html", context)


@require_safe
def product_detail_view(request: HttpRequest, handle: str) -> HttpResponse:
    """Product detail page with variant selection, stock check, installments, and delivery."""
    product = get_object_or_404(
        Product.objects.prefetch_related("variants"), handle=handle, status="active"
    )
    context = get_storefront_context(request)
    variants = list(product.variants.all())
    selected_variant = variants[0] if variants else None

    # Calculate installments estimate (e.g. 12 months)
    installment_egp: str | None = None
    if selected_variant and selected_variant.price_amount > 0:
        monthly = (Decimal(selected_variant.price_amount) / Decimal("100")) / Decimal("12")
        installment_egp = f"{monthly:.2f}"

    whatsapp_link = ""
    phone = context["settings"].whatsapp_number or "201000000000"
    whatsapp_link = (
        f"https://wa.me/{phone}?text="
        f"Hello! I am inquiring about {product.title_en} ({product.handle})"
    )

    context.update(
        {
            "product": product,
            "variants": variants,
            "selected_variant": selected_variant,
            "installment_egp": installment_egp,
            "whatsapp_link": whatsapp_link,
        }
    )
    return render(request, "storefront/product_detail.html", context)


@require_safe
def cart_view(request: HttpRequest) -> HttpResponse:
    """View shopping cart contents and calculated subtotals."""
    context = get_storefront_context(request)
    cart: dict[str, int] = request.session.get("cart", {})

    items: list[dict[str, Any]] = []
    total_amount = 0

    if cart:
        variants = Variant.objects.filter(sku__in=list(cart.keys())).select_related("product")
        for v in variants:
            qty = cart.get(v.sku, 1)
            line_total = v.price_amount * qty
            total_amount += line_total
            items.append(
                {
                    "variant": v,
                    "quantity": qty,
                    "line_total_formatted": f"{Decimal(line_total) / 100:.2f} EGP",
                }
            )

    context.update(
        {
            "cart_items": items,
            "cart_total_formatted": f"{Decimal(total_amount) / 100:.2f} EGP",
            "cart_is_empty": len(items) == 0,
        }
    )
    return render(request, "storefront/cart.html", context)


@require_http_methods(["POST"])
def cart_add_view(request: HttpRequest) -> HttpResponse:
    """Add SKU item to session-backed cart with zero-JS and HTMX compatibility."""
    sku = request.POST.get("sku", "").strip()
    qty_str = request.POST.get("quantity", "1").strip()

    try:
        qty = int(qty_str)
        if qty < 1:
            qty = 1
    except ValueError:
        qty = 1

    variant = Variant.objects.filter(sku=sku).first()
    if not variant:
        messages.error(request, "Selected product item does not exist.")
        return redirect("storefront-home")

    cart = request.session.get("cart", {})
    cart[sku] = cart.get(sku, 0) + qty
    request.session["cart"] = cart

    if request.headers.get("HX-Request"):
        cart_count = sum(int(q) for q in cart.values())
        return HttpResponse(
            f'<span class="djet-cart-count" id="cart-counter">{cart_count}</span>',
            content_type="text/html",
        )

    messages.success(request, f"Added {variant.title_en or variant.product.title_en} to your cart.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "storefront-cart"
    return redirect(next_url)


@require_http_methods(["POST"])
def cart_update_view(request: HttpRequest) -> HttpResponse:
    """Update SKU quantities or remove items from cart."""
    sku = request.POST.get("sku", "").strip()
    action = request.POST.get("action", "set")

    cart = request.session.get("cart", {})
    if sku in cart:
        if action == "remove":
            del cart[sku]
        elif action == "increase":
            cart[sku] += 1
        elif action == "decrease":
            cart[sku] -= 1
            if cart[sku] <= 0:
                del cart[sku]
        request.session["cart"] = cart

    return redirect("storefront-cart")


@require_safe
def warranty_check_view(request: HttpRequest) -> HttpResponse:
    """Public non-PII warranty status check by serial number or IMEI."""
    context = get_storefront_context(request)
    query = request.GET.get("serial", "").strip().upper()
    unit: SerialUnit | None = None
    not_found = False

    if query:
        unit = (
            SerialUnit.objects.select_related("variant", "variant__product")
            .filter(serial_number=query)
            .first()
        )
        if not unit:
            not_found = True

    context.update(
        {
            "query": query,
            "unit": unit,
            "not_found": not_found,
        }
    )
    return render(request, "storefront/warranty_check.html", context)


@require_safe
def order_track_view(request: HttpRequest) -> HttpResponse:
    """Public order lookup by order reference number and telephone number."""
    context = get_storefront_context(request)
    order_ref = request.GET.get("order_ref", "").strip()
    phone = request.GET.get("phone", "").strip()

    context.update(
        {
            "order_ref": order_ref,
            "phone": phone,
        }
    )
    return render(request, "storefront/order_track.html", context)
