"""System checks for preset and client brand profile configuration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.core.checks import CheckMessage, Error, register
from django.core.exceptions import ImproperlyConfigured

from apps.presets.services import get_brand_profile, get_preset_definition, normalize_preset_code


@register()
def check_brand_profile(
    app_configs: Sequence[Any] | None = None,
    **kwargs: Any,
) -> list[CheckMessage]:
    """Surface a broken DJET_BRAND_PROFILE at deploy time instead of on first request."""
    try:
        profile = get_brand_profile()
    except (ImproperlyConfigured, ValueError) as exc:
        return [Error(str(exc), id="djet.E101")]
    if profile is None:
        return []

    base = normalize_preset_code(str(profile["base_preset"]))
    if get_preset_definition(base)["code"] != base:
        return [
            Error(
                f"Brand profile {profile['code']!r} extends unknown preset {base!r}.",
                id="djet.E102",
            )
        ]
    return []
