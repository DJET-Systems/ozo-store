"""Tests verifying sensitive cost, margin, and purchase price masking across HTML and CSV."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.catalog.models import Category, Product, Variant
from apps.core.models import Role, StaffUser
from apps.core.rbac import sync_builtin_roles
from apps.inventory.models import Location, StockLevel


@pytest.fixture(autouse=True)
def setup_roles_and_catalog(db: None, settings: Any) -> None:
    settings.ROOT_URLCONF = "config.urls_dashboard"
    sync_builtin_roles()

    category = Category.objects.create(
        name_en="Coffee",
        name_ar="قهوة",
        slug="coffee",
    )
    product = Product.objects.create(
        title_en="Specialty Geisha Beans",
        title_ar="حبوب قهوة جيشا فاخرة",
        handle="specialty-geisha-beans",
        category=category,
        status="active",
    )
    variant = Variant.objects.create(
        product=product,
        sku="GEISHA-250G",
        title_en="250g Whole Bean",
        title_ar="250 جرام حبوب كاملة",
        price_amount=25000,  # 250.00 EGP
        cost_amount=15000,  # 150.00 EGP (Sensitive field)
    )

    location = Location.objects.create(
        code="CAIRO-HQ",
        name_en="Cairo Central Warehouse",
        name_ar="مستودع القاهرة المركزي",
        priority=1,
    )
    StockLevel.objects.create(
        variant=variant,
        location=location,
        on_hand=Decimal("50.000"),
        avg_unit_cost=Decimal("15000.0000"),  # 150.00 EGP in minor units (Sensitive field)
    )


@pytest.mark.django_db
def test_cashier_cannot_see_costs_in_products_or_inventory_html() -> None:
    """Staff without 'reports.view_costs' receives masked values in HTML."""
    cashier_role = Role.objects.get(name="Cashier")
    cashier = StaffUser.objects.create_user(
        username="cashier_mask_test",
        email="cashier@example.com",
        password="ValidPassword123!",
        role=cashier_role,
        is_staff=True,
    )

    client = Client()
    client.force_login(cashier)

    # 1. Products list: retail price is visible, cost amount 150.00 is masked
    prod_resp = client.get(reverse("dashboard-products"))
    assert prod_resp.status_code == 200
    prod_html = prod_resp.content.decode()
    assert "250.00" in prod_html
    assert "150.00" not in prod_html
    assert "*** RESTRICTED ***" in prod_html

    # 2. Inventory list: location & SKU visible, avg unit cost is masked
    inv_resp = client.get(reverse("dashboard-inventory"))
    assert inv_resp.status_code == 200
    inv_html = inv_resp.content.decode()
    assert "CAIRO-HQ" in inv_html
    assert "GEISHA-250G" in inv_html
    assert "15000" not in inv_html
    assert "*** RESTRICTED ***" in inv_html


@pytest.mark.django_db
def test_csv_export_completely_strips_cost_columns_when_cost_permission_missing() -> None:
    """When exporting catalog or stock without 'reports.view_costs', columns are omitted."""
    # Create role with data.export but WITHOUT reports.view_costs
    custom_role = Role.objects.create(
        name="ExporterNoCosts",
        description="Can export data without cost visibility",
        permissions=["data.export", "catalog.view", "inventory.view"],
    )
    user = StaffUser.objects.create_user(
        username="export_user",
        email="exporter@example.com",
        password="ValidPassword123!",
        role=custom_role,
        is_staff=True,
    )

    client = Client()
    client.force_login(user)

    # Catalog export
    cat_resp = client.get(reverse("dashboard-export", kwargs={"dataset": "catalog"}))
    assert cat_resp.status_code == 200
    csv_text = b"".join(cat_resp.streaming_content).decode("utf-8")  # type: ignore[attr-defined]

    assert "Product Title (EN)" in csv_text
    assert "Retail Price (EGP)" in csv_text
    # Cost and margin columns must be completely absent from header and rows!
    assert "Cost Price (EGP)" not in csv_text
    assert "Gross Margin (EGP)" not in csv_text
    assert "150.00" not in csv_text

    # Inventory export
    inv_resp = client.get(reverse("dashboard-export", kwargs={"dataset": "inventory"}))
    assert inv_resp.status_code == 200
    inv_csv_text = b"".join(inv_resp.streaming_content).decode("utf-8")  # type: ignore[attr-defined]

    assert "Location Code" in inv_csv_text
    assert "On Hand" in inv_csv_text
    assert "Avg Unit Cost (EGP)" not in inv_csv_text
    assert "150.00" not in inv_csv_text


@pytest.mark.django_db
def test_privileged_accountant_and_owner_see_all_cost_data() -> None:
    """Accountant and Owner with 'reports.view_costs' see real cost prices and margins."""
    accountant_role = Role.objects.get(name="Accountant")
    accountant = StaffUser.objects.create_user(
        username="acct_user",
        email="acct@example.com",
        password="ValidPassword123!",
        role=accountant_role,
        is_staff=True,
    )

    client = Client()
    client.force_login(accountant)

    # Reports screen has COGS and Margin cards
    rep_resp = client.get(reverse("dashboard-reports"))
    assert rep_resp.status_code == 200
    rep_html = rep_resp.content.decode()
    assert "Total COGS" in rep_html
    assert "Gross Margin" in rep_html
    assert "Restricted Field" not in rep_html

    # Catalog export contains cost and margin columns
    cat_resp = client.get(reverse("dashboard-export", kwargs={"dataset": "catalog"}))
    assert cat_resp.status_code == 200
    csv_text = b"".join(cat_resp.streaming_content).decode("utf-8")  # type: ignore[attr-defined]
    assert "Cost Price (EGP)" in csv_text
    assert "Gross Margin (EGP)" in csv_text
    assert "150.00" in csv_text
    assert "100.00" in csv_text  # 250 - 150 = 100.00 margin
