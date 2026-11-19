"""Tests for Vertical Preset engine, alias normalization, and activation."""

from __future__ import annotations

import io

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, override_settings

from apps.catalog.models import Category
from apps.core.models import AuditLog, StoreSettings
from apps.presets.checks import check_brand_profile
from apps.presets.services import (
    apply_preset,
    get_brand_profile,
    get_effective_definition,
    get_preset_definition,
    list_presets,
    normalize_preset_code,
)


def test_list_presets_loads_all_definitions() -> None:
    """All 5 declarative vertical presets must be loaded and available."""
    presets = list_presets()
    expected_codes = {"general", "electronics", "clothing", "food", "minimarket"}
    codes = {p["code"] for p in presets}
    assert codes == expected_codes

    for defn in presets:
        assert defn["code"] in expected_codes
        assert defn["name"] != ""
        assert "home_sections" in defn
        assert "tokens" in defn
        assert "card_flags" in defn


def test_normalize_preset_aliases() -> None:
    """Merchant industry synonyms correctly normalize to standard preset codes."""
    assert normalize_preset_code("fashion") == "clothing"
    assert normalize_preset_code("apparel") == "clothing"
    assert normalize_preset_code("restaurant") == "food"
    assert normalize_preset_code("kitchen") == "food"
    assert normalize_preset_code("grocery") == "minimarket"
    assert normalize_preset_code("supermarket") == "minimarket"
    assert normalize_preset_code("phones") == "electronics"
    assert normalize_preset_code("gadgets") == "electronics"
    assert normalize_preset_code("unknown_vertical") == "unknown_vertical"


def test_get_preset_definition_fallback() -> None:
    """Unknown preset names safely fallback to the general preset."""
    defn = get_preset_definition("nonexistent")
    assert defn["code"] == "general"


@pytest.mark.django_db
def test_apply_preset_updates_settings_and_logs_audit() -> None:
    """apply_preset modifies StoreSettings, tokens, and records audit trail."""
    settings = StoreSettings.get_solo()
    assert settings.active_preset == "general"

    applied = apply_preset("electronics", actor="admin@djet.test")
    assert applied["code"] == "electronics"

    settings.refresh_from_db()
    assert settings.active_preset == "electronics"
    assert settings.brand_tokens.get("--accent") == "#1D4ED8"
    assert len(settings.home_sections) > 0

    # Verify audit log entry
    audit = AuditLog.objects.filter(action="preset:applied").first()
    assert audit is not None
    assert audit.diff.get("preset") == "electronics"
    assert audit.actor_email == "admin@djet.test"


@pytest.mark.django_db
def test_apply_preset_management_command() -> None:
    """Management command manage.py apply_preset works with --list and --preset."""
    out_list = io.StringIO()
    call_command("apply_preset", "--list", stdout=out_list)
    output = out_list.getvalue()
    assert "Available DJET Storefront Presets" in output
    assert "electronics" in output

    out_apply = io.StringIO()
    call_command("apply_preset", "--preset", "clothing", stdout=out_apply)
    assert "Successfully activated preset 'clothing'" in out_apply.getvalue()

    settings = StoreSettings.get_solo()
    assert settings.active_preset == "clothing"


def test_ozo_brand_profile_overlays_electronics_preset() -> None:
    """When DJET_BRAND_PROFILE=ozo, electronics preset merges OZO brand tokens and sections."""
    with override_settings(DJET_BRAND_PROFILE="ozo"):
        defn = get_effective_definition("electronics")
        assert defn["code"] == "electronics"
        assert defn["brand_code"] == "ozo"
        assert defn["tokens"]["--accent"] == "#005CA9"
        assert defn["tokens"]["--brand-navy"] == "#0A1F5C"
        assert defn["brand"]["name_en"] == "OZO Shop"
        assert defn["brand"]["whatsapp"] == "201026646657"
        section_types = [s["type"] for s in defn["home_sections"]]
        assert "hero_brand" in section_types
        assert "service_promos" in section_types
        assert "repair_center" in section_types
        assert "brand_strip" in section_types
        assert "store_visit" in section_types

        # Non-matching verticals remain untouched for sales demo previews
        food_defn = get_effective_definition("food")
        assert food_defn["code"] == "food"
        assert "brand_code" not in food_defn
        assert food_defn["tokens"]["--accent"] == "#C2410C"


def test_brand_profile_rejects_path_traversal_and_missing_files() -> None:
    """get_brand_profile and check_brand_profile fail closed on invalid profile codes."""
    for bad_code in ("../etc/passwd", "ozo/../../secret", "UPPERCASE", "$bad"):
        with pytest.raises(ImproperlyConfigured):
            get_brand_profile(bad_code)

    with pytest.raises(ImproperlyConfigured):
        get_brand_profile("nonexistent_brand_profile")

    with override_settings(DJET_BRAND_PROFILE="../traversal"):
        errors = check_brand_profile()
        assert len(errors) == 1
        assert errors[0].id == "djet.E101"

    with override_settings(DJET_BRAND_PROFILE="ozo"):
        assert check_brand_profile() == []


@pytest.mark.django_db
def test_ozo_branded_storefront_renders_all_sections(client: Client) -> None:
    """Storefront home renders OZO Shop 20-year anniversary, repair centre, and Mokattam address."""
    with override_settings(DJET_BRAND_PROFILE="ozo"):
        apply_preset("electronics", load_demo_data=True, actor="architect@djet.online")
        assert Category.objects.filter(slug="playstation").exists()
        assert Category.objects.filter(slug="mobiles").exists()

        resp_ar = client.get("/")
        assert resp_ar.status_code == 200
        html_ar = resp_ar.content.decode("utf-8")
        assert "--accent: #005CA9" in html_ar
        assert "أوزو شوب" in html_ar
        assert "متستناش القبض" in html_ar
        assert "مركز صيانة أوزو" in html_ar
        assert "01026646657" in html_ar
        assert "https://www.instagram.com/ozo__shop/" in html_ar
        assert "https://www.facebook.com/OZOShopEgypt/" in html_ar
