"""Orders, checkout, fulfillment, and line-item snapshot models."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.catalog.models import Variant
from apps.core.models import TimeStampedModel
from apps.core.money import Money
from apps.inventory.models import Location


class Order(TimeStampedModel):
    """Customer order supporting Cash on Delivery (COD) and In-Branch Pickup."""

    FULFILLMENT_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("home_delivery", "Home Delivery (Courier)"),
        ("branch_pickup", "Pick Up at Branch (Mokattam Showroom)"),
    )

    PAYMENT_METHOD_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("cod", "Cash on Delivery (COD)"),
        ("pay_at_branch", "Pay at Branch on Pickup (Cash / POS / Installments)"),
    )

    STATUS_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("pending", "Pending Confirmation"),
        ("confirmed", "Confirmed"),
        ("packed", "Packed / Ready for Pickup"),
        ("shipped", "Shipped / With Courier"),
        ("delivered", "Delivered / Completed"),
        ("cancelled", "Cancelled"),
    )

    reference = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Public order reference number (e.g. OZO-2026-84192)",
    )
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=32, db_index=True)
    customer_email = models.EmailField(blank=True)

    fulfillment_method = models.CharField(
        max_length=32,
        choices=FULFILLMENT_CHOICES,
        default="home_delivery",
    )
    payment_method = models.CharField(
        max_length=32,
        choices=PAYMENT_METHOD_CHOICES,
        default="cod",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    pickup_location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pickup_orders",
    )
    governorate = models.CharField(max_length=128, blank=True)
    city = models.CharField(max_length=128, blank=True)
    address_line = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Monetary fields stored strictly in integer minor units (piastres, 1 EGP = 100 piastres)
    subtotal_amount = models.BigIntegerField(default=0)
    shipping_amount = models.BigIntegerField(default=0)
    total_amount = models.BigIntegerField(default=0)

    class Meta:
        db_table = "orders_order"
        ordering: ClassVar[list[str]] = ["-created_at"]
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self) -> str:
        return f"{self.reference} ({self.customer_name})"

    @property
    def subtotal(self) -> Money:
        return Money.from_minor(self.subtotal_amount, "EGP")

    @property
    def shipping_fee(self) -> Money:
        return Money.from_minor(self.shipping_amount, "EGP")

    @property
    def total(self) -> Money:
        return Money.from_minor(self.total_amount, "EGP")


class OrderItem(TimeStampedModel):
    """Immutable line-item snapshot captured at order placement time."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        Variant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )
    sku = models.CharField(max_length=128)
    title_en = models.CharField(max_length=255)
    title_ar = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_amount = models.BigIntegerField(default=0)
    line_total_amount = models.BigIntegerField(default=0)

    class Meta:
        db_table = "orders_order_item"
        verbose_name = "Order item"
        verbose_name_plural = "Order items"

    def __str__(self) -> str:
        return f"{self.sku} x {self.quantity} ({self.order.reference})"

    @property
    def unit_price(self) -> Money:
        return Money.from_minor(self.unit_price_amount, "EGP")

    @property
    def line_total(self) -> Money:
        return Money.from_minor(self.line_total_amount, "EGP")
