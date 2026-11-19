#!/usr/bin/env python3
"""Reproducible Lighthouse + HTTP TTFB benchmark runner for DJET Store (Phase 001 / 015)."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DJET_BUDGETS = {
    "lcp_ms": 2500.0,
    "cls": 0.05,
    "ttfb_uncached_ms": 500.0,
    "ttfb_cached_ms": 200.0,
    "home_transfer_kb": 500.0,
    "js_transfer_kb": 40.0,
    "css_transfer_kb": 25.0,
}


def detect_chrome(explicit: str | None) -> str:
    """Locate Chrome or Chromium binary."""
    if explicit:
        return explicit
    for candidate in (
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if Path(candidate).exists():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if not found:
        raise FileNotFoundError("Chrome/Chromium binary not found; pass --chrome-path.")
    return found


def measure_http_ttfb(url: str, timeout: float = 15.0) -> dict[str, Any]:
    """Measure direct uncached HTTP GET TTFB and response headers."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    req = urllib.request.Request(  # noqa: S310 - scheme validated above
        url,
        headers={
            "User-Agent": "DJET-Store-Benchmark/1.0",
            "Cache-Control": "no-cache",
        },
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            _ = resp.read(1)
            ttfb_ms = round((time.perf_counter() - start) * 1000.0, 2)
            body_rest = resp.read()
            total_ms = round((time.perf_counter() - start) * 1000.0, 2)
            cache_hdr = resp.headers.get("CF-Cache-Status", resp.headers.get("X-Cache", ""))
            return {
                "status_code": resp.status,
                "ttfb_ms": ttfb_ms,
                "download_ms": total_ms,
                "html_bytes": 1 + len(body_rest),
                "server": resp.headers.get("Server", ""),
                "cache_status": cache_hdr,
                "content_encoding": resp.headers.get("Content-Encoding", ""),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status_code": exc.code,
            "error": str(exc),
            "ttfb_ms": round((time.perf_counter() - start) * 1000.0, 2),
        }
    except Exception as exc:
        return {
            "status_code": None,
            "error": str(exc),
            "ttfb_ms": None,
        }


def run_lighthouse_once(
    url: str,
    *,
    chrome_path: str,
    output_json: Path,
) -> dict[str, Any]:
    """Execute Lighthouse CLI once for mobile Slow 4G profile and parse results."""
    env = os.environ.copy()
    env["CHROME_PATH"] = chrome_path
    cmd = [
        "npx",
        "--yes",
        "lighthouse",
        url,
        "--output=json",
        f"--output-path={output_json}",
        "--quiet",
        "--form-factor=mobile",
        "--screenEmulation.mobile=true",
        "--throttling-method=simulate",
        "--only-categories=performance,accessibility,best-practices,seo",
        "--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not output_json.exists():
        return {
            "error": f"Lighthouse failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}",
        }
    data = json.loads(output_json.read_text(encoding="utf-8"))
    gz_path = Path(f"{output_json}.gz")
    with gz_path.open("wb") as gz_raw, gzip.GzipFile(fileobj=gz_raw, mode="wb", mtime=0) as gz_out:
        gz_out.write(output_json.read_bytes())
    output_json.unlink()
    if data.get("runtimeError"):
        return {
            "error": data["runtimeError"].get("message", "Unknown Lighthouse runtimeError"),
            "code": data["runtimeError"].get("code"),
        }
    return extract_metrics(data)


def extract_metrics(lhr: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized Core Web Vitals, resource sizes, and scores from Lighthouse JSON."""
    cats = lhr.get("categories", {})
    audits = lhr.get("audits", {})

    def score(cat: str) -> int | None:
        val = cats.get(cat, {}).get("score")
        return round(val * 100) if isinstance(val, int | float) else None

    def num_audit(name: str) -> float | None:
        val = audits.get(name, {}).get("numericValue")
        return round(float(val), 2) if isinstance(val, int | float) else None

    resource_items = audits.get("resource-summary", {}).get("details", {}).get("items", [])
    resources: dict[str, dict[str, float | int]] = {}
    for item in resource_items:
        rtype = item.get("resourceType")
        if rtype:
            resources[rtype] = {
                "requests": int(item.get("requestCount", 0)),
                "transfer_kb": round(float(item.get("transferSize", 0)) / 1024.0, 2),
            }

    total_kb = resources.get("total", {}).get("transfer_kb")
    js_kb = resources.get("script", {}).get("transfer_kb")
    css_kb = resources.get("stylesheet", {}).get("transfer_kb")
    lcp_ms = num_audit("largest-contentful-paint")
    cls_val = num_audit("cumulative-layout-shift")
    ttfb_ms = num_audit("server-response-time")

    dom_items = audits.get("dom-size", {}).get("numericValue")

    return {
        "lighthouse_version": lhr.get("lighthouseVersion"),
        "final_url": lhr.get("finalDisplayedUrl") or lhr.get("requestedUrl"),
        "scores": {
            "performance": score("performance"),
            "accessibility": score("accessibility"),
            "best_practices": score("best-practices"),
            "seo": score("seo"),
        },
        "metrics": {
            "fcp_ms": num_audit("first-contentful-paint"),
            "lcp_ms": lcp_ms,
            "tbt_ms": num_audit("total-blocking-time"),
            "cls": cls_val,
            "speed_index_ms": num_audit("speed-index"),
            "ttfb_ms": ttfb_ms,
            "dom_elements": int(dom_items) if isinstance(dom_items, int | float) else None,
        },
        "resources": resources,
        "budget_check": {
            "lcp_lte_2500ms": (lcp_ms <= DJET_BUDGETS["lcp_ms"]) if lcp_ms is not None else None,
            "cls_lte_0_05": (cls_val <= DJET_BUDGETS["cls"]) if cls_val is not None else None,
            "ttfb_lte_500ms": (
                (ttfb_ms <= DJET_BUDGETS["ttfb_uncached_ms"]) if ttfb_ms is not None else None
            ),
            "js_transfer_lte_40kb": (
                (js_kb <= DJET_BUDGETS["js_transfer_kb"]) if js_kb is not None else None
            ),
            "css_transfer_lte_25kb": (
                (css_kb <= DJET_BUDGETS["css_transfer_kb"]) if css_kb is not None else None
            ),
            "total_transfer_lte_500kb": (
                (total_kb <= DJET_BUDGETS["home_transfer_kb"]) if total_kb is not None else None
            ),
        },
    }


def _aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute median and min/max spread across successful runs."""
    valid = [r for r in runs if "metrics" in r]
    if not valid:
        return {"error": runs[0].get("error", "No valid runs") if runs else "No runs"}

    def med(extractor: Any) -> float | None:
        vals = [extractor(r) for r in valid]
        nums = [v for v in vals if isinstance(v, int | float)]
        return round(float(statistics.median(nums)), 2) if nums else None

    lcp_vals = [r["metrics"]["lcp_ms"] for r in valid if r["metrics"]["lcp_ms"] is not None]
    perf_vals = [
        r["scores"]["performance"] for r in valid if r["scores"]["performance"] is not None
    ]
    return {
        "runs_completed": len(valid),
        "median_scores": {
            "performance": med(lambda r: r["scores"]["performance"]),
            "accessibility": med(lambda r: r["scores"]["accessibility"]),
            "best_practices": med(lambda r: r["scores"]["best_practices"]),
            "seo": med(lambda r: r["scores"]["seo"]),
        },
        "median_metrics": {
            "fcp_ms": med(lambda r: r["metrics"]["fcp_ms"]),
            "lcp_ms": med(lambda r: r["metrics"]["lcp_ms"]),
            "tbt_ms": med(lambda r: r["metrics"]["tbt_ms"]),
            "cls": med(lambda r: r["metrics"]["cls"]),
            "speed_index_ms": med(lambda r: r["metrics"]["speed_index_ms"]),
            "ttfb_ms": med(lambda r: r["metrics"]["ttfb_ms"]),
            "total_transfer_kb": med(lambda r: r["resources"].get("total", {}).get("transfer_kb")),
            "js_transfer_kb": med(lambda r: r["resources"].get("script", {}).get("transfer_kb")),
            "css_transfer_kb": med(
                lambda r: r["resources"].get("stylesheet", {}).get("transfer_kb")
            ),
            "image_transfer_kb": med(lambda r: r["resources"].get("image", {}).get("transfer_kb")),
            "third_party_transfer_kb": med(
                lambda r: r["resources"].get("third-party", {}).get("transfer_kb")
            ),
            "total_requests": med(lambda r: r["resources"].get("total", {}).get("requests")),
        },
        "spread": {
            "lcp_min_ms": min(lcp_vals) if lcp_vals else None,
            "lcp_max_ms": max(lcp_vals) if lcp_vals else None,
            "performance_min": min(perf_vals) if perf_vals else None,
            "performance_max": max(perf_vals) if perf_vals else None,
        },
        "budget_check": valid[-1]["budget_check"],
    }


def main(argv: list[str] | None = None) -> int:
    """Run benchmark suite and write JSON reports."""
    parser = argparse.ArgumentParser(description="DJET Store Lighthouse + TTFB benchmark runner.")
    parser.add_argument("--urls-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--pause-seconds", type=float, default=1.5)
    parser.add_argument("--chrome-path", type=str, default=None)
    args = parser.parse_args(argv)

    config = json.loads(args.urls_file.read_text(encoding="utf-8"))
    pages = config.get("pages", [])
    if not pages:
        raise SystemExit("No pages listed in urls file.")

    chrome_path = detect_chrome(args.chrome_path)
    chrome_ver = subprocess.run(
        [chrome_path, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    lh_version = None

    for page in pages:
        name = page["name"]
        url = page["url"]
        print(f"[benchmark] Measuring {name}: {url} ({args.runs} runs)...", flush=True)
        http_probe = measure_http_ttfb(url)
        page_runs: list[dict[str, Any]] = []
        for run_idx in range(1, args.runs + 1):
            raw_path = args.output_dir / f"{name}.run{run_idx}.lighthouse.json"
            run_data = run_lighthouse_once(url, chrome_path=chrome_path, output_json=raw_path)
            if "lighthouse_version" in run_data and not lh_version:
                lh_version = run_data["lighthouse_version"]
            page_runs.append(run_data)
            if run_idx < args.runs:
                time.sleep(args.pause_seconds)

        results[name] = {
            "url": url,
            "http_probe": http_probe,
            "aggregate": _aggregate_runs(page_runs),
            "runs": page_runs,
        }

    summary = {
        "target": config.get("target", "custom"),
        "methodology": {
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "device_profile": "Lighthouse Mobile (Moto G Power emulation)",
            "throttling": "Simulated Slow 4G (150ms RTT, 1.6 Mbps down, 750 Kbps up, 4x CPU)",
            "runs_per_page": args.runs,
            "chrome_version": chrome_ver,
            "lighthouse_version": lh_version,
            "host_platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python_version": platform.python_version(),
        },
        "djet_budgets": DJET_BUDGETS,
        "pages": results,
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[benchmark] Wrote summary to {summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
