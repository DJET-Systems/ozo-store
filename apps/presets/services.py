"""Vertical Presets service boundary: definition loader, theme tokens, and activation."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from apps.catalog.models import Category
from apps.core.models import AuditLog, StoreSettings

PRESET_ALIASES: dict[str, str] = {
    "fashion": "clothing",
    "apparel": "clothing",
    "restaurant": "food",
    "kitchen": "food",
    "groceries": "minimarket",
    "supermarket": "minimarket",
    "grocery": "minimarket",
    "phones": "electronics",
    "gadgets": "electronics",
}

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


def normalize_preset_code(code: str) -> str:
    """Resolve aliases into canonical preset names."""
    canonical = code.strip().lower()
    return PRESET_ALIASES.get(canonical, canonical)


def get_preset_definition(code: str) -> dict[str, Any]:
    """Load JSON definition for a given preset code."""
    canonical = normalize_preset_code(code)
    def_file = DEFINITIONS_DIR / canonical / "preset.json"

    if not def_file.exists():
        # Fallback to general preset
        def_file = DEFINITIONS_DIR / "general" / "preset.json"

    with def_file.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def list_presets() -> list[dict[str, Any]]:
    """Enumerate all available preset definitions."""
    presets: list[dict[str, Any]] = []
    codes = ["general", "electronics", "clothing", "food", "minimarket"]
    for code in codes:
        with contextlib.suppress(Exception):
            presets.append(get_preset_definition(code))
    return presets


def apply_preset(
    code: str,
    *,
    load_demo_data: bool = False,
    actor: Any = None,
) -> dict[str, Any]:
    """Activate a vertical preset, updating tokens, home sections, and starter data."""
    definition = get_preset_definition(code)
    canonical = definition["code"]

    settings = StoreSettings.get_settings()
    settings.active_preset = canonical
    settings.brand_tokens = definition.get("tokens", {})
    settings.home_sections = definition.get("home_sections", [])
    settings.primary_language = definition.get("default_language", "ar")
    settings.save(
        update_fields=[
            "active_preset",
            "brand_tokens",
            "home_sections",
            "primary_language",
        ]
    )

    if load_demo_data:
        # Seed starter categories if not present
        starter_cats = definition.get("starter_categories", [])
        for cat_data in starter_cats:
            slug = cat_data["slug"]
            if not Category.objects.filter(slug=slug).exists():
                Category.objects.create(
                    slug=slug,
                    name_en=cat_data["name_en"],
                    name_ar=cat_data["name_ar"],
                )

    AuditLog.log_action(
        action="preset:applied",
        entity_type="Preset",
        entity_id=canonical,
        actor=actor,
        diff={"preset": canonical, "demo_data_seeded": load_demo_data},
    )

    return definition
