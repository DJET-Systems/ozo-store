"""Command to audit and reconcile StockLevel cache against the append-only StockMovement ledger."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.inventory.models import StockLevel, StockMovement, StockReservation
from apps.inventory.services import repair_stock_level


class Command(BaseCommand):
    """Nightly or on-demand inventory reconciliation task.

    Invariants checked:
    - INV-1: stock_level.on_hand == sum(movement deltas)
    - INV-2: stock_level.reserved == sum(active reservations)
    """

    help = "Reconcile StockLevel records against the append-only StockMovement ledger."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Automatically repair detected discrepancies and write audit logs.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        auto_repair: bool = options["repair"]

        # Collect all active (variant_id, location_id) pairs across tables
        keys: set[tuple[int, int]] = set()
        keys.update(StockLevel.objects.values_list("variant_id", "location_id"))
        keys.update(StockMovement.objects.values_list("variant_id", "location_id"))
        keys.update(StockReservation.objects.values_list("variant_id", "location_id"))

        total_scanned = len(keys)
        discrepancies = 0
        repaired = 0

        self.stdout.write(f"Starting inventory reconciliation scan across {total_scanned} pairs...")

        for var_id, loc_id in sorted(keys):
            level = StockLevel.objects.filter(variant_id=var_id, location_id=loc_id).first()
            actual_on_hand = level.on_hand if level else Decimal("0.000")
            actual_reserved = level.reserved if level else Decimal("0.000")

            expected_on_hand = StockMovement.objects.filter(
                variant_id=var_id, location_id=loc_id
            ).aggregate(total=Sum("quantity_delta"))["total"] or Decimal("0.000")

            expected_reserved = StockReservation.objects.filter(
                variant_id=var_id, location_id=loc_id, status="active"
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")

            is_mismatch = (actual_on_hand != expected_on_hand) or (
                actual_reserved != expected_reserved
            )

            if is_mismatch:
                discrepancies += 1
                msg = (
                    f"DISCREPANCY: (variant={var_id}, location={loc_id}) -> "
                    f"on_hand: cached={actual_on_hand} vs ledger={expected_on_hand} | "
                    f"reserved: cached={actual_reserved} vs active={expected_reserved}"
                )
                self.stderr.write(self.style.ERROR(msg))

                if auto_repair:
                    repair_stock_level(variant_id=var_id, location_id=loc_id)
                    repaired += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"REPAIRED: (variant={var_id}, location={loc_id})")
                    )

        if discrepancies == 0:
            self.stdout.write(
                self.style.SUCCESS(f"Reconciliation clean. {total_scanned} pairs verified.")
            )
        else:
            summary = (
                f"Reconciliation completed with {discrepancies} discrepancies "
                f"(repaired: {repaired})."
            )
            if auto_repair:
                self.stdout.write(self.style.WARNING(summary))
            else:
                self.stderr.write(self.style.ERROR(summary))
                raise SystemExit(1)
