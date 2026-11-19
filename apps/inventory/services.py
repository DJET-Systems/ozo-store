"""Inventory domain service: the SOLE authorized write path for all stock mutations.

Invariants enforced:
- INV-1: StockLevel.on_hand equals sum(StockMovement.quantity_delta) for any variant and location.
- INV-2: StockLevel.reserved equals sum(active StockReservation.quantity).
- INV-3: No negative on_hand unless variant.allow_negative_stock is explicitly true.
- INV-4: All updates acquire row locks in deterministic (variant_id, location_id) order.
- INV-5: StockMovement is append-only.
- INV-6: Every movement references a reason code, document ref, and actor.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import Variant
from apps.core.models import AuditLog
from apps.inventory.models import (
    SerialUnit,
    StockLevel,
    StockMovement,
    StockReservation,
)


class InventoryError(Exception):
    """Base exception for inventory domain errors."""


class InsufficientStock(InventoryError):
    """Raised when an operation would cause stock to drop below 0 when not allowed."""

    def __init__(
        self,
        variant_id: int,
        location_id: int,
        requested: Decimal,
        available: Decimal,
    ) -> None:
        self.variant_id = variant_id
        self.location_id = location_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for variant {variant_id} at location {location_id}: "
            f"requested {requested}, available {available}"
        )


class InvalidReservationState(InventoryError):
    """Raised when an operation is attempted on a non-active or non-existent reservation."""


@dataclass(frozen=True, slots=True)
class MovementLine:
    """Descriptor for a single variant stock change at a location."""

    variant_id: int
    location_id: int
    quantity_delta: Decimal | int | str
    unit_cost_amount: int | None = None  # minor units (piastres)
    batch_id: int | None = None
    serial_id: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.quantity_delta, float):
            raise TypeError(
                "Floats are prohibited for inventory quantities. Use Decimal, int, or str."
            )


@dataclass(frozen=True, slots=True)
class ReservationLine:
    """Descriptor for an order reservation request."""

    variant_id: int
    location_id: int
    quantity: Decimal | int | str

    def __post_init__(self) -> None:
        if isinstance(self.quantity, float):
            raise TypeError(
                "Floats are prohibited for inventory quantities. Use Decimal, int, or str."
            )


def _ensure_stock_levels_exist(pairs: list[tuple[int, int]]) -> None:
    """Ensure StockLevel rows exist using bulk insert with conflict suppression (Decision D5)."""
    if not pairs:
        return

    variant_ids = {p[0] for p in pairs}
    variants = {v.id: v for v in Variant.objects.filter(id__in=variant_ids)}

    levels_to_create = [
        StockLevel(
            variant_id=var_id,
            location_id=loc_id,
            allow_negative=variants[var_id].allow_negative_stock if var_id in variants else False,
        )
        for var_id, loc_id in pairs
    ]
    StockLevel.objects.bulk_create(levels_to_create, ignore_conflicts=True)


def _lock_stock_levels(pairs: list[tuple[int, int]]) -> dict[tuple[int, int], StockLevel]:
    """Acquire SELECT FOR UPDATE locks on StockLevel rows in deterministic order (Decision D6)."""
    sorted_pairs = sorted(set(pairs))
    _ensure_stock_levels_exist(sorted_pairs)

    locked_levels = (
        StockLevel.objects.select_for_update()
        .filter(
            variant_id__in=[p[0] for p in sorted_pairs],
            location_id__in=[p[1] for p in sorted_pairs],
        )
        .order_by("variant_id", "location_id")
    )

    mapping: dict[tuple[int, int], StockLevel] = {}
    for level in locked_levels:
        key = (level.variant_id, level.location_id)
        if key in sorted_pairs:
            mapping[key] = level

    return mapping


@transaction.atomic
def move_stock_many(
    *,
    lines: Sequence[MovementLine],
    reason: str,
    ref_type: str = "",
    ref_id: str = "",
    note: str = "",
    actor: Any = None,
    sync_audit: bool = True,
) -> list[StockMovement]:
    """Execute one or more stock movements atomically against the append-only ledger.

    Guarantees:
    - Atomicity: all lines commit together or none do.
    - Concurrency safety: sorted row locking avoids deadlocks and race conditions.
    - Non-negative invariant: prevents on_hand < 0 unless allow_negative is set.
    - Weighted Average Cost (WAC): updated on purchase_receipt and opening_balance.
    """
    if not lines:
        return []

    pairs = [(line.variant_id, line.location_id) for line in lines]
    locked_levels = _lock_stock_levels(pairs)

    created_movements: list[StockMovement] = []
    levels_to_save: set[StockLevel] = set()

    for line in lines:
        key = (line.variant_id, line.location_id)
        level = locked_levels[key]
        delta = Decimal(str(line.quantity_delta))

        # Check stock balance constraints
        new_on_hand = level.on_hand + delta
        if not level.allow_negative and new_on_hand < 0:
            raise InsufficientStock(
                variant_id=line.variant_id,
                location_id=line.location_id,
                requested=-delta,
                available=level.on_hand,
            )

        # Update Weighted Average Cost (WAC) on positive receipts with cost (Decision D8)
        if delta > 0 and line.unit_cost_amount is not None:
            incoming_cost = Decimal(line.unit_cost_amount)
            incoming_qty = delta
            old_qty = level.on_hand
            old_wac = level.avg_unit_cost
            total_qty = old_qty + incoming_qty
            if total_qty > 0:
                new_wac = ((old_qty * old_wac) + (incoming_qty * incoming_cost)) / total_qty
                level.avg_unit_cost = new_wac.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        # Update physical on_hand
        level.on_hand = new_on_hand
        levels_to_save.add(level)

        # If serial unit is associated, update its location and state
        if line.serial_id:
            serial = SerialUnit.objects.select_for_update().get(id=line.serial_id)
            if delta < 0:
                serial.status = "sold"
                serial.location = None
            elif delta > 0:
                serial.status = "in_stock"
                serial.location_id = line.location_id
            serial.save(update_fields=["status", "location", "updated_at"])

        # Create the append-only ledger entry
        movement = StockMovement.objects.create(
            variant_id=line.variant_id,
            location_id=line.location_id,
            quantity_delta=delta,
            reason=reason,
            ref_type=ref_type,
            ref_id=str(ref_id),
            unit_cost_amount=line.unit_cost_amount,
            batch_id=line.batch_id,
            serial_id=line.serial_id,
            note=line.note or note,
            created_by=(
                actor
                if (actor and hasattr(actor, "is_authenticated") and actor.is_authenticated)
                else None
            ),
        )
        created_movements.append(movement)

    # Save all modified stock levels
    for level in levels_to_save:
        level.save(update_fields=["on_hand", "avg_unit_cost", "updated_at"])

    if sync_audit:
        AuditLog.log_action(
            action=f"stock_movement:{reason}",
            entity_type="StockLedger",
            entity_id=ref_id or (str(created_movements[0].id) if created_movements else "0"),
            actor=actor,
            diff={
                "lines_count": len(created_movements),
                "reason": reason,
                "ref_type": ref_type,
                "ref_id": ref_id,
            },
        )

    return created_movements


@transaction.atomic
def reserve_many(
    *,
    order_id: str,
    lines: Sequence[ReservationLine],
    ttl_minutes: int = 30,
) -> list[StockReservation]:
    """Hold stock for an order across one or more lines without moving physical goods.

    Guarantees:
    - Atomicity: all items reserved or entire hold fails.
    - Checks (on_hand - reserved >= requested) for each line.
    - Updates StockLevel.reserved under row lock.
    """
    if not lines:
        return []

    pairs = [(line.variant_id, line.location_id) for line in lines]
    locked_levels = _lock_stock_levels(pairs)

    reservations: list[StockReservation] = []
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)

    for line in lines:
        key = (line.variant_id, line.location_id)
        level = locked_levels[key]
        requested = Decimal(str(line.quantity))

        available = level.on_hand - level.reserved
        if not level.allow_negative and available < requested:
            raise InsufficientStock(
                variant_id=line.variant_id,
                location_id=line.location_id,
                requested=requested,
                available=available,
            )

        level.reserved += requested
        level.save(update_fields=["reserved", "updated_at"])

        res = StockReservation.objects.create(
            order_id=order_id,
            variant_id=line.variant_id,
            location_id=line.location_id,
            quantity=requested,
            expires_at=expires_at,
            status="active",
        )
        reservations.append(res)

    return reservations


@transaction.atomic
def release_reservation(*, order_id: str, actor: Any = None) -> int:
    """Release active reservations for an order and decrement StockLevel.reserved."""
    active_reservations = list(
        StockReservation.objects.select_for_update()
        .filter(order_id=order_id, status="active")
        .order_by("variant_id", "location_id")
    )
    if not active_reservations:
        return 0

    pairs = [(res.variant_id, res.location_id) for res in active_reservations]
    locked_levels = _lock_stock_levels(pairs)

    for res in active_reservations:
        key = (res.variant_id, res.location_id)
        level = locked_levels[key]
        level.reserved = max(Decimal("0.000"), level.reserved - res.quantity)
        level.save(update_fields=["reserved", "updated_at"])

        res.status = "released"
        res.save(update_fields=["status", "updated_at"])

    AuditLog.log_action(
        action="stock_reservation:released",
        entity_type="Order",
        entity_id=order_id,
        actor=actor,
        diff={"released_count": len(active_reservations)},
    )
    return len(active_reservations)


@transaction.atomic
def consume_reservation(
    *,
    order_id: str,
    actor: Any = None,
) -> list[StockMovement]:
    """Convert active reservations into fulfilled sale shipments.

    Decrements StockLevel.reserved and executes sale_shipment stock movements.
    """
    active_reservations = list(
        StockReservation.objects.select_for_update()
        .filter(order_id=order_id, status="active")
        .order_by("variant_id", "location_id")
    )
    if not active_reservations:
        raise InvalidReservationState(f"No active reservations found for order {order_id}")

    pairs = [(res.variant_id, res.location_id) for res in active_reservations]
    locked_levels = _lock_stock_levels(pairs)

    # 1. Decrement reserved cache
    for res in active_reservations:
        key = (res.variant_id, res.location_id)
        level = locked_levels[key]
        level.reserved = max(Decimal("0.000"), level.reserved - res.quantity)
        level.save(update_fields=["reserved", "updated_at"])
        res.status = "consumed"
        res.save(update_fields=["status", "updated_at"])

    # 2. Build shipment lines
    movement_lines = [
        MovementLine(
            variant_id=res.variant_id,
            location_id=res.location_id,
            quantity_delta=-res.quantity,
            note=f"Fulfillment for order {order_id}",
        )
        for res in active_reservations
    ]

    # 3. Post movements through the ledger
    return move_stock_many(
        lines=movement_lines,
        reason="sale_shipment",
        ref_type="order",
        ref_id=order_id,
        actor=actor,
    )


def expire_stale_reservations() -> int:
    """Find all active reservations whose expiry timestamp has elapsed and release them."""
    now = timezone.now()
    stale_order_ids = (
        StockReservation.objects.filter(status="active", expires_at__lte=now)
        .values_list("order_id", flat=True)
        .distinct()
    )
    total_released = 0
    for order_id in stale_order_ids:
        total_released += release_reservation(order_id=order_id)
    return total_released


@transaction.atomic
def repair_stock_level(
    *,
    variant_id: int,
    location_id: int,
    actor: Any = None,
) -> tuple[Decimal, Decimal]:
    """Recompute StockLevel on_hand and reserved strictly from source of truth records.

    Source of truth:
    - on_hand: SUM(StockMovement.quantity_delta)
    - reserved: SUM(StockReservation.quantity WHERE status='active')

    Emits an AuditLog entry whenever discrepancy is detected and resolved.
    """
    key = (variant_id, location_id)
    locked_levels = _lock_stock_levels([key])
    level = locked_levels[key]

    movement_sum = StockMovement.objects.filter(
        variant_id=variant_id, location_id=location_id
    ).aggregate(total=Sum("quantity_delta"))["total"] or Decimal("0.000")

    reservation_sum = StockReservation.objects.filter(
        variant_id=variant_id, location_id=location_id, status="active"
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.000")

    old_on_hand = level.on_hand
    old_reserved = level.reserved

    discrepancy = (old_on_hand != movement_sum) or (old_reserved != reservation_sum)

    if discrepancy:
        level.on_hand = movement_sum
        level.reserved = reservation_sum
        level.save(update_fields=["on_hand", "reserved", "updated_at"])

        AuditLog.log_action(
            action="stock_level:repaired",
            entity_type="StockLevel",
            entity_id=f"{variant_id}:{location_id}",
            actor=actor,
            diff={
                "old_on_hand": str(old_on_hand),
                "new_on_hand": str(movement_sum),
                "old_reserved": str(old_reserved),
                "new_reserved": str(reservation_sum),
            },
        )

    return movement_sum, reservation_sum
