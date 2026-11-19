"""Comprehensive unit and integration tests for inventory domain services and ledger."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product, Variant
from apps.inventory.models import (
    Batch,
    Location,
    SerialUnit,
    StockLevel,
    StockReservation,
)
from apps.inventory.services import (
    InsufficientStock,
    InvalidReservationState,
    MovementLine,
    ReservationLine,
    consume_reservation,
    expire_stale_reservations,
    move_stock_many,
    release_reservation,
    reserve_many,
)


@pytest.fixture
def setup_inventory_fixtures(db):
    """Create test category, product, variants, and locations."""
    cat = Category.objects.create(name_en="Electronics", name_ar="إلكترونيات", slug="electronics")
    product = Product.objects.create(
        handle="phone-x",
        title_en="Phone X",
        title_ar="هاتف إكس",
        category=cat,
        status="active",
    )
    v1 = Variant.objects.create(
        product=product,
        sku="PH-X-64-BLK",
        price_amount=100000,  # 1,000.00 EGP
        cost_amount=80000,  # 800.00 EGP
        tracking_mode="none",
        allow_negative_stock=False,
    )
    v2_allow_neg = Variant.objects.create(
        product=product,
        sku="PH-X-CUSTOM-MTO",
        price_amount=150000,
        cost_amount=100000,
        tracking_mode="none",
        allow_negative_stock=True,
    )
    v_serial = Variant.objects.create(
        product=product,
        sku="PH-X-SERIAL-TRACKED",
        price_amount=200000,
        cost_amount=150000,
        tracking_mode="serial",
    )
    v_batch = Variant.objects.create(
        product=product,
        sku="PH-X-BATCH-TRACKED",
        price_amount=50000,
        cost_amount=30000,
        tracking_mode="batch",
    )

    loc_main = Location.objects.create(
        code="MAIN", name_en="Main Warehouse", name_ar="المستودع الرئيسي"
    )
    loc_branch = Location.objects.create(code="BRANCH1", name_en="Branch 1", name_ar="الفرع 1")

    return {
        "v1": v1,
        "v2_allow_neg": v2_allow_neg,
        "v_serial": v_serial,
        "v_batch": v_batch,
        "loc_main": loc_main,
        "loc_branch": loc_branch,
    }


def test_positive_receipt_and_wac_calculation(setup_inventory_fixtures):
    """Test receiving stock updates on_hand and recalculates weighted average cost (WAC)."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    # Initial receipt: 10 units @ 100.00 EGP (10000 piastres)
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("10.000"),
                unit_cost_amount=10000,
            )
        ],
        reason="purchase_receipt",
        ref_type="po",
        ref_id="PO-001",
    )

    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.on_hand == Decimal("10.000")
    assert level.avg_unit_cost == Decimal("10000.0000")
    assert level.available == Decimal("10.000")

    # Second receipt: 10 units @ 200.00 EGP (20000 piastres)
    # New WAC: (10 * 10000 + 10 * 20000) / 20 = 15000 piastres
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("10.000"),
                unit_cost_amount=20000,
            )
        ],
        reason="purchase_receipt",
        ref_type="po",
        ref_id="PO-002",
    )

    level.refresh_from_db()
    assert level.on_hand == Decimal("20.000")
    assert level.avg_unit_cost == Decimal("15000.0000")


def test_insufficient_stock_rejection(setup_inventory_fixtures):
    """Test reduction below 0 raises InsufficientStock when allow_negative_stock is False."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    # Receive 5 units
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("5.000"),
            )
        ],
        reason="purchase_receipt",
    )

    # Attempt to ship 6 units -> InsufficientStock
    with pytest.raises(InsufficientStock) as exc_info:
        move_stock_many(
            lines=[
                MovementLine(
                    variant_id=v1.id,
                    location_id=loc_main.id,
                    quantity_delta=Decimal("-6.000"),
                )
            ],
            reason="sale_shipment",
        )

    assert exc_info.value.requested == Decimal("6.000")
    assert exc_info.value.available == Decimal("5.000")

    # Verify no state mutated
    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.on_hand == Decimal("5.000")


def test_allow_negative_stock_permitted(setup_inventory_fixtures):
    """Test variant with allow_negative_stock=True can drop below 0."""
    v2 = setup_inventory_fixtures["v2_allow_neg"]
    loc_main = setup_inventory_fixtures["loc_main"]

    movements = move_stock_many(
        lines=[
            MovementLine(
                variant_id=v2.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("-3.000"),
            )
        ],
        reason="sale_shipment",
    )

    assert len(movements) == 1
    level = StockLevel.objects.get(variant=v2, location=loc_main)
    assert level.on_hand == Decimal("-3.000")
    assert level.allow_negative is True


def test_multi_line_movement_atomicity(setup_inventory_fixtures):
    """Test multiple lines commit atomically or rollback completely on error."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]
    loc_branch = setup_inventory_fixtures["loc_branch"]

    # Stock at MAIN = 10, BRANCH = 2
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id, location_id=loc_main.id, quantity_delta=Decimal("10.000")
            ),
            MovementLine(
                variant_id=v1.id, location_id=loc_branch.id, quantity_delta=Decimal("2.000")
            ),
        ],
        reason="opening_balance",
    )

    # Multi-line: transfer 5 from MAIN (valid), but 5 from BRANCH (exceeds 2)
    with pytest.raises(InsufficientStock):
        move_stock_many(
            lines=[
                MovementLine(
                    variant_id=v1.id, location_id=loc_main.id, quantity_delta=Decimal("-5.000")
                ),
                MovementLine(
                    variant_id=v1.id, location_id=loc_branch.id, quantity_delta=Decimal("-5.000")
                ),
            ],
            reason="transfer_out",
        )

    # Verify entire transaction rolled back: MAIN is still 10, BRANCH is still 2
    level_main = StockLevel.objects.get(variant=v1, location=loc_main)
    level_branch = StockLevel.objects.get(variant=v1, location=loc_branch)
    assert level_main.on_hand == Decimal("10.000")
    assert level_branch.on_hand == Decimal("2.000")


def test_reservation_hold_consume_and_release(setup_inventory_fixtures):
    """Test full reservation lifecycle: hold -> consume -> release."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    # 1. Receive 10 units
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id, location_id=loc_main.id, quantity_delta=Decimal("10.000")
            )
        ],
        reason="purchase_receipt",
    )

    # 2. Hold 4 units for Order DJ-101
    reservations = reserve_many(
        order_id="DJ-101",
        lines=[
            ReservationLine(variant_id=v1.id, location_id=loc_main.id, quantity=Decimal("4.000"))
        ],
        ttl_minutes=15,
    )
    assert len(reservations) == 1
    assert reservations[0].status == "active"

    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.on_hand == Decimal("10.000")
    assert level.reserved == Decimal("4.000")
    assert level.available == Decimal("6.000")

    # 3. Cannot reserve more than available (attempting 7 when available is 6)
    with pytest.raises(InsufficientStock):
        reserve_many(
            order_id="DJ-102",
            lines=[
                ReservationLine(
                    variant_id=v1.id, location_id=loc_main.id, quantity=Decimal("7.000")
                )
            ],
        )

    # 4. Consume reservation for DJ-101
    movements = consume_reservation(order_id="DJ-101")
    assert len(movements) == 1
    assert movements[0].reason == "sale_shipment"
    assert movements[0].quantity_delta == Decimal("-4.000")

    level.refresh_from_db()
    assert level.on_hand == Decimal("6.000")
    assert level.reserved == Decimal("0.000")
    assert level.available == Decimal("6.000")

    # 5. Test Release for a new reservation
    reserve_many(
        order_id="DJ-103",
        lines=[
            ReservationLine(variant_id=v1.id, location_id=loc_main.id, quantity=Decimal("3.000"))
        ],
    )
    level.refresh_from_db()
    assert level.reserved == Decimal("3.000")

    released_count = release_reservation(order_id="DJ-103")
    assert released_count == 1

    level.refresh_from_db()
    assert level.on_hand == Decimal("6.000")
    assert level.reserved == Decimal("0.000")


def test_stale_reservation_expiry(setup_inventory_fixtures):
    """Test periodic task releases stale reservations whose TTL elapsed."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id, location_id=loc_main.id, quantity_delta=Decimal("10.000")
            )
        ],
        reason="purchase_receipt",
    )

    # Create reservation with past expiry
    reserve_many(
        order_id="DJ-EXPIRED-1",
        lines=[
            ReservationLine(variant_id=v1.id, location_id=loc_main.id, quantity=Decimal("2.000"))
        ],
        ttl_minutes=0,
    )
    StockReservation.objects.filter(order_id="DJ-EXPIRED-1").update(
        expires_at=timezone.now() - timedelta(minutes=5)
    )

    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.reserved == Decimal("2.000")

    released = expire_stale_reservations()
    assert released == 1

    level.refresh_from_db()
    assert level.reserved == Decimal("0.000")
    assert StockReservation.objects.get(order_id="DJ-EXPIRED-1").status == "released"


def test_serial_unit_tracking(setup_inventory_fixtures):
    """Test receiving and selling unique serialized units."""
    v_serial = setup_inventory_fixtures["v_serial"]
    loc_main = setup_inventory_fixtures["loc_main"]

    sn = SerialUnit.objects.create(
        variant=v_serial,
        serial_number="IMEI-9990001",
        status="in_stock",
        location=loc_main,
    )

    # 1. Receipt movement with serial linked
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v_serial.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("1.000"),
                unit_cost_amount=150000,
                serial_id=sn.id,
            )
        ],
        reason="purchase_receipt",
    )

    sn.refresh_from_db()
    assert sn.status == "in_stock"
    assert sn.location == loc_main

    # 2. Sale shipment with serial linked
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v_serial.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("-1.000"),
                serial_id=sn.id,
            )
        ],
        reason="sale_shipment",
    )

    sn.refresh_from_db()
    assert sn.status == "sold"
    assert sn.location is None


def test_batch_tracking(setup_inventory_fixtures):
    """Test receipt and shipment linked to a batch lot."""
    v_batch = setup_inventory_fixtures["v_batch"]
    loc_main = setup_inventory_fixtures["loc_main"]

    batch = Batch.objects.create(
        variant=v_batch,
        batch_code="LOT-2026-X1",
        expiry_date=timezone.now().date() + timedelta(days=90),
    )

    movements = move_stock_many(
        lines=[
            MovementLine(
                variant_id=v_batch.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("50.000"),
                unit_cost_amount=30000,
                batch_id=batch.id,
            )
        ],
        reason="purchase_receipt",
    )

    assert movements[0].batch == batch
    level = StockLevel.objects.get(variant=v_batch, location=loc_main)
    assert level.on_hand == Decimal("50.000")


def test_transfer_between_locations(setup_inventory_fixtures):
    """Test stock transfer between two locations via transfer_out and transfer_in."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]
    loc_branch = setup_inventory_fixtures["loc_branch"]

    # Seed 10 at MAIN
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("10.000"),
            )
        ],
        reason="purchase_receipt",
    )

    # Transfer 4 from MAIN to BRANCH
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("-4.000"),
            ),
            MovementLine(
                variant_id=v1.id,
                location_id=loc_branch.id,
                quantity_delta=Decimal("4.000"),
            ),
        ],
        reason="transfer_in",
        ref_type="transfer",
        ref_id="TR-001",
    )

    level_main = StockLevel.objects.get(variant=v1, location=loc_main)
    level_branch = StockLevel.objects.get(variant=v1, location=loc_branch)
    assert level_main.on_hand == Decimal("6.000")
    assert level_branch.on_hand == Decimal("4.000")


def test_customer_return_restock_and_writeoff(setup_inventory_fixtures):
    """Test customer returns: restock adds stock back; writeoff logs disposal with 0 delta."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    # Initial stock: 10, then sell 2 -> on_hand = 8
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("10.000"),
            )
        ],
        reason="purchase_receipt",
    )
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("-2.000"),
            )
        ],
        reason="sale_shipment",
    )

    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.on_hand == Decimal("8.000")

    # 1. Customer returns 1 item in resalable condition -> return_restock (+1)
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("1.000"),
            )
        ],
        reason="return_restock",
        ref_type="return_request",
        ref_id="RET-001",
    )
    level.refresh_from_db()
    assert level.on_hand == Decimal("9.000")

    # 2. Customer returns 1 item damaged / broken -> return_writeoff (0 delta)
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("0.000"),
            )
        ],
        reason="return_writeoff",
        ref_type="return_request",
        ref_id="RET-002",
        note="Damaged casing: scrapped",
    )
    level.refresh_from_db()
    assert level.on_hand == Decimal("9.000")


def test_stock_count_and_damage_adjustments(setup_inventory_fixtures):
    """Test stock count discrepancy adjustments (+/-) and damage write-offs."""
    v1 = setup_inventory_fixtures["v1"]
    loc_main = setup_inventory_fixtures["loc_main"]

    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("20.000"),
            )
        ],
        reason="opening_balance",
    )

    # 1. Count session found 22 (positive variance +2)
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("2.000"),
            )
        ],
        reason="adjustment_count",
        ref_type="count_session",
        ref_id="CNT-NOV-01",
    )
    level = StockLevel.objects.get(variant=v1, location=loc_main)
    assert level.on_hand == Decimal("22.000")

    # 2. Damage adjustment: 3 units destroyed by water leak
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=v1.id,
                location_id=loc_main.id,
                quantity_delta=Decimal("-3.000"),
            )
        ],
        reason="adjustment_damage",
        note="Water leak in warehouse section C",
    )
    level.refresh_from_db()
    assert level.on_hand == Decimal("19.000")


def test_edge_cases_empty_lines_and_invalid_consumption(setup_inventory_fixtures):
    """Test edge cases: empty lines list and consuming non-existent reservation."""
    assert move_stock_many(lines=[], reason="adjustment_count") == []
    assert reserve_many(order_id="EMPTY", lines=[]) == []

    with pytest.raises(InvalidReservationState):
        consume_reservation(order_id="NON_EXISTENT_ORDER_999")
