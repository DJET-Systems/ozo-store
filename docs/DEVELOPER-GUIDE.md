# DJET Store — Developer & Engineering Handbook
**The Architectural & Implementation Standard for DJET Systems Engineers**

---

## 1. Architectural Philosophy: Permanence by Design

DJET Store is built as a **self-hostable, modular monolith** engineered to deliver maximum speed, uncompromising reliability, and institutional security for commerce and supply-chain operations in Egypt and the MENA region.

### Core Architectural Axioms
1. **Append-Only Stock Ledger:** The physical quantity on hand is a derived snapshot computed from an immutable, append-only ledger (`StockMovement`). No code path is permitted to update `on_hand` directly.
2. **Integer Monetary Minor Units:** All financial values (prices, costs, discounts, taxes) are stored as integer minor units (piastres for EGP: `1 EGP = 100 piastres`). Floating-point arithmetic is strictly prohibited in business logic.
3. **Surface Isolation:** The public Storefront (`shop.djet.localhost`) and the staff Dashboard (`admin.djet.localhost`) have completely isolated URL configurations, session cookies, and middleware boundaries to eliminate cross-surface privilege escalation.
4. **Zero-Trust RBAC & Sensitive Cost Masking:** Staff permissions are enforced at the view, model, and template layers. Sensitive unit costs, profit margins, and supplier purchase prices are strictly masked from untrusted staff and public visitors.
5. **Core Never Imports Add-Ons:** The core application modules (`core`, `catalog`, `inventory`, `orders`, `payments`, `shipping`, `purchasing`, `notifications`, `reports`, `dashboard`, `storefront`, `presets`) must never import from `apps.addons`. Add-ons interact solely through Django signals and declarative extension hooks.

---

## 2. Repository & App Layout

The repository follows a clean, decoupled modular monolith structure:

```text
djet-store/
├── apps/
│   ├── core/           # AuditLog, StoreSettings, StaffUser, StaffRole, Money, Crypto
│   ├── catalog/        # Category, Product, Variant, CSV Importer, Barcode Lookup
│   ├── inventory/      # Location, Batch, SerialUnit, StockLevel, StockMovement
│   ├── customers/      # Customer profiles, addresses, contact verifications
│   ├── orders/         # Order state machine, line items, checkout pipelines
│   ├── payments/       # Gateway interfaces (Fawry, Paymob, Instapay, COD)
│   ├── shipping/       # Courier adapters (Bosta, Mylerz, Internal Fleet)
│   ├── purchasing/     # Suppliers, purchase orders, receiving, landed costs
│   ├── notifications/  # WhatsApp, SMS, Email transactional dispatchers
│   ├── reports/        # Real-time analytics, inventory valuation, reconciliation
│   ├── dashboard/      # Merchant management UI, RBAC, staff security
│   ├── storefront/     # Server-rendered customer storefront, cart, warranty check
│   ├── presets/        # Declarative vertical engine, tokens, section renderers
│   └── addons/         # Decoupled pluggable extensions and integrations
├── bin/
│   ├── setup-store     # Turnkey automated client store provisioner
│   ├── dev             # Local development server launcher
│   └── check           # Comprehensive 8-point quality & security test runner
├── config/             # 12-factor Django configurations (base, dev, prod, test)
├── deploy/             # Production Docker Compose, Caddyfile, backup sidecars
├── docs/               # System blueprints (000–016), ADRs, phase reports, guides
└── tests/              # Automated unit, integration, and security test suites
```

---

## 3. Working with the Stock Ledger

The stock ledger is the critical source of truth for all physical merchandise.

### Safe Ledger Invariants
- **Always** use `record_stock_movement()` in `apps/inventory/services.py` inside an atomic transaction with row-level locking (`select_for_update()`).
- **Never** bypass the ledger to directly alter `StockLevel.on_hand`.
- **Enforce idempotency:** Every stock movement requires an `idempotency_key` or `reference_id` to guarantee zero double-counting during network retries.

### Example: Recording a Stock Movement
```python
from django.db import transaction
from apps.inventory.models import Location, StockMovement, Variant
from apps.inventory.services import record_stock_movement

@transaction.atomic
def receive_goods(variant: Variant, location: Location, quantity: Decimal) -> StockMovement:
    return record_stock_movement(
        variant=variant,
        location=location,
        quantity=quantity,
        reason="purchase_receipt",
        reference_id=f"PO-2026-001:{variant.sku}",
        notes="Received from supplier dock.",
    )
```

---

## 4. Monetary Calculations & Minor Units

All monetary values are stored in minor units (`BigIntegerField`). For Egyptian Pounds (EGP), `100 piastres = 1.00 EGP`.

### Using the `Money` Value Object
The `Money` class in `apps/core/money.py` is frozen, slots-optimized, and guarantees exact mathematical precision without floating-point drift:

```python
from decimal import Decimal
from apps.core.money import Money, allocate

# Constructing Money
price = Money.from_major("1250.50", "EGP") # 125,050 piastres
unit_cost = Money.from_minor(98000, "EGP") # 980.00 EGP

# Arithmetic operations (currency-checked)
total = price * 3
margin = price - unit_cost

# Formatted output
print(price.formatted) # "1250.50 EGP"

# Proportional distribution without penny loss (Hamilton-Hare largest-remainder)
tax_and_split = allocate(price, [14, 86]) # Exact distribution preserving 100% of piastres
```

---

## 5. Working with Vertical Presets (ADR-0004)

DJET Store implements a **single-engine polymorphic architecture**: one shared template system driven by CSS custom property tokens, card display flags, and modular section lists.

### Built-in Vertical Presets
1. **`general`**: Standard department store, split hero, trust bar, 1:1 cards.
2. **`electronics`**: Mobile & electronics, IMEI warranty checks, installment hints, branch network.
3. **`clothing`**: Fashion & apparel, 3:4 portrait cards, size strip chips, "Bag" CTA.
4. **`food`**: Kitchen & restaurant, Arabic RTL default, 2-column menu layout, delivery status badge.
5. **`minimarket`**: Quick commerce & grocery, aisle pills, kg fractional steps, bottom basket bar.

### Applying Presets via CLI
```bash
# List available presets
uv run python manage.py apply_preset --list

# Apply preset and seed demo catalog structure
uv run python manage.py apply_preset electronics --demo-data
```

### Live Theme Previews
Sales engineers and developers can dynamically preview any preset on a running server by appending `?preset=<code_or_alias>`:
- `http://localhost:8000/?preset=electronics`
- `http://localhost:8000/?preset=clothing`
- `http://localhost:8000/?preset=food`
- `http://localhost:8000/?preset=minimarket`

---

## 6. Staff RBAC & Cost Data Protection

Security is enforced at every layer (deny-by-default).

### Staff Permission Decorators
```python
from django.contrib.auth.decorators import login_required
from apps.core.decorators import require_permission

@login_required(login_url="dashboard-login")
@require_permission("inventory.adjust")
def stock_adjustment_view(request):
    # Only staff with explicit inventory.adjust capability reach this view
    ...
```

### Masking Sensitive Cost Data
To prevent accidental leakage of supplier purchase costs and profit margins:
```python
from apps.core.permissions import can_view_cost_data

def format_variant_response(variant, staff_user):
    data = {
        "sku": variant.sku,
        "price": variant.price.formatted,
    }
    # Sensitive cost amounts are strictly restricted
    if can_view_cost_data(staff_user):
        data["cost"] = variant.cost.formatted
    return data
```

---

## 7. Developer Tooling & Automation Suite

DJET Store provides first-class developer tooling under `bin/`:

### 1. `bin/setup-store` — Turnkey Provisioner CLI
The official provisioning tool featuring the DJET Systems architecture stamp, real-time telemetry, and an interactive questionnaire wizard:
```bash
# Interactive mode (prompts for vertical, names, email, password):
bin/setup-store

# Unattended automated mode (for scripts and CI):
bin/setup-store -y --preset electronics --name-en "TechZone" --name-ar "تيك زون"
```

### 2. `bin/dev` — Local Development Server Launcher
Launches Django on `0.0.0.0:8000` and displays instant live links to all vertical theme demos.
```bash
bin/dev
```

### 3. `bin/check` — Institutional 8-Point Quality Gate
Executes the full static analysis, security scans, schema checks, and test suite with unified colored output:
```bash
bin/check
```

### 4. Custom Management Commands
- `python manage.py seed_roles`: Idempotently seeds the 6 built-in zero-trust RBAC roles.
- `python manage.py apply_preset <code_or_alias> [--demo-data]`: Activates a vertical preset and applies CSS tokens.
- `python manage.py import_products <path.csv> [--dry-run]`: Imports catalog products without touching the stock ledger.

---

## 8. Developer Quality Gates & Verification

Every pull request and deployment must pass the local **8-point quality gate**.

### Run All Quality Checks with One Command
```bash
bin/check
```

### Manual Individual Commands
```bash
# 1. Linting & Style
uv run ruff check .

# 2. Code Formatting
uv run ruff format --check .

# 3. Static Type Checking (Strict)
uv run mypy apps tests

# 4. Architecture Layer Boundaries
uv run lint-imports

# 5. Security SAST Scan
uv run bandit -c pyproject.toml -r apps config

# 6. Dependency CVE Audit
uv run pip-audit --skip-editable

# 7. Django System & Schema Checks
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run

# 8. Full Pytest Suite (PostgreSQL 18)
uv run pytest
```

---

## 9. Database Migrations Discipline

When updating models:
1. **Expand, then contract:** Always make schema changes backward-compatible for one deployment cycle.
2. Avoid nullable booleans; provide clean defaults (`default=False`).
3. Always verify that migrations do not lock production tables:
   ```bash
   uv run python manage.py makemigrations
   uv run python manage.py sqlmigrate <app> <migration_number>
   ```
4. Verify migration consistency before committing:
   ```bash
   uv run python manage.py makemigrations --check --dry-run
   ```
