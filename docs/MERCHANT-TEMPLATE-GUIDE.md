# DJET Store — Merchant & Template Onboarding Guide
**Turnkey E-Commerce Engine for DJET Systems Clients & Implementation Teams**

---

## 1. Executive Summary & Core Philosophy

**DJET Store** is engineered from the ground up for permanence, uncompromising security, and rapid vertical customization. Rather than maintaining dozens of fragmented forks or incompatible codebases across client engagements, DJET Systems uses an architectural model codified in **ADR-0004**:

> **"One Engine, Five Built-in Vertical Presets, Infinite Extensibility."**

A single high-performance codebase serves diverse client business models—from electronics dealers requiring IMEI tracking and installment calculators to fashion brands demanding 3:4 lookbooks, restaurants requiring 2-column menu layouts, and neighborhood minimarkets selling produce by the quarter-kilo.

### Architectural Invariants
1. **Append-Only Immutable Stock Ledger:** Physical stock changes are recorded strictly via `StockMovement` records. Catalog imports and price updates never touch the ledger.
2. **Integer Monetary Minor Units:** All prices, costs, and cart calculations are stored and calculated in integer piastres (100 piastres = 1.00 EGP). Floating-point arithmetic is strictly prohibited.
3. **Zero-Trust RBAC & Cost Data Masking:** Internal costs, margins, and supplier records are strictly masked from untrusted views, API endpoints, and storefront surfaces.
4. **Public Non-PII Safeguards:** The public warranty and order lookup endpoints never expose customer names, phone numbers, or warehouse addresses.

---

## 2. 15-Minute Client Provisioning Quickstart

When a sales deal is closed with a prospective merchant, the DJET engineering team or the merchant's technical staff can provision a production-grade store in under 15 minutes.

### Step 1: Clone the Repository
```bash
git clone git@github.com:djetsystems/djet-store.git client-store-acme
cd client-store-acme
```

### Step 2: Run the Turnkey Store Provisioner

DJET Store provides a swanky, interactive CLI wizard branded with the official DJET Systems architecture stamp.

```text
 ╔═════════════════════════════════════════════════════════════════════════════╗
 ║  DJET SYSTEMS · OFFICIAL ARCHITECTURE SPECIFICATION & STAMP                 ║
 ║  Signature : 0xDJET-99A4-PERMANENCE-BY-DESIGN                               ║
 ║  Architect : Anas Ghareib (Founder & Lead Security Architect)               ║
 ║  Standard  : ADR-0004 · Zero-Trust RBAC · Append-Only Stock Ledger          ║
 ╚═════════════════════════════════════════════════════════════════════════════╝
```

#### Mode A: Interactive Guided Wizard (Recommended for Developers)
Simply execute the script without arguments. It greets you and walks you through configuration questions with smart defaults on `[ENTER]`:

```bash
bin/setup-store
```

**Interactive Interview Questions:**
1. **Vertical Preset Selection:** Choose from `[1] general`, `[2] electronics`, `[3] clothing`, `[4] food`, `[5] minimarket`.
2. **Brand Identity:** Store titles in English and Arabic, plus WhatsApp support number.
3. **Staff Owner:** Executive owner email and custom password (or auto-generates a high-entropy 14-char passphrase).
4. **Starter Data:** Prompts whether to seed vertical categories and import the starter catalog CSV.

#### Mode B: Unattended / CI Mode (For Automated Deployments)
Pass flags with `--non-interactive` or `-y`:

```bash
# Example: Provisioning an Electronics & Mobile Store unattended
bin/setup-store -y \
  --preset electronics \
  --name-en "TechZone Egypt" \
  --name-ar "تيك زون مصر" \
  --whatsapp "201012345678" \
  --admin-email "admin@techzone.eg" \
  --admin-password "StrongPassPhrase2026!"
```

#### What `bin/setup-store` Automates (6-Step Telemetry):
1. **Cryptographic Key Fabrication:** Generates `.env` with a 64-character URL-safe `DJANGO_SECRET_KEY` and a 256-bit AES-GCM `ENCRYPTION_KEY` (`0600` permissions).
2. **PostgreSQL Schema Compilation:** Applies all migrations, partial unique indexes, and audit tables.
3. **Zero-Trust RBAC Seeding:** Executes `manage.py seed_roles` to initialize the 6 institutional roles (`Owner`, `Manager`, `Cashier`, `Accountant`, `Warehouse`, `Support`).
4. **Vertical Preset Synthesis:** Executes `manage.py apply_preset` to inject CSS design tokens, compose home sections, and configure card behaviors.
5. **Catalog Ingestion & Ledger Isolation:** Ingests sample products and categories via `manage.py import_products` without touching physical stock ledger rows.
6. **Executive Owner Provisioning:** Creates an active superuser staff account with hashed credentials, ready for immediate dashboard login.

---

## 3. The Five Production Vertical Presets

DJET Store ships with 5 battle-tested vertical presets located in `apps/presets/definitions/`.

| Preset Code | Target Industries | Accent Color | Key Features & Card Behaviors |
| :--- | :--- | :--- | :--- |
| **`general`** | Department stores, general retail | Teal (`#0E6B5C`) | Split hero, trust bar, 1:1 aspect cards, inline order lookup, standard add-to-cart. |
| **`electronics`** | Phones, laptops, appliances | Royal Blue (`#1D4ED8`) | Condition badges (Brand New, Grade A/B, Refurbished), IMEI warranty verification banner, 12-month installment calculations, branch store locator. |
| **`clothing`** | Fashion, apparel, footwear | Neutral Slate (`#18181B`) | Editorial overlay hero, 3:4 portrait product cards, size strip chips (S, M, L, XL), "Bag" cart terminology. |
| **`food`** | Restaurants, cafes, dark kitchens | Rustic Orange (`#C2410C`) | Arabic RTL default, preparation status pill ("Kitchen Open · 25-35m"), 2-column menu layout with sticky category sidebar. |
| **`minimarket`** | Groceries, supermarkets, convenience | Emerald Green (`#059669`) | Prominent top search bar, unit pricing suffix (EGP/kg), unit step sizing (0.25 kg, 0.5 kg), "Buy It Again" reorder strip, sticky bottom basket bar. |

### Matching UI Mockups
The templates directly implement the mockups documented in `docs/ui-references/`:
- `01_general_store_default.html` ➔ `apps/presets/definitions/general/`
- `02_electronics_mobile_store.html` ➔ `apps/presets/definitions/electronics/`
- `03_clothing_brand_store.html` ➔ `apps/presets/definitions/clothing/`
- `04_food_restaurant_store.html` ➔ `apps/presets/definitions/food/`
- `05_minimarket_grocery_store.html` ➔ `apps/presets/definitions/minimarket/`
- `06_product_detail_installment_warranty.html` ➔ `apps/storefront/templates/storefront/product_detail.html`
- `07_cart_and_warranty_check.html` ➔ `apps/storefront/templates/storefront/cart.html` & `warranty_check.html`

---

## 4. Live Theme Preview Engine (For Sales Demos)

DJET sales engineers can showcase different vertical themes on a single running instance without altering database configurations. Simply append `?preset=<code_or_alias>` to any storefront URL:

```text
http://localhost:8000/?preset=electronics
http://localhost:8000/?preset=clothing
http://localhost:8000/?preset=food
http://localhost:8000/?preset=minimarket
```

The system automatically resolves common industry synonyms:
- `fashion`, `apparel` ➔ `clothing`
- `phones`, `gadgets` ➔ `electronics`
- `restaurant`, `kitchen` ➔ `food`
- `grocery`, `supermarket` ➔ `minimarket`

---

## 5. High-Velocity Catalog Onboarding

Merchants can import thousands of products and variants within seconds using CSV.

### Management Command
```bash
# Validate import syntax without modifying database (Dry-Run)
python manage.py import_products path/to/catalog.csv --dry-run

# Execute live import
python manage.py import_products path/to/catalog.csv
```

### CSV Schema Specification
The CSV file accepts the following columns:

| Column | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `product_handle` | String | Yes | Unique product slug. Multiple rows with the same handle become variants of that product. |
| `title_en` | String | Yes | Product title in English |
| `title_ar` | String | No | Product title in Arabic (falls back to English) |
| `category_path` | String | No | Hierarchical path, e.g. `Phones > Apple > Smartphones` (auto-creates hierarchy) |
| `sku` | String | Yes | Unique Stock Keeping Unit code |
| `barcode` | String | No | UPC/EAN-13 barcode for physical HID barcode scanner integration |
| `variant_title_en` | String | No | Variant name (e.g. `128GB Black`, `Size XL`) |
| `price_egp` | Decimal | Yes | Retail selling price in EGP (e.g. `1450.00`) |
| `compare_at_egp` | Decimal | No | Original/strikethrough price in EGP |
| `cost_egp` | Decimal | No | Internal cost price (masked from storefront) |
| `condition` | Choice | No | `new`, `used_a`, `used_b`, `refurbished` |
| `unit` | String | No | `piece`, `kg`, `meter`, `liter` |
| `unit_step` | Decimal | No | Stepper increment, e.g. `0.250` for 250g |
| `warranty_months`| Integer | No | Official warranty duration in months |
| `tracking_mode` | Choice | No | `none`, `batch`, `serial` |

---

## 6. Creating a Custom Vertical Preset in 3 Steps

If a client requests a bespoke industry vertical (e.g. `perfumes` or `automotive_parts`), creating a new preset requires zero core code changes:

### Step 1: Create Definition Directory
Create `apps/presets/definitions/perfumes/preset.json`:
```json
{
  "code": "perfumes",
  "name": "Luxury Fragrances & Scents",
  "description": "High-end fragrance boutique with gold accents and note breakdowns",
  "default_language": "ar",
  "cart_label": "Bag",
  "tokens": {
    "--bg": "#FAFAF9",
    "--surface": "#FFFFFF",
    "--text": "#1C1917",
    "--accent": "#B45309",
    "--accent-hover": "#92400E",
    "--radius-card": "16px",
    "--font-sans": "'Playfair Display', serif"
  },
  "card_flags": {
    "aspect_ratio": "3/4",
    "show_condition_badge": false,
    "show_size_strip": true,
    "quick_add": false
  },
  "home_sections": [
    {
      "type": "hero_editorial_overlay",
      "title_en": "Signature Scents of the Orient",
      "title_ar": "العطور الشرقية الأصيلة",
      "subtitle_en": "Handcrafted pure oud and French extracts.",
      "subtitle_ar": "عود نقي ومستخلصات فرنسية معتقة."
    },
    { "type": "trust_bar" },
    { "type": "category_tiles", "title_en": "Fragrance Families", "title_ar": "عائلات العطور" },
    { "type": "product_collection", "title_en": "Best Sellers", "title_ar": "الأكثر مبيعاً" }
  ]
}
```

### Step 2: Activate the Preset
```bash
python manage.py apply_preset perfumes --demo-data
```

### Step 3: Verify
Visit `http://localhost:8000/` to immediately view the applied tokens and layout.

---

## 7. Production Deployment & Security Architecture

DJET Store is ready for Docker-based deployment with zero external dependencies besides PostgreSQL and Redis.

### Recommended Production Stack
- **Web App:** Gunicorn / Uvicorn running `config.wsgi:application`
- **Reverse Proxy:** Caddy or Nginx with automated Let's Encrypt TLS
- **Database:** PostgreSQL 16+ with row-level locks and `money` minor unit integrity
- **Background Jobs:** Procrastinate task worker running `python manage.py procrastinate worker`

### Security Hardening Checklist
- [x] Run `python manage.py check --deploy`
- [x] Set `DJANGO_DEBUG=False` in `.env`
- [x] Enforce `SECURE_SSL_REDIRECT=True` and `SESSION_COOKIE_SECURE=True`
- [x] Enable 2FA/TOTP for all Staff accounts (`python manage.py setup_totp <email>`)
- [x] Schedule daily stock reconciliation cron:
  ```crontab
  0 3 * * * cd /opt/djet-store && uv run python manage.py reconcile_stock >> /var/log/djet/reconcile.log 2>&1
  ```
