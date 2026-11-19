"""Database-level immutability tests verifying PostgreSQL triggers protect append-only tables."""

from decimal import Decimal

import pytest
from django.db import DatabaseError, connection, transaction

from apps.catalog.models import Category, Product, Variant
from apps.core.models import AuditLog
from apps.inventory.models import Location
from apps.inventory.services import MovementLine, move_stock_many


@pytest.fixture
def sample_movement_and_audit(db):
    cat = Category.objects.create(name_en="Immutability", name_ar="ثبات", slug="immutability")
    prod = Product.objects.create(handle="imm-p1", title_en="P1", title_ar="م1", category=cat)
    var = Variant.objects.create(product=prod, sku="IMM-001", price_amount=1000)
    loc = Location.objects.create(code="IMM_LOC", name_en="Imm Loc", name_ar="موقع ثبات")

    movements = move_stock_many(
        lines=[
            MovementLine(
                variant_id=var.id,
                location_id=loc.id,
                quantity_delta=Decimal("5.000"),
            )
        ],
        reason="opening_balance",
    )
    movement = movements[0]

    audit = AuditLog.log_action(
        action="test:action",
        entity_type="Test",
        entity_id="1",
        diff={"field": "value"},
    )

    return {"movement": movement, "audit": audit}


def test_stock_movement_update_forbidden_by_trigger(sample_movement_and_audit):
    """Test that direct UPDATE on inventory_stock_movement is blocked by PostgreSQL trigger."""
    if connection.vendor != "postgresql":
        pytest.skip("Immutable trigger requires PostgreSQL backend.")

    movement = sample_movement_and_audit["movement"]

    with (
        pytest.raises(DatabaseError, match="Table inventory_stock_movement is append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE inventory_stock_movement SET quantity_delta = 99 WHERE id = %s",
            [movement.id],
        )


def test_stock_movement_delete_forbidden_by_trigger(sample_movement_and_audit):
    """Test that direct DELETE on inventory_stock_movement is blocked by PostgreSQL trigger."""
    if connection.vendor != "postgresql":
        pytest.skip("Immutable trigger requires PostgreSQL backend.")

    movement = sample_movement_and_audit["movement"]

    with (
        pytest.raises(DatabaseError, match="Table inventory_stock_movement is append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "DELETE FROM inventory_stock_movement WHERE id = %s",
            [movement.id],
        )


def test_audit_log_update_forbidden_by_trigger(sample_movement_and_audit):
    """Test that direct UPDATE on core_audit_log is blocked by PostgreSQL trigger."""
    if connection.vendor != "postgresql":
        pytest.skip("Immutable trigger requires PostgreSQL backend.")

    audit = sample_movement_and_audit["audit"]

    with (
        pytest.raises(DatabaseError, match="Table core_audit_log is append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE core_audit_log SET action = 'tampered' WHERE id = %s",
            [audit.id],
        )


def test_audit_log_delete_forbidden_by_trigger(sample_movement_and_audit):
    """Test that direct DELETE on core_audit_log is blocked by PostgreSQL trigger."""
    if connection.vendor != "postgresql":
        pytest.skip("Immutable trigger requires PostgreSQL backend.")

    audit = sample_movement_and_audit["audit"]

    with (
        pytest.raises(DatabaseError, match="Table core_audit_log is append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "DELETE FROM core_audit_log WHERE id = %s",
            [audit.id],
        )
