"""Concurrency and race-condition tests for the append-only stock ledger."""

from decimal import Decimal

import pytest

from apps.catalog.models import Category, Product, Variant
from apps.inventory.models import Location, StockLevel, StockMovement
from apps.inventory.services import InsufficientStock, MovementLine, move_stock_many
from tests.conftest import run_concurrently


@pytest.mark.django_db(transaction=True)
def test_fifty_concurrent_purchases_never_oversell():
    """Definition of Done gate: 50 concurrent purchase attempts against 10 units never oversell."""
    # 1. Setup isolated product, variant, and location
    cat = Category.objects.create(
        name_en="Limited Drops", name_ar="إصدارات محدودة", slug="limited-drops"
    )
    product = Product.objects.create(
        handle="hyper-sneaker-x",
        title_en="Hyper Sneaker X",
        title_ar="حذاء هايبر إكس",
        category=cat,
        status="active",
    )
    variant = Variant.objects.create(
        product=product,
        sku="SNK-HYPER-001",
        price_amount=500000,  # 5,000 EGP
        cost_amount=300000,
        tracking_mode="none",
        allow_negative_stock=False,
    )
    location = Location.objects.create(
        code="CONCURRENCY_HUB",
        name_en="Concurrency Hub",
        name_ar="مركز التزامن",
    )

    # 2. Seed exactly 10 units into the ledger
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=variant.id,
                location_id=location.id,
                quantity_delta=Decimal("10.000"),
                unit_cost_amount=300000,
            )
        ],
        reason="purchase_receipt",
        ref_type="seed",
        ref_id="INITIAL-10",
    )

    initial_level = StockLevel.objects.get(variant=variant, location=location)
    assert initial_level.on_hand == Decimal("10.000")

    # 3. 50 parallel workers simultaneously attempt to buy 1 unit each
    def attempt_purchase(idx: int) -> str:
        try:
            move_stock_many(
                lines=[
                    MovementLine(
                        variant_id=variant.id,
                        location_id=location.id,
                        quantity_delta=Decimal("-1.000"),
                        note=f"Worker #{idx} checkout",
                    )
                ],
                reason="sale_shipment",
                ref_type="order",
                ref_id=f"ORD-RACE-{idx:03d}",
            )
            return "SUCCESS"
        except InsufficientStock:
            return "OUT_OF_STOCK"

    results = run_concurrently(attempt_purchase, workers=50)

    # 4. Strict assertions on outcomes
    success_count = sum(1 for r in results if r == "SUCCESS")
    out_of_stock_count = sum(1 for r in results if r == "OUT_OF_STOCK")

    assert success_count == 10, f"Expected exactly 10 successful checkouts, got {success_count}!"
    assert out_of_stock_count == 40, (
        f"Expected exactly 40 out of stock rejections, got {out_of_stock_count}!"
    )

    # 5. Invariant check on DB state
    final_level = StockLevel.objects.get(variant=variant, location=location)
    assert final_level.on_hand == Decimal("0.000"), f"Expected on_hand=0, got {final_level.on_hand}"

    total_movements = StockMovement.objects.filter(variant=variant, location=location).count()
    assert total_movements == 11, (
        f"Expected 1 receipt + 10 sales = 11 movements, got {total_movements}"
    )

    shipment_movements = StockMovement.objects.filter(
        variant=variant, location=location, reason="sale_shipment"
    ).count()
    assert shipment_movements == 10
