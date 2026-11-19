# DJET Store UI Reference Mockups

These artboards (`*.dc.html`) are **design references**, not production templates. They define the visual tokens (colours, spacing, radii, typography), composable section patterns, and product-card behaviours for DJET Store's **"One Engine, Four Presets, Extensible"** storefront ([ADR-0004](../adr/0004-one-engine-four-presets-ui.md)).

## Artboards

| File | Role | Key patterns |
|---|---|---|
| `Main.dc.html` | Default storefront home | Split hero, trust bar, category tiles, product grid, promo banner, inline order tracker |
| `Product.dc.html` | Default product detail | Gallery, variant chips/swatches, qty stepper, delivery estimate widget, WhatsApp inquiry |
| `Checkout.dc.html` | Mobile-first single-page checkout | Order summary, +20 phone input, governorate/address, COD/card/wallet radios, promo code |
| `Tpl-Mobile.dc.html` | Electronics & mobile preset | Condition pills (`New`, `Used A/B`, `Refurbished`), IMEI warranty lookup, installment table, branches |
| `Tpl-Clothing.dc.html` | Clothing brand preset | Editorial hero overlay, 3:4 cards, colour dots, out-of-stock size indicator, size guide table |
| `Tpl-Food.dc.html` | Food / restaurant preset (`ar`, `rtl`) | Cover status pills, category tabs, item customizer + kitchen notes, inline cart + delivery slots |
| `Tpl-Market.dc.html` | Mini-market preset | Barcode scan search bar, aisle pills, repeat last order, fractional weight steppers, bottom basket bar |

## Previewing Locally

Serve over HTTP (browsers block `<x-dc>` runtime scripts over `file://`):

```bash
python3 -m http.server -d docs/ui-references 8090
```

Then open `http://127.0.0.1:8090/` to browse all 7 artboards from `index.html`. (`support.js` and `vendor/react*.js` are the mockup preview runtime only and are excluded from Django builds and static collection.)
