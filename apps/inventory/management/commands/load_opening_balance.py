"""Seed command to import stock opening balances from CSV."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Category, Product, Variant
from apps.core.money import Money
from apps.inventory.models import Batch, Location, SerialUnit, StockMovement
from apps.inventory.services import MovementLine, move_stock_many


class Command(BaseCommand):
    """Seed inventory opening balance from CSV (e.g. samples/stock_opening_balance.csv)."""

    help = "Load stock opening balances from CSV file into the append-only stock ledger."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "file_path",
            nargs="?",
            default="samples/stock_opening_balance.csv",
            help="Path to opening balance CSV file.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        file_path = Path(options["file_path"])
        if not file_path.is_file():
            self.stderr.write(self.style.ERROR(f"CSV file not found: {file_path}"))
            raise SystemExit(1)

        # Pre-seed default locations if not existing
        locations: dict[str, Location] = {}
        main_loc, _ = Location.objects.get_or_create(
            code="MAIN",
            defaults={
                "name_en": "Main Warehouse",
                "name_ar": "المستودع الرئيسي",
                "kind": "warehouse",
                "sells_online": True,
                "priority": 1,
            },
        )
        locations["MAIN"] = main_loc

        branch1_loc, _ = Location.objects.get_or_create(
            code="BRANCH1",
            defaults={
                "name_en": "Branch 1 (Nasr City)",
                "name_ar": "فرع 1 (مدينة نصر)",
                "kind": "store",
                "sells_online": True,
                "priority": 2,
            },
        )
        locations["BRANCH1"] = branch1_loc

        category, _ = Category.objects.get_or_create(
            slug="general",
            defaults={"name_en": "General", "name_ar": "عام"},
        )

        rows_imported = 0
        total_movements = 0

        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                sku = row["sku"].strip()
                location_code = row["location_code"].strip().upper()
                qty_str = row["quantity"].strip()
                cost_str = row["unit_cost_egp"].strip()
                batch_code = row.get("batch_code", "").strip()
                expiry_str = row.get("expiry_date", "").strip()
                serials_str = row.get("serials", "").strip()

                if not sku or not location_code or not qty_str:
                    continue

                location = locations.get(location_code)
                if not location:
                    location, _ = Location.objects.get_or_create(
                        code=location_code,
                        defaults={
                            "name_en": f"Location {location_code}",
                            "name_ar": f"موقع {location_code}",
                            "kind": "store",
                            "sells_online": True,
                            "priority": 10,
                        },
                    )
                    locations[location_code] = location

                # Check if this row was already loaded (idempotency check)
                ref_id = f"open_bal_{sku}_{location_code}_{idx}"
                if StockMovement.objects.filter(
                    ref_type="opening_balance_csv", ref_id=ref_id
                ).exists():
                    self.stdout.write(
                        f"Row {idx} ({sku} @ {location_code}) already imported; skipping."
                    )
                    continue

                quantity = Decimal(qty_str)
                cost_money = Money.from_major(cost_str) if cost_str else Money.zero()

                # Infer tracking mode and unit
                tracking_mode = "none"
                if serials_str:
                    tracking_mode = "serial"
                elif batch_code:
                    tracking_mode = "batch"

                unit = "piece"
                unit_step = Decimal("1.000")
                if "KG" in sku.upper():
                    unit = "kg"
                    unit_step = Decimal("0.250")
                elif "L" in sku.upper():
                    unit = "litre"

                # Find or create variant
                product_handle = slugify(sku)
                product, _ = Product.objects.get_or_create(
                    handle=product_handle,
                    defaults={
                        "title_en": sku.replace("-", " "),
                        "title_ar": sku.replace("-", " "),
                        "category": category,
                        "status": "active",
                    },
                )

                variant, _ = Variant.objects.get_or_create(
                    sku__iexact=sku,
                    defaults={
                        "product": product,
                        "sku": sku,
                        "title_en": sku,
                        "title_ar": sku,
                        "cost_amount": cost_money.amount,
                        "price_amount": int(cost_money.amount * Decimal("1.25")),
                        "tracking_mode": tracking_mode,
                        "unit": unit,
                        "unit_step": unit_step,
                    },
                )

                batch_obj: Batch | None = None
                if batch_code:
                    expiry_date: date | None = None
                    if expiry_str:
                        expiry_date = date.fromisoformat(expiry_str)
                    batch_obj, _ = Batch.objects.get_or_create(
                        variant=variant,
                        batch_code=batch_code,
                        defaults={"expiry_date": expiry_date},
                    )

                movement_lines: list[MovementLine] = []

                if serials_str:
                    serials = [s.strip() for s in serials_str.split(";") if s.strip()]
                    for sn in serials:
                        serial_unit, _ = SerialUnit.objects.get_or_create(
                            variant=variant,
                            serial_number=sn,
                            defaults={"status": "in_stock", "location": location},
                        )
                        movement_lines.append(
                            MovementLine(
                                variant_id=variant.id,
                                location_id=location.id,
                                quantity_delta=Decimal("1.000"),
                                unit_cost_amount=cost_money.amount,
                                serial_id=serial_unit.id,
                                note="Imported via opening balance CSV",
                            )
                        )
                else:
                    movement_lines.append(
                        MovementLine(
                            variant_id=variant.id,
                            location_id=location.id,
                            quantity_delta=quantity,
                            unit_cost_amount=cost_money.amount,
                            batch_id=batch_obj.id if batch_obj else None,
                            note="Imported via opening balance CSV",
                        )
                    )

                movements = move_stock_many(
                    lines=movement_lines,
                    reason="opening_balance",
                    ref_type="opening_balance_csv",
                    ref_id=ref_id,
                )
                rows_imported += 1
                total_movements += len(movements)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully loaded opening balance: {rows_imported} rows processed, "
                f"{total_movements} ledger movements posted."
            )
        )
