# DJET Store — Product Vision and Budgets

> **DJET Store is the fast, secure, owner-controlled store and back office for local merchants, with inventory and supply chain as the core, not an afterthought.**

## 1. Three Testable Promises

1. **Fast.** Server-rendered storefront with strict performance, payload, and SQL query budgets enforced in CI.
2. **Operationally real.** Append-only stock ledger, multi-location inventory, serial/IMEI and batch/FEFO tracking, purchasing with landed costs, and COD courier reconciliation.
3. **Yours.** Single-tenant Docker Compose deployment per merchant, full CSV/ZIP data export at any time, and zero per-order platform commission.

## 2. Competitor Context (`kimostore.net`)

Initial structural observation of a real Egyptian electronics retailer (`kimostore.net`) shows a large, multi-level catalogue (thousands of SKUs), parallel trees of new and used goods, physical branch pages, installment info pages, bilingual EN/AR toggle, WhatsApp/hotline links, and heavy Shopify + agency theme JS/CSS overhead. DJET Store targets exactly this operational depth without SaaS lock-in or theme bloat.

## 3. One Engine, Four Presets, Extensible

All vertical presets share **one core server-rendered storefront engine** driven by design tokens (CSS custom properties), composable home sections, and product-card display flags:

| Preset | Core operational traits | Design reference |
|---|---|---|
| **Mobile & Electronics** | Serial/IMEI tracking, new/used grades A/B/C/refurbished, per-variant warranty, public IMEI warranty lookup, branch pickup | `docs/ui-references/Tpl-Mobile.dc.html` |
| **Clothing** | Size/colour axes, swatch-to-image mapping, out-of-stock size indicators, size charts, exchanges | `docs/ui-references/Tpl-Clothing.dc.html` |
| **Food** | Weight/volume units, batch expiry with FEFO, modifiers & kitchen notes, delivery time slots, RTL Arabic default | `docs/ui-references/Tpl-Food.dc.html` |
| **Mini-market** | Scan-first multi-barcode lookup, fractional weight pricing (`unit_step`), inline quantity steppers, repeat-last-order | `docs/ui-references/Tpl-Market.dc.html` |

New verticals can be introduced via a declarative preset manifest without modifying core storefront code.

## 4. Performance and Quality Budgets

Enforced in CI from Milestone M4 (Phase 005):

| Metric | Target | Condition |
|---|---|---|
| Largest Contentful Paint (LCP) | ≤ 2.5 s | Lighthouse mobile, Slow 4G throttling, mid-range Android profile |
| Time to First Byte (cached) | ≤ 200 ms | Anonymous catalogue pages |
| Time to First Byte (uncached) | ≤ 500 ms | Product page, 5,000-product / 50,000-variant dataset |
| Cumulative Layout Shift (CLS) | ≤ 0.05 | All storefront templates |
| Interaction to Next Paint (INP) | ≤ 150 ms | Add to cart, variant switch, filter |
| Storefront JavaScript | ≤ 40 KB gzip | First-party JS per page (excludes opt-in merchant tags) |
| Storefront CSS | ≤ 25 KB gzip | Whole site, single file |
| Home page transfer | ≤ 500 KB initial | Below-the-fold images lazy-loaded |
| Uncached SQL query budgets | Home ≤ 6, Collection ≤ 8, Product ≤ 6, Cart ≤ 5, Checkout ≤ 10 | Asserted in automated tests |
