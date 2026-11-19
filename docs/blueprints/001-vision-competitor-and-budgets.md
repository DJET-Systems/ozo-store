# 001 — Vision, Competitor Findings and Budgets

## 1. Problem

Local merchants want to sell online. The storefront is the easy part. What hurts is everything behind it: knowing what is in stock across branches, reordering from suppliers, matching courier COD payouts to orders, handling used and new stock, and doing it at a price that fits a small business. They currently choose between:

- Global SaaS (Shopify, WooCommerce hosting) with USD-oriented pricing and weak local payment/shipping fit.
- Local SaaS (Vondera, Baseet, Pashkateb, Matgarko and similar) that are cheaper but vary in depth and speed.
- Agencies that wrap one of the above in a custom theme.

## 2. Positioning

> **DJET Store is the fast, secure, owner-controlled store and back office for local merchants, with inventory and supply chain as the core, not an afterthought.**

Three promises, each testable:

1. **Fast.** Measurable performance budgets (section 5), enforced in CI.
2. **Operationally real.** Multi-location stock, purchase orders, COD reconciliation, serial/IMEI tracking where needed.
3. **Yours.** Independent hosting per merchant, data export at any time, no per-order platform fee.

## 3. Competitor observation: Kimo Store (kimostore.net)

Source: fetched the public home page on 17 Nov 2026. Findings below are limited to what that fetch showed. **Performance claims are not yet measured**; task 3 of this phase (section 6) measures them properly.

| Observation | Evidence in the page | Implication for DJET Store |
|---|---|---|
| Built on Shopify | Shopify asset paths, Shopify account and digital-wallet endpoints, Shopify meta tags | The merchant rents the platform and its constraints |
| Agency credit in footer | "Designed & Developed by YayaAds" | Agency-built theme on a SaaS base |
| Very large catalogue | "New arrival" collection shows 5,773 items; PC components 581; surveillance cameras 167 | Catalogue and search must stay fast at thousands of SKUs |
| Deep category tree | Three to four levels (Computer > PC Components > RAM) | Category navigation must be cheap to render |
| New and used goods | A full "Used" tree with "(Original Used)" products | **Condition grading** is a first-class concept (phase 004) |
| Physical branches | "Our Branches" page | Multi-location inventory and, later, POS |
| Installments | "Banks & Installments" page | Installment display is an add-on candidate (phase 012) |
| Marketing widgets | Sales popup, wishlist, compare, countdown deals, promo code banner, newsletter | Features merchants expect; each must be cheap in JS |
| Third-party tags | Google Tag Manager present | Budget JS from third-party tags separately |
| Bilingual | English and Arabic toggle | RTL and translation are table stakes |
| Companion mobile app | Store links in the footer | A future API-first add-on (phase 012) |
| Hotline and WhatsApp | Phone and WhatsApp links | Phone-first identity and WhatsApp notifications |

### What this teaches us

The competitor's catalogue is a **complex, high-SKU, mixed new/used retail operation with branches**. That is exactly where a Shopify theme struggles and where inventory depth wins. Our first demo data set should mimic this shape (electronics, accessories, used items, serials) so a prospect sees their own problem solved.

### Ethics note

Compete on engineering and product. Do not publish disparaging claims about a named company unless measured and reproducible. Phase 015 produces a **reproducible benchmark script** so any comparison shown to prospects can be checked by anyone.

## 4. Target merchants and verticals

| Vertical | Core needs beyond a basic store |
|---|---|
| Mobile and electronics | Serial/IMEI tracking, warranty, new vs used grade, installments |
| Clothing brands | Size and color variants, size charts, returns, seasonal collections |
| Food | Weight/volume units, expiry or batch, time-slot delivery, perishable limits |
| Mini-market | Barcode, weight pricing, tiny margins, fast reorder, branch POS later |

## 5. Budgets (targets, enforced from phase 005)

| Metric | Target | Condition |
|---|---|---|
| Largest Contentful Paint | ≤ 2.5 s | Lighthouse mobile, Slow 4G throttling, mid-range Android profile |
| Time to first byte (cached) | ≤ 200 ms | Anonymous catalogue pages |
| Time to first byte (uncached) | ≤ 500 ms | Product page, 5,000 SKU data set |
| Cumulative Layout Shift | ≤ 0.05 | All storefront templates |
| Interaction to Next Paint | ≤ 150 ms | Add to cart, variant switch, filter |
| Storefront JavaScript | ≤ 40 KB gzip, first-party, per page | Excludes merchant-added third-party tags |
| Storefront CSS | ≤ 25 KB gzip | Whole site, single file |
| Home page transfer | ≤ 500 KB initial | Images lazy-loaded below the fold |
| Third-party scripts | Off by default | Merchant opts in per tag; loaded after interaction |

These are goals. Phase 015 defines how they are measured and what happens when a build misses them.

## 6. Tasks in this phase

1. Create the repository skeleton from phase 002 (empty apps, settings, Docker files).
2. Add `docs/benchmarks/` with a script that runs Lighthouse (CLI) and WebPageTest-style checks against a URL list and writes JSON results.
3. Run it against `kimostore.net` (home, one collection, one product, cart) and store the raw results under `docs/benchmarks/competitors/2026-11/`. Record device profile, throttling, date and Lighthouse version.
4. Write `docs/benchmarks/README.md` explaining how to reproduce.
5. Create the demo data generator skeleton that will emit an electronics-style catalogue of 5,000 products (see `samples/`).
6. Write `docs/vision.md` summarising sections 2 to 5 for future contributors.

## 7. Definition of done (phase 001)

- [ ] Repo skeleton exists and `docker compose up` starts an empty Django with Postgres.
- [ ] Benchmark script runs and produces JSON output.
- [ ] Competitor baseline results are stored with full methodology.
- [ ] `PHASE-001-REPORT.md` written, including the measured competitor numbers (do not copy numbers from this document, it has none).
