"""Tests for Vertical Preset engine, alias normalization, and activation."""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from apps.core.models import AuditLog, StoreSettings
from apps.presets.services import (
    apply_preset,
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
