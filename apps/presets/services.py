"""Vertical Presets service boundary: definition loader, theme tokens, and activation."""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

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


# ---------------------------------------------------------------------------
# Client brand profiles
#
# A brand profile is a per-client overlay on top of one vertical preset. It
# keeps client identity (logo, palette, contact data, home composition) out of
# the shared vertical definitions so upstream template updates merge cleanly.
# Selected with the DJET_BRAND_PROFILE setting; empty means "no overlay".
# ---------------------------------------------------------------------------

BRANDS_DIR = Path(__file__).resolve().parent / "brands"
_BRAND_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_BRAND_REQUIRED_KEYS = ("code", "base_preset", "brand")


def get_brand_profile(code: str | None = None) -> dict[str, Any] | None:
    """Load the configured client brand profile, or None when none is configured.

    Fails closed: a configured-but-invalid profile raises ImproperlyConfigured
    instead of silently rendering an unbranded store.
    """
    raw = getattr(django_settings, "DJET_BRAND_PROFILE", "") if code is None else code
    brand_code = (raw or "").strip().lower()
    if not brand_code:
        return None
    if not _BRAND_CODE_RE.fullmatch(brand_code):
        # Reject anything that could escape BRANDS_DIR (e.g. "../", absolute paths).
        raise ImproperlyConfigured(f"Invalid DJET_BRAND_PROFILE value: {brand_code!r}")

    profile_file = BRANDS_DIR / f"{brand_code}.json"
    if not profile_file.is_file():
        raise ImproperlyConfigured(f"Brand profile not found: {profile_file.name}")

    with profile_file.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    missing = [key for key in _BRAND_REQUIRED_KEYS if key not in data]
    if missing:
        raise ImproperlyConfigured(f"Brand profile {brand_code!r} is missing keys: {missing}")
    return data


def get_effective_definition(code: str) -> dict[str, Any]:
    """Return the vertical preset definition with the client brand overlay applied.

    The overlay only applies when the requested vertical matches the profile's
    ``base_preset``, so ``?preset=food`` sales previews still render untouched.
    """
    definition = get_preset_definition(code)
    profile = get_brand_profile()
    if profile is None or normalize_preset_code(profile["base_preset"]) != definition["code"]:
        return definition

    merged = dict(definition)
    merged["tokens"] = {**definition.get("tokens", {}), **profile.get("tokens", {})}
    merged["card_flags"] = {**definition.get("card_flags", {}), **profile.get("card_flags", {})}
    for key in ("home_sections", "starter_categories", "name", "description"):
        if key in profile:
            merged[key] = profile[key]
    merged["brand"] = profile["brand"]
    merged["brand_code"] = profile["code"]
    return merged


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
    definition = get_effective_definition(code)
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
        diff={
            "preset": canonical,
            "brand_profile": definition.get("brand_code", ""),
            "demo_data_seeded": load_demo_data,
        },
    )

    return definition
