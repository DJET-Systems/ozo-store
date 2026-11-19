"""Order creation, pricing calculation, and controlled status transition services."""

from __future__ import annotations

import secrets
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Variant
from apps.core.models import AuditLog
from apps.inventory.models import Location
from apps.orders.models import Order, OrderItem

# Fixed flat courier shipping fee in minor units (75.00 EGP = 7500 piastres); free for branch pickup
HOME_DELIVERY_FEE_MINOR = 7500

ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "packed", "cancelled"},
    "confirmed": {"packed", "shipped", "delivered", "cancelled"},
    "packed": {"shipped", "delivered", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


def generate_order_reference(prefix: str = "OZO") -> str:
    """Generate a collision-resistant human-readable order number e.g. OZO-2026-48291."""
    year = timezone.localdate().year
    for _ in range(10):
        token = f"{prefix}-{year}-{secrets.randbelow(90000) + 10000}"
        if not Order.objects.filter(reference=token).exists():
            return token
    return f"{prefix}-{year}-{secrets.token_hex(3).upper()}"


@transaction.atomic
def create_order_from_cart(
    *,
    cart: dict[str, int],
    customer_name: str,
    customer_phone: str,
    customer_email: str = "",
    fulfillment_method: str = "home_delivery",
    payment_method: str = "cod",
    pickup_location_id: int | None = None,
    governorate: str = "",
    city: str = "",
    address_line: str = "",
    notes: str = "",
) -> Order:
    """Validate cart lines, snapshot integer-piastre prices, and persist an Order."""
    if not cart:
        raise ValueError("Cannot place an order with an empty cart.")

    clean_name = customer_name.strip()
    clean_phone = "".join(ch for ch in customer_phone if ch.isdigit() or ch == "+")
    if not clean_name or len(clean_phone) < 8:
        raise ValueError("Customer name and a valid telephone number are required.")

    if fulfillment_method not in {"home_delivery", "branch_pickup"}:
        fulfillment_method = "home_delivery"

    if fulfillment_method == "branch_pickup":
        payment_method = "pay_at_branch"
        shipping_amount = 0
        pickup_location = (
            Location.objects.filter(id=pickup_location_id, is_active=True).first()
            if pickup_location_id
            else Location.objects.filter(is_active=True, is_public_branch=True)
            .order_by("priority")
            .first()
        )
    else:
        payment_method = "cod"
        shipping_amount = HOME_DELIVERY_FEE_MINOR
        pickup_location = None
        if not address_line.strip():
            raise ValueError("Delivery street address is required for Home Delivery (COD).")

    variants = list(
        Variant.objects.select_related("product").filter(
            sku__in=list(cart.keys()), product__status="active"
        )
    )
    if not variants:
        raise ValueError("None of the items in your cart are currently available.")

    subtotal_amount = 0
    line_payloads: list[dict[str, Any]] = []
    for variant in variants:
        qty = max(1, int(cart.get(variant.sku, 1)))
        line_total = variant.price_amount * qty
        subtotal_amount += line_total
        line_payloads.append(
            {
                "variant": variant,
                "sku": variant.sku,
                "title_en": f"{variant.product.title_en} ({variant.title_en})"
                if variant.title_en
                else variant.product.title_en,
                "title_ar": f"{variant.product.title_ar} ({variant.title_ar})"
                if variant.title_ar
                else variant.product.title_ar,
                "quantity": qty,
                "unit_price_amount": variant.price_amount,
                "line_total_amount": line_total,
            }
        )

    total_amount = subtotal_amount + shipping_amount
    order = Order.objects.create(
        reference=generate_order_reference("OZO"),
        customer_name=clean_name,
        customer_phone=clean_phone,
        customer_email=customer_email.strip(),
        fulfillment_method=fulfillment_method,
        payment_method=payment_method,
        status="pending",
        pickup_location=pickup_location,
        governorate=governorate.strip(),
        city=city.strip(),
        address_line=address_line.strip(),
        notes=notes.strip(),
        subtotal_amount=subtotal_amount,
        shipping_amount=shipping_amount,
        total_amount=total_amount,
    )

    for payload in line_payloads:
        OrderItem.objects.create(order=order, **payload)

    AuditLog.log_action(
        action="order:created",
        entity_type="Order",
        entity_id=order.reference,
        actor=clean_phone,
        diff={
            "fulfillment_method": fulfillment_method,
            "payment_method": payment_method,
            "total_amount": total_amount,
            "items_count": len(line_payloads),
        },
    )
    return order


@transaction.atomic
def transition_order_status(
    *,
    order: Order,
    new_status: str,
    actor: Any = None,
) -> Order:
    """Transition an order through the state machine and write an immutable audit entry."""
    old_status = order.status
    if new_status == old_status:
        return order

    allowed = ALLOWED_STATUS_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise ValueError(f"Cannot transition order from '{old_status}' to '{new_status}'.")

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])

    AuditLog.log_action(
        action="order:status_changed",
        entity_type="Order",
        entity_id=order.reference,
        actor=actor,
        diff={"old_status": old_status, "new_status": new_status},
    )
    return order
