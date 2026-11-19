"""Storefront views: dynamic section engine, category catalog, cart, and warranty lookup."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from apps.catalog.models import Category, Product, Variant
from apps.core.models import StoreSettings
from apps.inventory.models import Location, SerialUnit
from apps.orders.models import Order
from apps.orders.services import HOME_DELIVERY_FEE_MINOR, create_order_from_cart
from apps.presets.services import get_effective_definition, normalize_preset_code


def get_storefront_context(request: HttpRequest) -> dict[str, Any]:
    """Compile shared storefront context including active preset tokens and session cart count."""
    settings = StoreSettings.get_settings()

    # Allow query parameter preview (e.g. ?preset=electronics or ?preset=food) for sales demos
    preview_code = request.GET.get("preset") or request.GET.get("preview_preset")
    active_code = preview_code if preview_code else settings.active_preset
    active_code = normalize_preset_code(active_code)

    preset_def = get_effective_definition(active_code)
    brand = preset_def.get("brand", {})
    cart = request.session.get("cart", {})
    cart_count = sum(int(qty) for qty in cart.values())

    founded = brand.get("founded_year")
    brand_years = timezone.localdate().year - int(founded) if founded else None

    # Staff-managed setting wins; the brand profile provides the launch default.
    whatsapp_number = "".join(
        ch for ch in (settings.whatsapp_number or brand.get("whatsapp", "")) if ch.isdigit()
    )

    return {
        "settings": settings,
        "preset": preset_def,
        "tokens": preset_def.get("tokens", {}),
        "card_flags": preset_def.get("card_flags", {}),
        "cart_count": cart_count,
        "active_preset_code": active_code,
        "brand": brand,
        "brand_code": preset_def.get("brand_code", ""),
        "brand_years": brand_years,
        "whatsapp_number": whatsapp_number,
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
    if context["whatsapp_number"]:
        message = f"Hello! I am inquiring about {product.title_en} ({product.handle})"
        whatsapp_link = f"https://wa.me/{context['whatsapp_number']}?text={quote(message)}"

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
    clean_phone = "".join(ch for ch in phone if ch.isdigit())

    matched_order: Order | None = None
    if order_ref and clean_phone:
        candidate = (
            Order.objects.prefetch_related("items").filter(reference__iexact=order_ref).first()
        )
        if candidate and clean_phone in "".join(
            ch for ch in candidate.customer_phone if ch.isdigit()
        ):
            matched_order = candidate

    context.update(
        {
            "order_ref": order_ref,
            "phone": phone,
            "matched_order": matched_order,
        }
    )
    return render(request, "storefront/order_track.html", context)


@require_http_methods(["GET", "POST"])
def checkout_view(request: HttpRequest) -> HttpResponse:
    """Checkout view supporting Cash on Delivery (COD) and Pick Up at Branch."""
    context = get_storefront_context(request)
    cart: dict[str, int] = request.session.get("cart", {})
    if not cart:
        messages.info(request, "Your cart is empty. Add items before checking out.")
        return redirect("storefront-cart")

    variants = list(
        Variant.objects.filter(sku__in=list(cart.keys()), product__status="active").select_related(
            "product"
        )
    )
    if not variants:
        request.session["cart"] = {}
        messages.error(request, "The items in your cart are no longer available.")
        return redirect("storefront-cart")

    items: list[dict[str, Any]] = []
    subtotal_amount = 0
    for v in variants:
        qty = max(1, int(cart.get(v.sku, 1)))
        line_total = v.price_amount * qty
        subtotal_amount += line_total
        items.append(
            {
                "variant": v,
                "quantity": qty,
                "line_total_formatted": f"{Decimal(line_total) / 100:.2f} EGP",
            }
        )

    branches = list(
        Location.objects.filter(is_active=True, is_public_branch=True).order_by("priority")
    )
    delivery_fee_egp = f"{Decimal(HOME_DELIVERY_FEE_MINOR) / 100:.2f} EGP"
    total_with_delivery_egp = f"{Decimal(subtotal_amount + HOME_DELIVERY_FEE_MINOR) / 100:.2f} EGP"
    subtotal_egp = f"{Decimal(subtotal_amount) / 100:.2f} EGP"

    if request.method == "POST":
        customer_name = request.POST.get("customer_name", "").strip()
        customer_phone = request.POST.get("customer_phone", "").strip()
        customer_email = request.POST.get("customer_email", "").strip()
        fulfillment_method = request.POST.get("fulfillment_method", "home_delivery").strip()
        payment_method = request.POST.get("payment_method", "cod").strip()
        governorate = request.POST.get("governorate", "Cairo").strip()
        city = request.POST.get("city", "Al-Moqattam").strip()
        address_line = request.POST.get("address_line", "").strip()
        notes = request.POST.get("notes", "").strip()
        pickup_loc_raw = request.POST.get("pickup_location_id", "").strip()
        pickup_location_id = int(pickup_loc_raw) if pickup_loc_raw.isdigit() else None

        try:
            order = create_order_from_cart(
                cart=cart,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=customer_email,
                fulfillment_method=fulfillment_method,
                payment_method=payment_method,
                pickup_location_id=pickup_location_id,
                governorate=governorate,
                city=city,
                address_line=address_line,
                notes=notes,
            )
            request.session["cart"] = {}
            request.session["last_order_ref"] = order.reference
            messages.success(
                request,
                f"Order {order.reference} placed! Thank you, {order.customer_name}.",
            )
            return redirect("storefront-order-confirmation", reference=order.reference)
        except ValueError as exc:
            messages.error(request, str(exc))

    context.update(
        {
            "cart_items": items,
            "subtotal_formatted": subtotal_egp,
            "delivery_fee_formatted": delivery_fee_egp,
            "total_with_delivery_formatted": total_with_delivery_egp,
            "branches": branches,
        }
    )
    return render(request, "storefront/checkout.html", context)


@require_safe
def order_confirmation_view(request: HttpRequest, reference: str) -> HttpResponse:
    """Order confirmation receipt page for COD and Branch Pickup orders."""
    context = get_storefront_context(request)
    order = get_object_or_404(
        Order.objects.prefetch_related("items").select_related("pickup_location"),
        reference=reference,
    )
    context["order"] = order
    return render(request, "storefront/order_confirmation.html", context)
