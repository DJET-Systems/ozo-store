"""Tests for storefront engine views, dynamic presets, cart mutations, and warranty checks."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from apps.catalog.models import Category, Product, Variant
from apps.core.models import StoreSettings
from apps.inventory.models import Location, SerialUnit


@pytest.fixture
def catalog_fixture(db: None) -> dict[str, Product | Variant | Category]:
    """Create sample categories, products, and variants for storefront testing."""
    cat = Category.objects.create(
        name_en="Laptops & Computers",
        name_ar="أجهزة الكمبيوتر المحمولة",
        slug="laptops",
    )
    prod = Product.objects.create(
        handle="thinkpad-x1-carbon",
        title_en="ThinkPad X1 Carbon Gen 11",
        title_ar="لينوفو ثينك باد إكس 1 كاربون",
        description_en="Ultra-light enterprise laptop with Intel Core i7.",
        description_ar="كمبيوتر محمول خفيف الوزن للأعمال بمعالج إنتل كور i7.",
        category=cat,
        primary_brand="Lenovo",
        status="active",
    )
    v1 = Variant.objects.create(
        product=prod,
        sku="TP-X1C-16G",
        title_en="16GB RAM / 512GB SSD",
        title_ar="16 جيجا رام / 512 جيجا",
        price_amount=4800000,  # 48,000.00 EGP
        compare_at_price_amount=5200000,
        cost_amount=4100000,
        condition="new",
        warranty_months=24,
    )
    v2 = Variant.objects.create(
        product=prod,
        sku="TP-X1C-32G",
        title_en="32GB RAM / 1TB SSD",
        title_ar="32 جيجا رام / 1 تيرابايت",
        price_amount=5800000,  # 58,000.00 EGP
        cost_amount=5000000,
        condition="new",
        warranty_months=24,
    )
    return {"category": cat, "product": prod, "v1": v1, "v2": v2}


@pytest.mark.django_db
def test_storefront_home_default_preset(client: Client, catalog_fixture: dict[str, Any]) -> None:
    """Home view renders 200 OK with default preset sections."""
    resp = client.get("/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "DJET Store" in content
    assert "thinkpad-x1-carbon" in content
    assert "48000.00 EGP" in content


@pytest.mark.django_db
def test_storefront_live_preset_query_param(
    client: Client, catalog_fixture: dict[str, Any]
) -> None:
    """Live ?preset= param overlays vertical tokens and sections without mutating DB."""
    settings = StoreSettings.get_solo()
    assert settings.active_preset == "general"

    # Preview electronics preset
    resp = client.get("/?preset=electronics")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "--accent: #1D4ED8" in content  # Electronics blue accent

    # Verify persistent DB settings remain general
    settings.refresh_from_db()
    assert settings.active_preset == "general"

    # Preview food preset
    resp_food = client.get("/?preset=food")
    assert resp_food.status_code == 200
    content_food = resp_food.content.decode("utf-8")
    assert "--accent: #C2410C" in content_food  # Food rustic orange accent
    assert "Menu Sections" in content_food


@pytest.mark.django_db
def test_category_listing_view(client: Client, catalog_fixture: dict[str, Any]) -> None:
    """Category view displays category header and filtered products."""
    resp = client.get("/c/laptops/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "laptops" in content
    assert "thinkpad-x1-carbon" in content


@pytest.mark.django_db
def test_product_detail_view(client: Client, catalog_fixture: dict[str, Any]) -> None:
    """Product detail page displays title, prices, installments, and WhatsApp inquiry."""
    store = StoreSettings.get_solo()
    store.whatsapp_number = "+20 102 664 6657"
    store.save()

    resp = client.get("/p/thinkpad-x1-carbon/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "thinkpad-x1-carbon" in content
    assert "48000.00 EGP" in content
    assert "Lenovo" in content
    # Number is normalised to digits and the prefilled message is URL-encoded.
    assert "https://wa.me/201026646657?text=Hello%21%20I%20am%20inquiring" in content


@pytest.mark.django_db
def test_product_detail_has_no_placeholder_whatsapp(
    client: Client, catalog_fixture: dict[str, Any]
) -> None:
    """Without a configured number, no WhatsApp link is rendered (never a placeholder)."""
    resp = client.get("/p/thinkpad-x1-carbon/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "wa.me" not in content
    assert "201000000000" not in content


@pytest.mark.django_db
def test_cart_add_and_update_standard_form(client: Client, catalog_fixture: dict[str, Any]) -> None:
    """Standard POST to add and update cart items with session persistence."""
    # Add to cart
    resp_add = client.post(
        "/cart/add/",
        {"sku": "TP-X1C-16G", "quantity": "2", "next": "/cart/"},
        follow=True,
    )
    assert resp_add.status_code == 200
    content = resp_add.content.decode("utf-8")
    assert "thinkpad-x1-carbon" in content
    assert "96000.00 EGP" in content

    # Increase quantity
    resp_inc = client.post(
        "/cart/update/",
        {"sku": "TP-X1C-16G", "action": "increase"},
        follow=True,
    )
    assert resp_inc.status_code == 200
    assert "144000.00 EGP" in resp_inc.content.decode("utf-8")

    # Remove item
    resp_rem = client.post(
        "/cart/update/",
        {"sku": "TP-X1C-16G", "action": "remove"},
        follow=True,
    )
    assert resp_rem.status_code == 200
    assert "Your cart is currently empty" in resp_rem.content.decode("utf-8")


@pytest.mark.django_db
def test_cart_add_htmx_partial(client: Client, catalog_fixture: dict[str, Any]) -> None:
    """HTMX cart addition returns lightweight counter badge fragment."""
    resp = client.post(
        "/cart/add/",
        {"sku": "TP-X1C-16G", "quantity": "1"},
        HTTP_HX_REQUEST="true",
    )
    assert resp.status_code == 200
    assert 'id="cart-counter"' in resp.content.decode("utf-8")
    assert "1" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_public_warranty_check_non_pii_defense_in_depth(
    client: Client, catalog_fixture: dict[str, Any]
) -> None:
    """Warranty check renders device authenticity but NEVER leaks customer PII or cost data."""
    v1: Variant = catalog_fixture["v1"]
    loc = Location.objects.create(
        code="WH-01",
        name_en="Central Warehouse",
        name_ar="المستودع الرئيسي",
    )
    unit = SerialUnit.objects.create(
        variant=v1,
        location=loc,
        serial_number="SN-TP-X1C-9901",
        status="available",
    )

    resp = client.get(f"/warranty-check/?serial={unit.serial_number}")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")

    # Public device authenticity is shown
    assert "Verified Genuine Unit" in content
    assert "SN-TP-X1C-9901" in content
    assert "24 Months" in content

    # SECURITY INVARIANT: No cost amount or sensitive internal data in public view
    assert "41000" not in content
    assert "cost_amount" not in content
    assert "Central Warehouse" not in content  # internal warehouse not leaked


@pytest.mark.django_db
def test_public_warranty_check_not_found(client: Client) -> None:
    """Unknown serial returns polite not found message."""
    resp = client.get("/warranty-check/?serial=INVALID-SERIAL-123")
    assert resp.status_code == 200
    assert "No Record Found" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_order_track_view(client: Client) -> None:
    """Order track view renders lookup form and status timeline."""
    resp = client.get("/track/?order_ref=ORD-2026-901&phone=01000000000")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "Shipment In Transit" in content
    assert "ORD-2026-901" in content
