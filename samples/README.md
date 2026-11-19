# Samples: reference sheets and fixtures

All data here is **fictional and illustrative**. Brands, phone numbers, prices, fees and barcodes are placeholders. Do not treat them as market data, and replace shipping fees with the merchant's real rates.

| File | Used by | What it demonstrates |
|---|---|---|
| `products_import.csv` | Phase 004 importer | Variants via `product_handle` + option columns, condition grading, units + `unit_step`, tracking modes (`serial`, `batch`, `none`), Arabic titles, warranty, reorder fields |
| `stock_opening_balance.csv` | Phase 003/004 seed | Multi-location balances, serial lists (`;` separated), batches with expiry, fractional quantity for weight items |
| `courier_settlement.csv` | Phase 008 COD reconciliation | A courier statement with normal matches, a fee-heavy line, a row with **no order reference**, and a returned-to-sender row |
| `shipping_zones.csv` | Phase 006/011 | Zone templates by governorate with base fee, extra-kg fee, free-shipping threshold and ETA |
| `suppliers.csv` | Phase 009 | Supplier import with payment terms and lead times |

## Format rules for importers

- Encoding UTF-8 with or without BOM. Delimiter comma. Quote fields containing commas.
- Money columns end in `_egp` and are decimals in pounds; the importer converts to integer piastres.
- `product_handle` groups variant rows into a single `Product` (optional `product_title_en` / `product_title_ar` override the derived product title). Legacy CSVs omitting `product_handle` fall back to deterministic grouping shown in the dry-run preview.
- `unit_step` defines the minimum increment step for sales and stock operations (e.g. `0.25` for `kg`, `1` for `piece`). Defaults per unit when omitted.
- `condition` values: `new`, `used_a`, `used_b`, `used_c`, `refurbished`.
- `tracking_mode` values: `none`, `batch`, `serial`.
- `category_path` uses ` > ` as the separator and creates missing nodes (dry-run lists them).
- Rows are keyed by `sku`; re-importing the same file is idempotent.
- Empty optional columns mean "no value", not "set to zero".

## Expected behaviours the agent should assert in tests

1. `products_import.csv` imports 12 variants across 8 products. Rows `PH-ACME-A1-*` (`product_handle=acme-a1-phone`) form one product with two option axes (Storage, Colour). `TS-BASIC-*` (`product_handle=basic-cotton-tshirt`) forms one product with Size and Colour axes.
2. Re-import produces 0 creates, 0 updates.
3. `stock_opening_balance.csv` produces ledger rows with reason `opening_balance`; serial variants require serial counts equal to quantity (the file satisfies this).
4. Validation failures to cover with variants of these files: duplicate SKU, duplicate barcode, serial count not equal to quantity, negative quantity, expiry date in the past, unknown location code.
5. `courier_settlement.csv`: rows with a known tracking number match automatically; `TRK100006` has no order reference and must go to the review queue; `TRK100004` shows a net amount far below COD minus a normal fee and must be flagged as a shortfall; `TRK100009` is a return and creates no COD expectation (classified as `return_fee`).
   (The agent should create matching test orders and shipments in fixtures so these tracking numbers exist.)
