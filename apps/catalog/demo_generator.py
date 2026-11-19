"""Deterministic electronics-shaped demo catalog generator (Phase 001 / 004 / 015)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

DEMO_CSV_COLUMNS = [
    "product_handle",
    "sku",
    "barcode",
    "title_en",
    "title_ar",
    "category_path",
    "brand",
    "condition",
    "unit",
    "unit_step",
    "tracking_mode",
    "price_egp",
    "compare_at_price_egp",
    "cost_egp",
    "weight_g",
    "option1_name",
    "option1_value",
    "option2_name",
    "option2_value",
    "warranty_months",
    "status",
    "reorder_point",
    "reorder_quantity",
]


@dataclass(frozen=True)
class _Archetype:
    code: str
    category_path: str
    en_prefix: str
    ar_prefix: str
    tracking_mode: str
    unit: str
    unit_step: str
    base_price_egp: int
    weight_g: int
    warranty_months: int
    allow_used: bool
    option1_name: str
    option1_values: tuple[str, ...]
    option2_name: str
    option2_values: tuple[str, ...]


_BRANDS = (
    ("Acme", "أكمي"),
    ("Nova", "نوفا"),
    ("Linko", "لينكو"),
    ("Netix", "نيتيكس"),
    ("VoltEdge", "فولت إيدج"),
    ("SightGuard", "سايت جارد"),
    ("CoreByte", "كور بايت"),
    ("ZetaTech", "زيتا تك"),
)

_ARCHETYPES: tuple[_Archetype, ...] = (
    _Archetype(
        code="PH",
        category_path="Mobile & Tablet > Mobile Phones",
        en_prefix="Smartphone",
        ar_prefix="هاتف ذكي",
        tracking_mode="serial",
        unit="piece",
        unit_step="1",
        base_price_egp=9500,
        weight_g=195,
        warranty_months=12,
        allow_used=True,
        option1_name="Storage",
        option1_values=("128GB", "256GB"),
        option2_name="Colour",
        option2_values=("Black", "Blue"),
    ),
    _Archetype(
        code="TB",
        category_path="Mobile & Tablet > Tablets",
        en_prefix="Tablet",
        ar_prefix="تابلت",
        tracking_mode="serial",
        unit="piece",
        unit_step="1",
        base_price_egp=8200,
        weight_g=460,
        warranty_months=12,
        allow_used=True,
        option1_name="Storage",
        option1_values=("64GB", "128GB"),
        option2_name="Colour",
        option2_values=("Space Grey", "Silver"),
    ),
    _Archetype(
        code="LT",
        category_path="Computer > Laptops",
        en_prefix="Laptop",
        ar_prefix="لاب توب",
        tracking_mode="serial",
        unit="piece",
        unit_step="1",
        base_price_egp=22000,
        weight_g=1650,
        warranty_months=12,
        allow_used=True,
        option1_name="RAM",
        option1_values=("8GB", "16GB"),
        option2_name="Storage",
        option2_values=("512GB",),
    ),
    _Archetype(
        code="RM",
        category_path="Computer > PC Components > RAM",
        en_prefix="DDR4 Desktop Memory",
        ar_prefix="ذاكرة رام مكتبية",
        tracking_mode="none",
        unit="piece",
        unit_step="1",
        base_price_egp=1400,
        weight_g=85,
        warranty_months=24,
        allow_used=True,
        option1_name="Capacity",
        option1_values=("8GB", "16GB"),
        option2_name="",
        option2_values=("",),
    ),
    _Archetype(
        code="SD",
        category_path="Computer > PC Components > Storage SSD",
        en_prefix="NVMe SSD Drive",
        ar_prefix="قرص تخزين SSD",
        tracking_mode="serial",
        unit="piece",
        unit_step="1",
        base_price_egp=2100,
        weight_g=55,
        warranty_months=24,
        allow_used=False,
        option1_name="Capacity",
        option1_values=("500GB", "1TB"),
        option2_name="",
        option2_values=("",),
    ),
    _Archetype(
        code="CAM",
        category_path="Security & Surveillance > CCTV Cameras",
        en_prefix="HD Surveillance Camera",
        ar_prefix="كاميرا مراقبة",
        tracking_mode="serial",
        unit="piece",
        unit_step="1",
        base_price_egp=1350,
        weight_g=380,
        warranty_months=12,
        allow_used=False,
        option1_name="Resolution",
        option1_values=("2MP", "5MP"),
        option2_name="",
        option2_values=("",),
    ),
    _Archetype(
        code="CBL",
        category_path="Mobile & Tablet > Accessories > Charger Cables",
        en_prefix="Braided USB-C Cable",
        ar_prefix="كابل شحن USB-C",
        tracking_mode="none",
        unit="piece",
        unit_step="1",
        base_price_egp=140,
        weight_g=45,
        warranty_months=6,
        allow_used=False,
        option1_name="Length",
        option1_values=("1m", "2m"),
        option2_name="",
        option2_values=("",),
    ),
    _Archetype(
        code="NW",
        category_path="Network > Network Accessories",
        en_prefix="Cat6 Connector Pack",
        ar_prefix="عبوة موصلات شبكة Cat6",
        tracking_mode="none",
        unit="pack",
        unit_step="1",
        base_price_egp=185,
        weight_g=300,
        warranty_months=0,
        allow_used=False,
        option1_name="",
        option1_values=("",),
        option2_name="",
        option2_values=("",),
    ),
)

_CONDITION_LABELS: dict[str, tuple[str, str, Decimal, int]] = {
    "new": ("", "", Decimal("1.00"), 12),
    "used_a": (" (Used Grade A)", " (مستعمل درجة أ)", Decimal("0.72"), 3),
    "used_b": (" (Used Grade B)", " (مستعمل درجة ب)", Decimal("0.60"), 1),
    "used_c": (" (Used Grade C)", " (مستعمل درجة ج)", Decimal("0.48"), 1),
    "refurbished": (" (Refurbished)", " (مجدد)", Decimal("0.80"), 6),
}

_AR_OPTION_LABELS: dict[str, str] = {
    "Black": "أسود",
    "Blue": "أزرق",
    "Space Grey": "رمادي",
    "Silver": "فضي",
    "1m": "1 متر",
    "2m": "2 متر",
}


def _ean13_from_seq(seq: int) -> str:
    """Return a deterministic valid 13-digit EAN barcode from a sequence integer."""
    body = f"6229{seq:08d}"
    odd_sum = sum(int(body[i]) for i in range(0, 12, 2))
    even_sum = sum(int(body[i]) for i in range(1, 12, 2))
    check = (10 - ((odd_sum + 3 * even_sum) % 10)) % 10
    return f"{body}{check}"


def _deterministic_mix(seed: int, index: int, salt: int = 0) -> int:
    """Deterministic integer mixer for repeatable synthetic fixture variation."""
    x = (seed ^ (index * 0x9E3779B1) ^ (salt * 0x85EBCA77)) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    return x


def iter_demo_catalog_rows(
    *,
    products: int = 5000,
    seed: int = 42,
    max_variants_per_product: int | None = None,
) -> Iterator[dict[str, str]]:
    """Yield deterministic product/variant CSV rows matching samples/products_import.csv."""
    if products < 1:
        raise ValueError("products must be >= 1")
    used_choices = ("used_a", "used_b", "used_c", "refurbished")
    barcode_seq = 1

    for idx in range(1, products + 1):
        arch = _ARCHETYPES[(idx - 1) % len(_ARCHETYPES)]
        brand_en, brand_ar = _BRANDS[(idx - 1) % len(_BRANDS)]
        model_code = f"{arch.code}{idx:04d}"
        handle = f"{brand_en.lower()}-{arch.code.lower()}-{idx:04d}"

        if arch.allow_used and idx % 4 == 0:
            condition = used_choices[_deterministic_mix(seed, idx, 1) % len(used_choices)]
            category_path = (
                "Computer > Used Laptops" if arch.code == "LT" else f"{arch.category_path} (Used)"
            )
        else:
            condition = "new"
            category_path = arch.category_path

        cond_en_suffix, cond_ar_suffix, price_factor, used_warranty = _CONDITION_LABELS[condition]
        warranty = arch.warranty_months if condition == "new" else used_warranty
        margin_step = 72 + (_deterministic_mix(seed, idx, 2) % 15)
        margin_pct = Decimal(str(margin_step)) / Decimal("100")

        combos = [(v1, v2) for v1 in arch.option1_values for v2 in arch.option2_values]
        if condition != "new":
            combos = combos[:1]
        elif max_variants_per_product is not None:
            combos = combos[:max_variants_per_product]

        for opt_idx, (opt1_val, opt2_val) in enumerate(combos):
            step_premium = Decimal("1.00") + Decimal(opt_idx) * Decimal("0.12")
            raw_price = (Decimal(arch.base_price_egp) * price_factor * step_premium).quantize(
                Decimal("1")
            )
            price_egp = f"{raw_price:.2f}"
            cost_egp = f"{(raw_price * margin_pct).quantize(Decimal('1')):.2f}"
            compare_egp = (
                f"{(raw_price * Decimal('1.12')).quantize(Decimal('1')):.2f}"
                if idx % 5 == 0
                else ""
            )

            parts_en = [p for p in (opt1_val, opt2_val) if p]
            parts_ar = [_AR_OPTION_LABELS.get(p, p) for p in parts_en]
            opt_en = f" {' '.join(parts_en)}" if parts_en else ""
            opt_ar = f" {' '.join(parts_ar)}" if parts_ar else ""

            sku_suffix = "-".join(p.replace(" ", "").upper() for p in parts_en)
            sku = f"{arch.code}-{brand_en[:4].upper()}-{idx:04d}"
            if sku_suffix:
                sku = f"{sku}-{sku_suffix}"
            if condition != "new":
                sku = f"{sku}-{condition.upper()}"

            barcode = _ean13_from_seq(barcode_seq)
            barcode_seq += 1

            yield {
                "product_handle": handle,
                "sku": sku,
                "barcode": barcode,
                "title_en": f"{brand_en} {arch.en_prefix} {model_code}{opt_en}{cond_en_suffix}",
                "title_ar": f"{arch.ar_prefix} {brand_ar} {model_code}{opt_ar}{cond_ar_suffix}",
                "category_path": category_path,
                "brand": brand_en,
                "condition": condition,
                "unit": arch.unit,
                "unit_step": arch.unit_step,
                "tracking_mode": arch.tracking_mode,
                "price_egp": price_egp,
                "compare_at_price_egp": compare_egp,
                "cost_egp": cost_egp,
                "weight_g": str(arch.weight_g),
                "option1_name": arch.option1_name if opt1_val else "",
                "option1_value": opt1_val,
                "option2_name": arch.option2_name if opt2_val else "",
                "option2_value": opt2_val,
                "warranty_months": str(warranty),
                "status": "active",
                "reorder_point": "3" if arch.tracking_mode == "serial" else "15",
                "reorder_quantity": "10" if arch.tracking_mode == "serial" else "50",
            }


def write_demo_catalog_csv(
    output: Path | TextIO | Any,
    *,
    products: int = 5000,
    seed: int = 42,
    max_variants_per_product: int | None = None,
) -> tuple[int, int]:
    """Write deterministic demo catalog CSV and return (products_count, variants_count)."""
    if isinstance(output, Path):
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            return _write_to_handle(
                handle,
                products=products,
                seed=seed,
                max_variants_per_product=max_variants_per_product,
            )
    return _write_to_handle(
        output,
        products=products,
        seed=seed,
        max_variants_per_product=max_variants_per_product,
    )


def _write_to_handle(
    handle: Any,
    *,
    products: int,
    seed: int,
    max_variants_per_product: int | None,
) -> tuple[int, int]:
    writer = csv.DictWriter(handle, fieldnames=DEMO_CSV_COLUMNS)
    writer.writeheader()
    variant_count = 0
    for row in iter_demo_catalog_rows(
        products=products,
        seed=seed,
        max_variants_per_product=max_variants_per_product,
    ):
        writer.writerow(row)
        variant_count += 1
    return products, variant_count


def render_demo_catalog_csv_string(
    *,
    products: int = 5000,
    seed: int = 42,
    max_variants_per_product: int | None = None,
) -> str:
    """Render the demo catalog CSV to an in-memory UTF-8 string."""
    buf = io.StringIO()
    write_demo_catalog_csv(
        buf,
        products=products,
        seed=seed,
        max_variants_per_product=max_variants_per_product,
    )
    return buf.getvalue()
