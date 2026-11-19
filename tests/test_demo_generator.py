"""Tests for the deterministic 5,000-product electronics demo generator."""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

from apps.catalog.demo_generator import (
    DEMO_CSV_COLUMNS,
    iter_demo_catalog_rows,
    write_demo_catalog_csv,
)

SAMPLES_IMPORT_CSV = Path(__file__).resolve().parent.parent / "samples" / "products_import.csv"


def _is_valid_ean13(code: str) -> bool:
    if len(code) != 13 or not code.isdigit():
        return False
    odd_sum = sum(int(code[i]) for i in range(0, 12, 2))
    even_sum = sum(int(code[i]) for i in range(1, 12, 2))
    expected = (10 - ((odd_sum + 3 * even_sum) % 10)) % 10
    return int(code[12]) == expected


def test_demo_generator_matches_sample_csv_header() -> None:
    """Generated CSV columns match samples/products_import.csv exactly."""
    with SAMPLES_IMPORT_CSV.open("r", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header == DEMO_CSV_COLUMNS


def test_demo_generator_is_deterministic() -> None:
    """Running with the same seed yields identical rows."""
    first = list(iter_demo_catalog_rows(products=100, seed=42))
    second = list(iter_demo_catalog_rows(products=100, seed=42))
    assert first == second


def test_demo_generator_emits_5000_products_with_valid_invariants(tmp_path: Path) -> None:
    """Generating 5,000 electronics products produces unique SKUs/barcodes and bilingual titles."""
    out = tmp_path / "demo_5000.csv"
    t0 = time.perf_counter()
    p_count, v_count = write_demo_catalog_csv(out, products=5000, seed=42)
    elapsed = time.perf_counter() - t0

    assert p_count == 5000
    assert v_count > 5000
    assert elapsed < 3.0

    skus: set[str] = set()
    barcodes: set[str] = set()
    handles: set[str] = set()
    conditions: set[str] = set()
    tracking_modes: set[str] = set()

    with out.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert row["product_handle"]
            assert row["title_en"]
            assert row["title_ar"]
            assert row["sku"] not in skus
            assert row["barcode"] not in barcodes
            assert _is_valid_ean13(row["barcode"])
            skus.add(row["sku"])
            barcodes.add(row["barcode"])
            handles.add(row["product_handle"])
            conditions.add(row["condition"])
            tracking_modes.add(row["tracking_mode"])

    assert len(handles) == 5000
    assert {"new", "used_a", "used_b", "used_c", "refurbished"}.issubset(conditions)
    assert {"serial", "none"} == tracking_modes


def test_demo_generator_streams_to_text_io() -> None:
    """write_demo_catalog_csv accepts an in-memory StringIO stream."""
    buf = io.StringIO()
    p_count, v_count = write_demo_catalog_csv(buf, products=10, seed=7)
    assert p_count == 10
    assert v_count >= 10
    lines = buf.getvalue().strip().splitlines()
    assert len(lines) == v_count + 1
