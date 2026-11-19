"""Management command to activate a vertical storefront preset."""

from __future__ import annotations

import argparse
from typing import Any

from django.core.management.base import BaseCommand

from apps.presets.services import apply_preset, list_presets


class Command(BaseCommand):
    help = "Activate a vertical storefront preset and configure brand design tokens."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "preset_code",
            type=str,
            nargs="?",
            default="",
            help="Preset code to apply: general, electronics, clothing, food, minimarket.",
        )
        parser.add_argument(
            "--preset",
            dest="preset_flag",
            type=str,
            default="",
            help="Optional flag alias for preset code.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all registered preset packages.",
        )
        parser.add_argument(
            "--demo-data",
            action="store_true",
            help="Seed starter categories and demo catalog structure.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        code = options.get("preset_flag") or options.get("preset_code")
        if options["list"] or not code:
            self.stdout.write(self.style.NOTICE("Available DJET Storefront Presets:"))
            for p in list_presets():
                self.stdout.write(f" - {p['code']}: {p['name']} ({p['description']})")
            return

        demo = options["demo_data"]

        self.stdout.write(f"Applying preset '{code}' (seed_demo={demo})...")
        definition = apply_preset(code, load_demo_data=demo)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully activated preset '{definition['code']}' ({definition['name']}). "
                f"Configured {len(definition.get('tokens', {}))} design tokens and "
                f"{len(definition.get('home_sections', []))} home sections."
            )
        )
