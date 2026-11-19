"""Inventory domain models: Locations, StockLevel, StockMovement ledger, and Reservations."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Location(TimeStampedModel):
    """Physical branch, warehouse, or transit storage holding stock."""

    KIND_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("store", "Store / Retail Branch"),
        ("warehouse", "Main Warehouse / Fulfillment Center"),
        ("returns", "Returns / Quarantine Depot"),
    )

    code = models.CharField(
        max_length=64, unique=True, help_text="Unique short code (e.g. MAIN, BRANCH1)"
    )
    name_en = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255)
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default="warehouse")
    sells_online = models.BooleanField(
        default=True,
        help_text="Stock at this location is available for ecommerce checkout fulfillment",
    )
    priority = models.IntegerField(
        default=10, help_text="Allocation priority (lower numbers chosen first)"
    )
    is_active = models.BooleanField(default=True)
    is_public_branch = models.BooleanField(
        default=False, help_text="Exposed on storefront branches grid and pickup selector"
    )
    opening_hours_en = models.CharField(max_length=255, blank=True)
    opening_hours_ar = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    address_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "inventory_location"
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering: ClassVar[tuple[str, ...]] = ("priority", "code")

    def __str__(self) -> str:
        return f"{self.code} - {self.name_en}"


class Batch(TimeStampedModel):
    """Lot or production batch with optional expiry date."""

    variant = models.ForeignKey(
        "catalog.Variant",
        on_delete=models.CASCADE,
        related_name="batches",
    )
    batch_code = models.CharField(max_length=128)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "inventory_batch"
        verbose_name = "Batch"
        verbose_name_plural = "Batches"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["variant", "batch_code"],
                name="uq_inventory_batch_variant_code",
            )
        ]

    def __str__(self) -> str:
        exp = f" (Exp: {self.expiry_date})" if self.expiry_date else ""
        return f"{self.variant.sku} Lot:{self.batch_code}{exp}"


class SerialUnit(TimeStampedModel):
    """Individual serialized unit (e.g. phone IMEI, laptop serial) tracked uniquely."""

    STATUS_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("in_stock", "In Stock"),
        ("reserved", "Reserved"),
        ("sold", "Sold"),
        ("returned", "Returned"),
    )

    variant = models.ForeignKey(
        "catalog.Variant",
        on_delete=models.CASCADE,
        related_name="serials",
    )
    serial_number = models.CharField(max_length=128, db_index=True)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default="in_stock", db_index=True
    )
    location = models.ForeignKey(
        Location,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="serials",
    )

    class Meta:
        db_table = "inventory_serial_unit"
        verbose_name = "Serial Unit"
        verbose_name_plural = "Serial Units"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["variant", "serial_number"],
                name="uq_inventory_serial_variant_sn",
            )
        ]

    def __str__(self) -> str:
        return f"{self.variant.sku} [SN: {self.serial_number}] ({self.status})"


class StockLevel(TimeStampedModel):
    """Derived inventory cache per variant and location.

    CRITICAL ARCHITECTURAL INVARIANT:
    This table MUST NEVER be directly updated by outside views or forms.
    All mutations must flow strictly through apps.inventory.services!
    """

    variant = models.ForeignKey(
        "catalog.Variant",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    on_hand = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text="Physical count currently present in the facility",
    )
    reserved = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text="Quantity allocated to unfulfilled orders/holds",
    )
    avg_unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text="Weighted Average Cost (WAC) per unit in minor units",
    )
    # Decision D4: Denormalized from variant to enable database-level CHECK constraint
    allow_negative = models.BooleanField(
        default=False,
        help_text="Permit negative on_hand balance when true",
    )

    class Meta:
        db_table = "inventory_stock_level"
        verbose_name = "Stock Level"
        verbose_name_plural = "Stock Levels"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["variant", "location"],
                name="uq_inventory_stock_level_var_loc",
            ),
            models.CheckConstraint(
                condition=Q(allow_negative=True) | Q(on_hand__gte=0),
                name="chk_stock_level_on_hand_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(reserved__gte=0),
                name="chk_stock_level_reserved_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.variant.sku} @ {self.location.code}: "
            f"on_hand={self.on_hand}, reserved={self.reserved}"
        )

    @property
    def available(self) -> Decimal:
        """Available stock for checkout = on_hand - reserved."""
        return max(Decimal("0.000"), self.on_hand - self.reserved)


class StockMovement(models.Model):
    """Append-only immutable stock ledger.

    Every physical movement, receipt, count adjustment, or transfer
    creates a single immutable record here. No updates or deletes allowed!
    """

    REASON_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("purchase_receipt", "Purchase Receipt (+)"),
        ("sale_shipment", "Sale Fulfillment (-)"),
        ("return_restock", "Customer Return Restock (+)"),
        ("return_writeoff", "Customer Return Write-off (0)"),
        ("adjustment_count", "Physical Count Adjustment (+/-)"),
        ("adjustment_damage", "Damaged / Spoiled Write-off (-)"),
        ("transfer_out", "Stock Transfer Out (-)"),
        ("transfer_in", "Stock Transfer In (+)"),
        ("opening_balance", "Opening Balance Import (+)"),
        ("repair_reconcile", "Reconciliation Ledger Repair (+/-)"),
    )

    variant = models.ForeignKey(
        "catalog.Variant",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    quantity_delta = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text="Signed quantity (+ for additions, - for reductions)",
    )
    reason = models.CharField(max_length=64, choices=REASON_CHOICES)
    ref_type = models.CharField(
        max_length=64, blank=True, help_text="e.g. order, po, transfer, count_session"
    )
    ref_id = models.CharField(
        max_length=128, blank=True, help_text="External or internal document identifier"
    )
    unit_cost_amount = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Unit cost in minor units (piastres) at transaction time",
    )
    batch = models.ForeignKey(
        Batch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    serial = models.ForeignKey(
        SerialUnit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_stock_movements",
    )

    class Meta:
        db_table = "inventory_stock_movement"
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        ordering: ClassVar[tuple[str, ...]] = ("-created_at", "-id")

    def __str__(self) -> str:
        sign = "+" if self.quantity_delta > 0 else ""
        return (
            f"[{self.created_at:%Y-%m-%d %H:%M}] {self.variant.sku} @ {self.location.code} "
            f"{sign}{self.quantity_delta} ({self.reason})"
        )


class StockReservation(TimeStampedModel):
    """Temporary hold on stock during checkout before order fulfillment or payment timeout."""

    STATUS_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("active", "Active"),
        ("consumed", "Consumed (Converted to Sale)"),
        ("released", "Released / Expired"),
    )

    order_id = models.CharField(max_length=128, db_index=True)
    variant = models.ForeignKey(
        "catalog.Variant",
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default="active", db_index=True
    )

    class Meta:
        db_table = "inventory_stock_reservation"
        verbose_name = "Stock Reservation"
        verbose_name_plural = "Stock Reservations"
        ordering: ClassVar[tuple[str, ...]] = ("-created_at",)

    def __str__(self) -> str:
        return f"Hold {self.quantity} of {self.variant.sku} for {self.order_id} ({self.status})"
