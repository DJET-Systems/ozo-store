# PHASE-001-REPORT — Vision, Competitor Baseline, and Budgets

- **Date:** 2026-11-19
- **Milestone:** M0 (Foundation — closes Phases 001 & 002)
- **Status:** Complete

---

## 1. What Was Built

1. **Repository skeleton (`001` §6.1, `002` §3):**
   - Created `pyproject.toml`, `uv.lock`, `manage.py`, `djet_store/`, `config/`, and all 14 domain apps under `apps/`.
   - Pinned `Django==6.1.3` with `psycopg[binary]`, `procrastinate`, `argon2-cffi`, `cryptography==50.0.2`, `phonenumbers`, and `pyyaml`.
2. **Reproducible benchmark harness (`docs/benchmarks/`):**
   - [run_benchmark.py](file:///home/ansgrb/backyard/djet-store/docs/benchmarks/run_benchmark.py): runs Lighthouse CLI (Mobile Slow 4G simulation) and direct uncached HTTP TTFB probes, computing median and min/max spread across runs and asserting against DJET Store's Phase 001 budgets.
   - [urls_kimostore.json](file:///home/ansgrb/backyard/djet-store/docs/benchmarks/urls_kimostore.json): target list for `kimostore.net` (home, collection, product, cart).
   - [docs/benchmarks/README.md](file:///home/ansgrb/backyard/djet-store/docs/benchmarks/README.md): reproduction instructions and reference VPS specification (`2 vCPU / 4 GB RAM`).
3. **Competitor baseline (`docs/benchmarks/competitors/2026-11/`):**
   - Captured raw Lighthouse reports (`*.lighthouse.json.gz`) and aggregated [summary.json](file:///home/ansgrb/backyard/djet-store/docs/benchmarks/competitors/2026-11/summary.json).
4. **Demo data generator (`apps/catalog/demo_generator.py`):**
   - Deterministic (`--seed 42`) electronics-style catalog generator supporting 5,000+ bilingual (EN/AR) products across new, used (`used_a`, `used_b`, `used_c`), and refurbished conditions, serial and non-serial tracking modes, option axes, and valid EAN-13 barcodes.
   - Management command: `python manage.py generate_demo_catalog`.
   - Updated [samples/products_import.csv](file:///home/ansgrb/backyard/djet-store/samples/products_import.csv) and [samples/README.md](file:///home/ansgrb/backyard/djet-store/samples/README.md) with `product_handle` and `unit_step`.
5. **Vision & design documentation:**
   - [docs/vision.md](file:///home/ansgrb/backyard/djet-store/docs/vision.md) summarizing positioning, the "One Engine, Four Presets, Extensible" UI architecture derived from [docs/ui-references/](file:///home/ansgrb/backyard/djet-store/docs/ui-references/README.md), and enforceable budgets.

---

## 2. Measured Competitor Baseline (`kimostore.net`)

**Methodology (recorded in `summary.json`):**
- **Captured at:** `2026-11-19T06:05:53Z`
- **Tooling:** Lighthouse `13.6.0`, Google Chrome `157.0.8103.78`
- **Device & throttling:** Lighthouse Mobile (Moto G Power emulation), simulated Slow 4G (`150 ms` RTT, `1.6 Mbps` download, `750 Kbps` upload, `4×` CPU slowdown)
- **Runs:** 3 runs requested per URL (`home` completed 2 valid runs because run 1 hit an `npx` registry `ETIMEDOUT` fetching `devtools-protocol`; `collection`, `product`, and `cart` each completed 3 valid runs)

| Page | Perf Score (med, range) | LCP ms (med, range) | CLS (med) | TBT ms (med) | Direct HTTP TTFB (ms) | Total Transfer (KB) | JS Transfer (KB) | CSS Transfer (KB) | 3rd-Party (KB) | Requests |
|---|---|---|---|---|---|---|---|---|---|---|
| Home (`/`) | 38.0 (36–40) | 5,966.92 (5,264.19–6,669.65) | 0.00 | 3,720.25 | 731.33 | 6,082.98 | 2,178.56 | 62.55 | 2,283.72 | 501 |
| Collection (`/collections/pc-components`) | 12.0 (10–17) | 7,304.55 (6,623.56–8,039.93) | 0.63 | 3,459.06 | 714.24 | 3,609.18 | 1,913.57 | 124.13 | 1,977.48 | 260 |
| Product (`/products/ram-for-pc-...`) | 33.0 (31–35) | 24,786.82 (24,083.95–25,050.57) | 0.02 | 4,753.01 | 673.02 | 5,178.01 | 2,434.45 | 133.29 | 2,670.30 | 526 |
| Cart (`/cart`) | 36.0 (36–36) | 27,693.28 (27,054.31–29,043.90) | 0.02 | 5,714.00 | 586.02 | 4,156.30 | 2,125.72 | 99.56 | 2,192.56 | 393 |

**Budget comparison against DJET Store Phase 001 targets:**
- LCP target `≤ 2,500 ms`: competitor failed on all 4 pages (5,967 ms to 27,693 ms).
- CLS target `≤ 0.05`: competitor passed on home/product/cart (`0.00`–`0.02`), failed on collection (`0.63`).
- JS target `≤ 40 KB` gzip: competitor transferred `1,914–2,434 KB` across 67–129 script requests.
- CSS target `≤ 25 KB` gzip: competitor transferred `62.55–133.29 KB` across 23–54 stylesheet requests.
- Home transfer target `≤ 500 KB`: competitor transferred `6,082.98 KB` across 501 requests.

**Demo generator verification (`pytest tests/test_demo_generator.py`):**
- 5,000 deterministic electronics products generated and validated against the CSV schema (`product_handle`, unique SKUs, unique valid EAN-13 check digits, bilingual EN/AR titles, all 5 condition grades, `serial` and `none` tracking modes) in under 3 seconds.

---

## 3. Deliberately Skipped / Deferred

- DJET Store storefront measurements: deferred to Milestone M4 (Phase 005) when storefront templates and seeded catalogue views exist.
- Database persistence of the 5,000-product seed: deferred to Milestone M1/M3 (`catalog` and `inventory` schemas).

---

## 4. Deviations from Blueprint

- **Milestone re-sequencing ([ADR-0001](file:///home/ansgrb/backyard/djet-store/docs/adr/0001-milestone-resequencing.md)):** Combined Phases 001 and 002 with pulled-forward CI/test infrastructure into Milestone M0 so Phase 003 (`M1`) starts on a verified PostgreSQL + CI foundation.
- **CSV contract clarification:** Added `product_handle` and `unit_step` columns to `samples/products_import.csv` (with deterministic legacy fallback planned for Phase 004) so multi-variant rows group unambiguously into products.

---

## 5. Open Questions

None. All 8 founder architectural decisions were locked on 2026-11-19.
