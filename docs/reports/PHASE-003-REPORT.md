# PHASE-003-REPORT — Domain Model, Money, AuditLog, and the Stock Ledger

- **Date:** 2026-11-19
- **Milestone:** M1 (Phase 003 — Domain Model and the Stock Ledger)
- **Status:** Complete
- **Branch:** `feature/milestone-m1-ledger`
- **Git Tag:** `phase-003`

---

## 1. What Was Built

1. **Money Value Object ([apps/core/money.py](file:///home/ansgrb/backyard/djet-store/apps/core/money.py)):**
   - Invariant: All monetary amounts stored as integer minor units (piastres for EGP: 1 EGP = 100 piastres).
   - Strictly rejects float calculations (`TypeError`) to prevent precision drift.
   - Commercial half-up rounding (`ROUND_HALF_UP`) on major unit conversions.
   - Currency isolation: arithmetic or comparison across different currencies raises `CurrencyMismatchError`.
   - Largest-remainder algorithm (`allocate`) using the Hamilton-Hare method: distributes remainders deterministically, guaranteeing exact total preservation down to the single minor unit without losing or fabricating piastres.
   - Fuzzed with property-based testing in [tests/test_money.py](file:///home/ansgrb/backyard/djet-store/tests/test_money.py) using Hypothesis.

2. **Base Core & Audit Models ([apps/core/models.py](file:///home/ansgrb/backyard/djet-store/apps/core/models.py), [apps/core/fields.py](file:///home/ansgrb/backyard/djet-store/apps/core/fields.py)):**
   - `TimeStampedModel`: abstract base model with indexed `created_at` and `updated_at`.
   - `AuditLog`: immutable audit trail (`core_audit_log`) recording action, actor, entity_type, entity_id, JSON diff, IP address, user-agent, correlation ID, and timestamp.
   - `StoreSettings`: singleton configuration model (`core_store_settings`) enforcing ID=1, managing active presets (`general`, `electronics`, `fashion`, `groceries`), currencies, languages, tax mode, audit retention, and global negative stock toggle.
   - `FeatureFlag`: slug-indexed toggle model (`core_feature_flag`).
   - `EncryptedCharField`: model field transparently encrypting credentials at rest using AES-CBC/HMAC (Fernet) derived from Django's secret key.

3. **Catalog Domain Models ([apps/catalog/models.py](file:///home/ansgrb/backyard/djet-store/apps/catalog/models.py)):**
   - `Category`: category hierarchy with slug and parent-child relations.
   - `Product`: handle, bilingual titles (AR/EN), description, category, brand, and lifecycle status (`draft`, `active`, `archived`).
   - `Variant`: SKU with case-insensitive unique constraint `Lower('sku')`, optional barcode, minor-unit prices/costs (piastres), tracking modes (`none`, `batch`, `serial`), units (`piece`, `kg`, etc.), `unit_step` (e.g. 0.250 kg for produce/cheese), and `allow_negative_stock`.

4. **Inventory Domain & Stock Ledger ([apps/inventory/models.py](file:///home/ansgrb/backyard/djet-store/apps/inventory/models.py)):**
   - `Location`: physical location codes (`MAIN`, `BRANCH1`), kinds (`warehouse`, `store`, `returns`), priority, and online fulfillment eligibility.
   - `Batch`: lot tracking with optional expiration dates.
   - `SerialUnit`: individual serial/IMEI tracking with lifecycle states (`in_stock`, `reserved`, `sold`, `returned`).
   - `StockLevel`: derived inventory cache per variant and location. Denormalized `allow_negative` from variant to satisfy Decision D4. Database CHECK constraints: `(allow_negative OR on_hand >= 0)` and `(reserved >= 0)`.
   - `StockMovement`: append-only immutable ledger recording all physical stock mutations (`purchase_receipt`, `sale_shipment`, `adjustment_count`, `transfer_out`/`transfer_in`, `return_restock`, `opening_balance`, `repair_reconcile`) with signed quantity deltas, unit costs, batch/serial links, document refs, and actor.
   - `StockReservation`: temporary checkout stock holds with TTL expiry.

5. **Inventory Service Layer ([apps/inventory/services.py](file:///home/ansgrb/backyard/djet-store/apps/inventory/services.py)):**
   - The **sole** authorized write path for all inventory mutations.
   - Concurrency & deadlock safety: lines sorted deterministically by `(variant_id, location_id)` before row acquisition (Decision D6).
   - Race-free record initialization via `bulk_create(ignore_conflicts=True)` / `INSERT ... ON CONFLICT DO NOTHING` (Decision D5).
   - Weighted Average Cost (WAC) recalculation on positive receipts (`NUMERIC(18,4)`).
   - Atomic reservation creation, reservation release, and reservation consumption into sale shipments.
   - Periodic stale reservation expiry (`expire_stale_reservations`).
   - Ledger reconciliation repair service (`repair_stock_level`).

6. **Database Immutability Protections:**
   - PostgreSQL triggers:
     - `trg_prevent_stock_movement_update_delete` on `inventory_stock_movement` ([0002_stock_movement_immutable_trigger.py](file:///home/ansgrb/backyard/djet-store/apps/inventory/migrations/0002_stock_movement_immutable_trigger.py)).
     - `trg_prevent_audit_log_update_delete` on `core_audit_log` ([0003_audit_log_immutable_trigger.py](file:///home/ansgrb/backyard/djet-store/apps/core/migrations/0003_audit_log_immutable_trigger.py)).
     Raises an exception with SQLSTATE `restrict_violation` on any attempt to execute `UPDATE` or `DELETE`.
   - `apply_db_grants` command updated to revoke `UPDATE`, `DELETE`, `TRUNCATE` on `inventory_stock_movement` and `core_audit_log` from `djet_app`.

7. **Management Commands:**
   - `load_opening_balance`: seeds stock from CSV (`samples/stock_opening_balance.csv`) idempotently, creating locations, variants, serials, and batches.
   - `reconcile_stock`: audits `StockLevel` cache against `StockMovement` sums and active reservations; `--repair` flag heals discrepancies and writes audit records.
   - `expire_reservations`: releases timed-out checkout reservations.

---

## 2. Measured Verification Output

### Static Analysis, Types & Security Gates
- `ruff check .` & `ruff format --check .`: passed (`0` errors, `101` files formatted).
- `mypy apps tests`: `Success: no issues found in 94 source files` (strict on `core`, `inventory`, `orders`, `payments`).
- `lint-imports`: `Contracts: 2 kept, 0 broken` (no cross-boundary violations).
- `bandit -c pyproject.toml -r apps config`: `No issues identified`.
- `pip-audit --skip-editable`: `No known vulnerabilities found`.

### Test Suite (Pytest against PostgreSQL 18)
- Total tests: **54 passed in 3.47s**.
- Concurrency test ([tests/test_concurrency.py](file:///home/ansgrb/backyard/djet-store/tests/test_concurrency.py)):
  - 50 concurrent worker threads attempting to purchase 1 unit simultaneously against an initial stock of 10 units.
  - Exactly 10 checkouts succeeded, exactly 40 received `InsufficientStock`. Final `on_hand = 0`, zero deadlocks, zero oversell.
- Reconciliation test ([tests/test_reconciliation.py](file:///home/ansgrb/backyard/djet-store/tests/test_reconciliation.py)):
  - Deliberately corrupted `StockLevel.on_hand` is detected by `reconcile_stock` (exit code 1).
  - With `--repair`, the service restores ground truth from movement sums and writes an audit log.
- AST forbidden writers test ([tests/test_forbidden_writers.py](file:///home/ansgrb/backyard/djet-store/tests/test_forbidden_writers.py)):
  - Verifies that no Python file outside `apps/inventory/services.py` assigns to `.on_hand` or `.reserved` or executes `.update(on_hand=..., reserved=...)`.
- DB immutability test ([tests/test_db_immutability.py](file:///home/ansgrb/backyard/djet-store/tests/test_db_immutability.py)):
  - Verifies that direct SQL `UPDATE` and `DELETE` on `inventory_stock_movement` and `core_audit_log` are rejected by PostgreSQL triggers.
- Core Settings & Crypto tests ([tests/test_settings_and_crypto.py](file:///home/ansgrb/backyard/djet-store/tests/test_settings_and_crypto.py)):
  - Singleton enforcement on `StoreSettings`, feature flags toggling, transparent AES-CBC/HMAC encryption at rest on `EncryptedCharField`, and audit trail capture.
- Expanded Ledger flows ([tests/test_ledger_services.py](file:///home/ansgrb/backyard/djet-store/tests/test_ledger_services.py)):
  - Transfers between locations (`transfer_out` / `transfer_in`), customer returns (`return_restock` vs `return_writeoff`), stock count adjustments (`adjustment_count`), and damage write-offs (`adjustment_damage`).

### CI Gates on GitHub Actions (Run 44489904106)
- `CI/quality`: Passed in 42s (ruff, full mypy across 97 files, import-linter, bandit, pip-audit, Django system checks, makemigrations drift check, opening balance seed & reconciliation smoke check, 54 pytest tests on PostgreSQL 18).
- `CI/compose-smoke`: Passed in 1m33s (ephemeral env, Docker Compose build and start, HTTPS storefront and dashboard healthz, isolated session cookie checks).

---

## 3. Deliberately Skipped / Deferred

- **Full Catalog UI / Dashboard CRUD screens:** Scheduled for Milestone M2 / M3 (Phases 004 & 007).
- **Checkout Cart and Order workflows:** Scheduled for Milestone M4 / M5 (Phases 005 & 006).

---

## 4. Deviations from Blueprint

- **Decision D4 Denormalization:** PostgreSQL CHECK constraints cannot evaluate foreign table columns (`variant.allow_negative_stock`); hence `allow_negative` was denormalized onto `stock_level` and synchronized during `bulk_create` / `move_stock_many`.
- **Decision D5 Concurrency:** `select_for_update().get_or_create()` was replaced with `bulk_create(ignore_conflicts=True)` (`INSERT ... ON CONFLICT DO NOTHING`) followed by deterministic `select_for_update().order_by('variant_id', 'location_id')` to eliminate PostgreSQL insertion race conditions.

---

## 5. Definition of Done Checklist

- [x] No code outside `inventory.services` can change `on_hand` (verified by AST scan and DB triggers).
- [x] Concurrency test: 50 parallel purchase attempts against 10 units never oversell.
- [x] Reconcile job detects a deliberately corrupted `stock_level` row in a test and repairs it.
- [x] Money tests cover rounding, arithmetic, largest-remainder allocation, and currency mismatches.
- [x] `PHASE-003-REPORT.md` written and branch prepared for PR review.
