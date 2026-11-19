# DJET Store Benchmarks

This directory contains the reproducible Lighthouse CLI + direct HTTP TTFB benchmark harness and captured baseline JSON results.

## Reference Environment Specification

Per `015-testing-and-benchmark-gates.md`:
- **Reference VPS profile:** 2 vCPU / 4 GB RAM Linux VPS (target single-merchant production size)
- **Device profile:** Lighthouse Mobile (`--form-factor=mobile --screenEmulation.mobile=true`, Moto G Power emulation)
- **Network & CPU throttling:** Lighthouse simulated Slow 4G (150 ms TCP RTT, 1.6 Mbps download, 750 Kbps upload, 4× CPU slowdown)
- **Runs per URL:** 3 runs by default, reporting median and min/max spread (use `--runs 5` for release validation)

## How to Reproduce

Prerequisites:
- Python 3.13+
- Node.js + `npx` (runs Lighthouse CLI)
- Google Chrome or Chromium (`/usr/bin/google-chrome` or `--chrome-path`)

Run against a URL list JSON file:

```bash
python3 docs/benchmarks/run_benchmark.py \
  --urls-file docs/benchmarks/urls_kimostore.json \
  --output-dir docs/benchmarks/competitors/2026-11 \
  --runs 3
```

### Output

- `<page>.run<N>.lighthouse.json.gz` — gzip-compressed raw Lighthouse JSON report for auditability
- `summary.json` — methodology metadata, median Core Web Vitals, resource breakdown (JS, CSS, images, third-party), direct HTTP TTFB probe, and pass/fail checks against DJET Store's Phase 001 budgets

## Ethics & Accuracy Rules

1. Measure public pages only, at low rate (`--pause-seconds 1.5` default).
2. Always publish methodology (date, throttling, tool versions, run count, median and spread) alongside any numbers.
3. Re-run before citing comparisons externally; never extrapolate beyond what was measured.
