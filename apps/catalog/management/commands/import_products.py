"""Management command to bulk-import products and variants from CSV."""

from __future__ import annotations

import argparse
from typing import Any

from django.core.management.base import BaseCommand

from apps.catalog.services import import_products_from_csv


class Command(BaseCommand):
    help = "Bulk import catalog products and variants from a CSV file."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "csv_path",
            type=str,
            help="Path to the products import CSV file (e.g. samples/products_import.csv).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the import, validate records, and show diff without saving mutations.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        csv_path = options["csv_path"]
        dry_run = options["dry_run"]

        self.stdout.write(f"Initiating catalog import from: {csv_path} (dry_run={dry_run})")
        result = import_products_from_csv(csv_path, dry_run=dry_run)

        if result.errors:
            self.stderr.write(self.style.ERROR(f"Import encountered {len(result.errors)} errors:"))
            for err in result.errors:
                self.stderr.write(f" - {err}")

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Processed {result.total_rows} rows: "
                f"Products (+{result.products_created}, ~{result.products_updated}), "
                f"Variants (+{result.variants_created}, ~{result.variants_updated})."
            )
        )
