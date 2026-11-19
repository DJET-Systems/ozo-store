"""Catalog models: Category, Product, and Variant with pricing and tracking modes."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel
from apps.core.money import Money


class Category(TimeStampedModel):
    """Product category node in a tree hierarchy."""

    name_en = models.CharField(max_length=255)
    name_ar = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    description = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)

    class Meta:
        db_table = "catalog_category"
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self) -> str:
        return f"{self.name_en} / {self.name_ar}"


class Product(TimeStampedModel):
    """Core product definition containing one or more sellable Variants."""

    STATUS_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("draft", "Draft"),
        ("active", "Active"),
        ("archived", "Archived"),
    )

    handle = models.SlugField(max_length=255, unique=True)
    title_en = models.CharField(max_length=255)
    title_ar = models.CharField(max_length=255)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    primary_brand = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")

    class Meta:
        db_table = "catalog_product"
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self) -> str:
        return f"{self.title_en} / {self.title_ar}"


class Variant(TimeStampedModel):
    """Sellable SKU item with pricing, tracking mode, and physical units."""

    TRACKING_MODE_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("none", "None (Standard Count)"),
        ("batch", "Batch / Lot Tracked"),
        ("serial", "Serial / IMEI Tracked"),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=128)
    barcode = models.CharField(max_length=128, blank=True, null=True, unique=True)
    title_en = models.CharField(max_length=255, blank=True)
    title_ar = models.CharField(max_length=255, blank=True)

    # Monetary amounts stored as integer minor units (piastres for EGP)
    price_amount = models.BigIntegerField(
        default=0, help_text="Retail price in minor units (piastres)"
    )
    compare_at_price_amount = models.BigIntegerField(
        null=True, blank=True, help_text="Original/strikethrough price in minor units"
    )
    cost_amount = models.BigIntegerField(default=0, help_text="Purchase/cost price in minor units")

    CONDITION_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("new", "New"),
        ("used_a", "Used Grade A"),
        ("used_b", "Used Grade B"),
        ("refurbished", "Refurbished"),
    )

    tracking_mode = models.CharField(
        max_length=32,
        choices=TRACKING_MODE_CHOICES,
        default="none",
    )
    condition = models.CharField(
        max_length=32,
        choices=CONDITION_CHOICES,
        default="new",
    )
    unit = models.CharField(max_length=32, default="piece")
    unit_step = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("1.000"))
    weight_g = models.IntegerField(default=0, help_text="Weight in grams")
    options_json = models.JSONField(
        default=dict, blank=True, help_text="Variant options key-value map"
    )
    warranty_months = models.IntegerField(default=0, help_text="Warranty period in months")
    reorder_point = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("0.000"))
    reorder_quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal("0.000")
    )
    allow_negative_stock = models.BooleanField(
        default=False,
        help_text="Permit stock to drop below 0 (e.g. made-to-order items)",
    )

    class Meta:
        db_table = "catalog_variant"
        verbose_name = "Variant"
        verbose_name_plural = "Variants"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                Lower("sku"),
                name="uq_catalog_variant_sku_lower",
            )
        ]

    def __str__(self) -> str:
        return f"{self.sku} ({self.title_en or self.product.title_en})"

    @property
    def price(self) -> Money:
        return Money(amount=self.price_amount, currency="EGP")

    @price.setter
    def price(self, money: Money) -> None:
        self.price_amount = money.amount

    @property
    def cost(self) -> Money:
        return Money(amount=self.cost_amount, currency="EGP")

    @cost.setter
    def cost(self, money: Money) -> None:
        self.cost_amount = money.amount

    @property
    def compare_at_price(self) -> Money | None:
        if self.compare_at_price_amount is None:
            return None
        return Money(amount=self.compare_at_price_amount, currency="EGP")

    @compare_at_price.setter
    def compare_at_price(self, money: Money | None) -> None:
        self.compare_at_price_amount = money.amount if money else None
