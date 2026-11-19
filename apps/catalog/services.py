"""Catalog domain services: bulk product CSV import, categories, and barcode lookups."""

from __future__ import annotations

import contextlib
import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, Product, Variant


@dataclass
class ImportResult:
    """Summary metrics of a catalog CSV import operation."""

    dry_run: bool
    total_rows: int = 0
    products_created: int = 0
    products_updated: int = 0
    variants_created: int = 0
    variants_updated: int = 0
    errors: list[str] = field(default_factory=list)
    product_handles: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def created_products(self) -> int:
        return self.products_created

    @property
    def created_variants(self) -> int:
        return self.variants_created


def get_or_create_category_path(path_str: str) -> Category | None:
    """Resolve or create a nested category tree from a path string e.g. 'A > B > C'."""
    if not path_str or not path_str.strip():
        return None

    parts = [p.strip() for p in path_str.split(">") if p.strip()]
    parent: Category | None = None

    for part in parts:
        slug = slugify(part, allow_unicode=True) or f"cat-{abs(hash(part)) % 100000}"
        category = (
            Category.objects.filter(slug=slug).first()
            or Category.objects.filter(name_en__iexact=part, parent=parent).first()
        )
        if not category:
            category = Category.objects.create(
                name_en=part,
                name_ar=part,
                slug=slug,
                parent=parent,
            )
        parent = category

    return parent


def import_products_from_csv(
    source: str | Path | TextIO,
    *,
    dry_run: bool = False,
) -> ImportResult:
    """Import products and variants from CSV according to the DJET contract.

    Invariants:
    - Zero-touch to the stock ledger: catalog import never writes to StockMovement or StockLevel.
    - Groups rows into products by product_handle (with deterministic fallback).
    - If dry_run=True, executes within an atomic transaction rolled back at the end.
    """
    result = ImportResult(dry_run=dry_run)

    # Resolve source into file-like iterator
    f: TextIO
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            result.errors.append(f"File not found: {p}")
            return result
        f = p.open("r", encoding="utf-8-sig")
        should_close = True
    else:
        f = source
        should_close = False

    try:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            result.errors.append("Empty CSV file or missing headers.")
            return result

        rows = list(reader)
        result.total_rows = len(rows)

        # Group rows by product_handle or fallback prefix
        product_groups: dict[str, list[dict[str, Any]]] = {}
        for idx, row in enumerate(rows, start=2):
            raw_handle = row.get("product_handle", "").strip() or row.get("handle", "").strip()
            sku = row.get("sku", "").strip()
            title_en = row.get("title_en", "").strip()

            if not raw_handle:
                # Deterministic grouping fallback (F1/D-Q3)
                if sku and "-" in sku:
                    parts = sku.split("-")
                    raw_handle = slugify("-".join(parts[:3]))
                else:
                    raw_handle = slugify(title_en) or f"product-{idx}"

            handle = slugify(raw_handle) or f"product-{idx}"
            product_groups.setdefault(handle, []).append(row)

        @transaction.atomic
        def _execute_import() -> None:
            for handle, variant_rows in product_groups.items():
                first_row = variant_rows[0]
                category_path = first_row.get("category_path", "").strip()
                category = get_or_create_category_path(category_path)
                brand = first_row.get("brand", "").strip()
                status = first_row.get("status", "active").strip().lower()
                if status not in {"draft", "active", "archived"}:
                    status = "active"

                # Product titles & optional image URL
                prod_title_en = first_row.get("product_title_en") or first_row.get("title_en", "")
                prod_title_ar = first_row.get("product_title_ar") or first_row.get("title_ar", "")
                image_url = first_row.get("image_url", "").strip()

                product, prod_created = Product.objects.get_or_create(
                    handle=handle,
                    defaults={
                        "title_en": prod_title_en,
                        "title_ar": prod_title_ar or prod_title_en,
                        "primary_brand": brand,
                        "category": category,
                        "status": status,
                        "image_url": image_url,
                    },
                )

                if prod_created:
                    result.products_created += 1
                else:
                    # Update fields if modified
                    product.title_en = prod_title_en
                    product.title_ar = prod_title_ar or prod_title_en
                    product.primary_brand = brand or product.primary_brand
                    if category:
                        product.category = category
                    if image_url:
                        product.image_url = image_url
                    product.status = status
                    product.save(
                        update_fields=[
                            "title_en",
                            "title_ar",
                            "primary_brand",
                            "category",
                            "image_url",
                            "status",
                        ]
                    )
                    result.products_updated += 1

                result.product_handles.append(handle)

                # Process variants for this product
                for v_row in variant_rows:
                    sku = v_row.get("sku", "").strip()
                    if not sku:
                        result.errors.append(f"Missing SKU in row for product {handle}")
                        continue

                    barcode = v_row.get("barcode", "").strip() or None
                    v_title_en = v_row.get("title_en", "").strip()
                    v_title_ar = v_row.get("title_ar", "").strip()
                    tracking_mode = v_row.get("tracking_mode", "none").strip().lower()
                    if tracking_mode not in {"none", "batch", "serial"}:
                        tracking_mode = "none"

                    condition = v_row.get("condition", "new").strip().lower()
                    if condition not in {"new", "used_a", "used_b", "refurbished"}:
                        condition = "new"

                    unit = v_row.get("unit", "piece").strip() or "piece"
                    unit_step_str = v_row.get("unit_step", "1.000").strip()
                    try:
                        unit_step = Decimal(unit_step_str) if unit_step_str else Decimal("1.000")
                    except Exception:
                        unit_step = Decimal("1.000")

                    # Monetary values in minor units (piastres)
                    try:
                        price_val = Decimal(v_row.get("price_egp", "0") or "0")
                        price_amount = int(price_val * 100)
                    except Exception:
                        price_amount = 0

                    cost_str = v_row.get("cost_egp", "").strip()
                    try:
                        cost_amount = int(Decimal(cost_str) * 100) if cost_str else 0
                    except Exception:
                        cost_amount = 0

                    compare_str = (
                        v_row.get("compare_at_price_egp", "").strip()
                        or v_row.get("compare_at_egp", "").strip()
                    )
                    try:
                        compare_at_price_amount = (
                            int(Decimal(compare_str) * 100) if compare_str else None
                        )
                    except Exception:
                        compare_at_price_amount = None

                    # Weight & Warranty
                    weight_str = v_row.get("weight_g", "0").strip()
                    weight_g = int(weight_str) if weight_str and weight_str.isdigit() else 0

                    warranty_str = v_row.get("warranty_months", "0").strip()
                    warranty_months = (
                        int(warranty_str) if warranty_str and warranty_str.isdigit() else 0
                    )

                    # Options map
                    options_json: dict[str, str] = {}
                    for i in (1, 2, 3):
                        opt_name = v_row.get(f"option{i}_name", "").strip()
                        opt_val = v_row.get(f"option{i}_value", "").strip()
                        if opt_name and opt_val:
                            options_json[opt_name] = opt_val

                    variant = Variant.objects.filter(sku__iexact=sku).first()
                    if not variant:
                        Variant.objects.create(
                            product=product,
                            sku=sku,
                            barcode=barcode,
                            title_en=v_title_en,
                            title_ar=v_title_ar or v_title_en,
                            price_amount=price_amount,
                            compare_at_price_amount=compare_at_price_amount,
                            cost_amount=cost_amount,
                            tracking_mode=tracking_mode,
                            condition=condition,
                            unit=unit,
                            unit_step=unit_step,
                            weight_g=weight_g,
                            options_json=options_json,
                            warranty_months=warranty_months,
                        )
                        result.variants_created += 1
                    else:
                        variant.product = product
                        variant.barcode = barcode
                        variant.title_en = v_title_en
                        variant.title_ar = v_title_ar or v_title_en
                        variant.price_amount = price_amount
                        variant.compare_at_price_amount = compare_at_price_amount
                        variant.cost_amount = cost_amount
                        variant.tracking_mode = tracking_mode
                        variant.condition = condition
                        variant.unit = unit
                        variant.unit_step = unit_step
                        variant.weight_g = weight_g
                        variant.options_json = options_json
                        variant.warranty_months = warranty_months
                        variant.save()
                        result.variants_updated += 1

            if dry_run:
                raise transaction.TransactionManagementError(
                    "Dry-run requested; rolling back all database mutations."
                )

        if dry_run:
            with contextlib.suppress(transaction.TransactionManagementError):
                _execute_import()
        else:
            _execute_import()

    finally:
        if should_close:
            f.close()

    return result


def lookup_barcode(barcode: str) -> dict[str, Any] | None:
    """Find variant by exact barcode or SKU string for HID scanner inputs."""
    clean_code = barcode.strip()
    if not clean_code:
        return None

    variant = Variant.objects.select_related("product").filter(barcode=clean_code).first()
    if not variant:
        variant = Variant.objects.select_related("product").filter(sku__iexact=clean_code).first()

    if not variant:
        return None

    return {
        "sku": variant.sku,
        "barcode": variant.barcode,
        "title_en": variant.title_en or variant.product.title_en,
        "title_ar": variant.title_ar or variant.product.title_ar,
        "price_formatted": str(variant.price),
        "tracking_mode": variant.tracking_mode,
        "product_handle": variant.product.handle,
    }
