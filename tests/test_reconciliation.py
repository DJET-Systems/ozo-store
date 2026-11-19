"""Tests for inventory ledger reconciliation and discrepancy repair job."""

import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product, Variant
from apps.core.models import AuditLog
from apps.inventory.models import Location, StockLevel
from apps.inventory.services import MovementLine, move_stock_many


@pytest.fixture
def setup_reconciliation_item(db):
    cat = Category.objects.create(name_en="Gadgets", name_ar="أجهزة", slug="gadgets")
    product = Product.objects.create(
        handle="gadget-a", title_en="Gadget A", title_ar="أداة أ", category=cat
    )
    variant = Variant.objects.create(product=product, sku="GDT-A-01", price_amount=10000)
    location = Location.objects.create(code="DEPOT1", name_en="Depot 1", name_ar="مستودع 1")

    # Legitimate ledger entries: +10 then -3 = ground truth 7
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=variant.id,
                location_id=location.id,
                quantity_delta=Decimal("10.000"),
            )
        ],
        reason="purchase_receipt",
    )
    move_stock_many(
        lines=[
            MovementLine(
                variant_id=variant.id,
                location_id=location.id,
                quantity_delta=Decimal("-3.000"),
            )
        ],
        reason="sale_shipment",
    )

    level = StockLevel.objects.get(variant=variant, location=location)
    assert level.on_hand == Decimal("7.000")

    return {"variant": variant, "location": location, "level": level}


def test_reconciliation_detects_deliberate_corruption(setup_reconciliation_item):
    """Test reconciliation command detects when a StockLevel row has been corrupted."""
    variant = setup_reconciliation_item["variant"]
    location = setup_reconciliation_item["location"]

    # Deliberately corrupt the cached on_hand value
    StockLevel.objects.filter(variant=variant, location=location).update(on_hand=Decimal("999.000"))

    out = io.StringIO()
    err = io.StringIO()

    # Running reconcile without --repair must exit with code 1 and output the discrepancy
    with pytest.raises(SystemExit) as exc_info:
        call_command("reconcile_stock", stdout=out, stderr=err)

    assert exc_info.value.code == 1
    error_output = err.getvalue()
    assert "DISCREPANCY" in error_output
    assert "cached=999.000 vs ledger=7.000" in error_output


def test_reconciliation_repairs_corruption_and_audits(setup_reconciliation_item):
    """Test reconciliation with --repair restores correct balance and writes audit record."""
    variant = setup_reconciliation_item["variant"]
    location = setup_reconciliation_item["location"]

    # Corrupt on_hand to 42.000
    StockLevel.objects.filter(variant=variant, location=location).update(on_hand=Decimal("42.000"))

    out = io.StringIO()
    err = io.StringIO()

    # Run with --repair
    call_command("reconcile_stock", "--repair", stdout=out, stderr=err)

    # Verify StockLevel is repaired back to ground truth (7.000)
    level = StockLevel.objects.get(variant=variant, location=location)
    assert level.on_hand == Decimal("7.000")

    # Verify AuditLog was recorded
    audit = AuditLog.objects.filter(
        action="stock_level:repaired",
        entity_id=f"{variant.id}:{location.id}",
    ).first()
    assert audit is not None
    assert audit.diff_json["old_on_hand"] == "42.000"
    assert audit.diff_json["new_on_hand"] == "7.000"

    # Subsequent run must report clean
    out_clean = io.StringIO()
    call_command("reconcile_stock", stdout=out_clean)
    assert "Reconciliation clean" in out_clean.getvalue()
