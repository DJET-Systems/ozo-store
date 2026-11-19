"""Tests for Catalog CSV import, product/variant grouping, and zero-touch ledger isolation."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalog.models import Category, Product, Variant
from apps.catalog.services import import_products_from_csv, lookup_barcode
from apps.inventory.models import StockMovement

SAMPLE_CSV = "\n".join(
    [
        "handle,title_en,title_ar,category_path,sku,barcode,variant_title_en,variant_title_ar,"
        "price_egp,compare_at_egp,cost_egp,condition,unit,unit_step,weight_g,warranty_months",
        "iphone-15-pro,iPhone 15 Pro,آيفون 15 برو,Phones > Apple > Smartphones,IP15P-128-BLK,"
        "0195949038289,128GB Black,128 جيجا أسود,54000.00,58000.00,47000.00,new,piece,1.000,187,12",
        "iphone-15-pro,iPhone 15 Pro,آيفون 15 برو,Phones > Apple > Smartphones,IP15P-256-BLK,"
        "0195949038296,256GB Black,256 جيجا أسود,61000.00,,52000.00,new,piece,1.000,187,12",
        "egyptian-oranges,Fresh Baladi Oranges,برتقال بلدي طازج,Fresh Produce > Fruits,ORG-BLD-KG,"
        "622100000001,,الطازج,25.50,,18.00,new,kg,0.500,1000,0",
        "",
    ]
)


@pytest.mark.django_db
def test_import_products_dry_run_leaves_no_records() -> None:
    """Dry-run must roll back atomic transaction and leave 0 products and variants."""
    csv_file = io.StringIO(SAMPLE_CSV)
    result = import_products_from_csv(csv_file, dry_run=True)

    assert result.success is True
    assert result.created_products == 2
    assert result.created_variants == 3

    assert Product.objects.count() == 0
    assert Variant.objects.count() == 0
    assert Category.objects.count() == 0


@pytest.mark.django_db
def test_import_products_creates_hierarchy_and_variants() -> None:
    """Import creates nested categories and groups variants under matching product handle."""
    csv_file = io.StringIO(SAMPLE_CSV)
    result = import_products_from_csv(csv_file, dry_run=False)

    assert result.success is True
    assert result.created_products == 2
    assert result.created_variants == 3

    # Check category hierarchy: Phones > Apple > Smartphones
    cat_smartphones = Category.objects.get(name_en="Smartphones")
    assert cat_smartphones.parent is not None
    assert cat_smartphones.parent.name_en == "Apple"
    assert cat_smartphones.parent.parent is not None
    assert cat_smartphones.parent.parent.name_en == "Phones"

    # Check product grouping
    prod = Product.objects.get(handle="iphone-15-pro")
    assert prod.variants.count() == 2
    assert set(prod.variants.values_list("sku", flat=True)) == {
        "IP15P-128-BLK",
        "IP15P-256-BLK",
    }

    # Check pricing and monetary minor units
    v128 = prod.variants.get(sku="IP15P-128-BLK")
    assert v128.price_amount == 5400000  # 54,000.00 EGP = 5,400,000 piastres
    assert v128.compare_at_price_amount == 5800000
    assert v128.barcode == "0195949038289"
    assert v128.warranty_months == 12

    # Check produce item with unit step
    v_org = Variant.objects.get(sku="ORG-BLD-KG")
    assert v_org.unit == "kg"
    assert v_org.unit_step == Decimal("0.500")
    assert v_org.price_amount == 2550  # 25.50 EGP


@pytest.mark.django_db
def test_import_products_zero_touch_ledger_invariant() -> None:
    """Catalog CSV import must NEVER create stock ledger entries (ledger isolation)."""
    assert StockMovement.objects.count() == 0

    csv_file = io.StringIO(SAMPLE_CSV)
    import_products_from_csv(csv_file, dry_run=False)

    # Invariant: ledger entries must remain exactly zero
    assert StockMovement.objects.count() == 0


@pytest.mark.django_db
def test_lookup_barcode_service() -> None:
    """Barcode lookup finds variant by exact match or barcode."""
    csv_file = io.StringIO(SAMPLE_CSV)
    import_products_from_csv(csv_file, dry_run=False)

    # Lookup by barcode
    found = lookup_barcode("0195949038289")
    assert found is not None
    assert found["sku"] == "IP15P-128-BLK"

    # Fallback lookup by SKU
    found_sku = lookup_barcode("ORG-BLD-KG")
    assert found_sku is not None
    assert found_sku["sku"] == "ORG-BLD-KG"

    # Non-existent
    assert lookup_barcode("UNKNOWN-999999") is None


@pytest.mark.django_db
def test_import_products_management_command(tmp_path: pytest.TempPathFactory) -> None:
    """Management command manage.py import_products runs successfully."""
    p = tmp_path / "test_import.csv"  # type: ignore[operator]
    p.write_text(SAMPLE_CSV, encoding="utf-8")

    out = io.StringIO()
    call_command("import_products", str(p), stdout=out)
    output = out.getvalue()

    assert "Products (+2" in output
    assert "Variants (+3" in output
    assert Product.objects.count() == 2
