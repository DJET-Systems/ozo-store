"""Management command to generate a deterministic electronics demo catalog CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.catalog.demo_generator import write_demo_catalog_csv


class Command(BaseCommand):
    """Emit a deterministic electronics-style catalog CSV matching samples/products_import.csv."""

    help = "Generate deterministic electronics-style demo catalog CSV (default 5,000 products)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Define CLI flags for product count, seed, and output path."""
        parser.add_argument("--products", type=int, default=5000)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--max-variants-per-product", type=int, default=None)
        parser.add_argument("--output", type=str, default="")

    def handle(self, *args: Any, **options: Any) -> None:
        """Write CSV to --output or stdout."""
        products = int(options["products"])
        seed = int(options["seed"])
        max_v = options["max_variants_per_product"]
        output_arg = str(options["output"]).strip()

        if output_arg:
            out_path = Path(output_arg)
            p_count, v_count = write_demo_catalog_csv(
                out_path,
                products=products,
                seed=seed,
                max_variants_per_product=max_v,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Generated {p_count} products ({v_count} variants) at {out_path}"
                )
            )
        else:
            write_demo_catalog_csv(
                self.stdout,
                products=products,
                seed=seed,
                max_variants_per_product=max_v,
            )
