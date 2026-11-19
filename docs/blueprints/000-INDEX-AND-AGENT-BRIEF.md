# 000 — Index and Agent Brief

**Project:** DJET Store, a self-hostable e-commerce and supply-chain template by DJET Systems (djet.online)
**Motto:** Permanence by Design
**Stack:** Django + Python, PostgreSQL, HTMX, Tailwind, Caddy, Docker Compose
**Status:** blueprint v1, written 17 Nov 2026

---

## 1. Who you are working for

You are a coding agent implementing a product for **DJET Systems**, a small engineering startup. The founder (Anas Ghareib) is a software engineer moving into security engineering and architecture. The product is sold to **local merchants in Egypt** (mobile shops, clothing brands, food, mini-markets, electronics retail) who today rely on Shopify-style SaaS and find the pricing and the local fit poor.

The goal is not "another storefront". The goal is **inventory, purchasing and fulfilment that a small merchant can afford**, wrapped in a storefront that is visibly faster and cleaner than what the local market ships today.

## 2. Read in this order

| Phase | File                                   | What it settles                                                    |
| ----- | -------------------------------------- | ------------------------------------------------------------------ |
| 001   | `001-vision-competitor-and-budgets.md` | Why, who for, competitor findings, performance and quality budgets |
| 002   | `002-architecture-and-deployment.md`   | Topology, repo layout, runtime, per-client deployment              |
| 003   | `003-domain-model-and-ledger.md`       | Entities, ERD, money rules, stock ledger                           |
| 004   | `004-catalog-and-inventory.md`         | Products, variants, attributes, stock operations                   |
| 005   | `005-storefront-performance-i18n.md`   | Server-rendered storefront, RTL/Arabic, image pipeline             |
| 006   | `006-orders-checkout-cod.md`           | Cart, checkout, order state machine, COD, returns                  |
| 007   | `007-dashboard-rbac.md`                | Merchant dashboard, roles, audit log                               |
| 008   | `008-payments-and-shipping.md`         | Provider and courier adapter interfaces, COD reconciliation        |
| 009   | `009-purchasing-suppliers.md`          | Suppliers, purchase orders, receiving, landed cost                 |
| 010   | `010-notifications-and-reports.md`     | WhatsApp/SMS/email, reports                                        |
| 011   | `011-vertical-presets.md`              | Clothing, food, mobile/electronics, mini-market presets            |
| 012   | `012-addon-system.md`                  | Add-on contract, hooks, feature flags                              |
| 013   | `013-installer-ops-backups.md`         | Provisioning, updates, backups, restore drills                     |
| 014   | `014-security-baseline.md`             | Threat model, controls, checklist                                  |
| 015   | `015-testing-and-benchmark-gates.md`   | Test pyramid, CI gates, performance gates                          |
| 016   | `016-roadmap-and-pricing.md`           | Build order, milestones, packaging                                 |

Sample data lives in `samples/`. Treat those files as fixtures and as the contract for import/export formats.

## 3. Non-negotiable rules for the agent

1. **Work phase by phase.** Do not start phase N+1 until phase N's "Definition of done" checklist passes.
2. **Money is integer minor units** (piastres for EGP). Never `float`. See phase 003.
3. **Stock only changes through the ledger.** No code path may write `on_hand` directly. See phase 003.
4. **Core never imports add-ons.** Add-ons subscribe to signals and extension points. See phase 012.
5. **Server-render first.** No SPA framework on the storefront. JavaScript is an enhancement. See phase 005.
6. **Security controls are part of each phase**, not a final phase. See phase 014 for the baseline every phase inherits.
7. **Everything user-facing is translatable** (Arabic and English from day one) and works in RTL.
8. **Write tests with the code.** A phase is not done without its tests and the benchmark gates in phase 015.
9. **Do not invent third-party API details.** Courier and payment-gateway request/response formats must be taken from each provider's current official documentation at implementation time. This blueprint defines our side of the interface only.
10. **Verify versions at build time.** Use current LTS or stable releases of Python, Django, PostgreSQL and libraries when you start, and pin them.

## 4. Conventions

- Repository name: `djet-store`. Python package root: `djet_store`.
- Django apps live under `apps/` and are named in the singular domain noun: `catalog`, `inventory`, `orders`, `customers`, `payments`, `shipping`, `purchasing`, `notifications`, `reports`, `dashboard`, `storefront`, `core`, `presets`, `addons`.
- Settings are split into `base`, `dev`, `prod`, `test`, all driven by environment variables (12-factor).
- Code style: `ruff` (lint and format), `mypy` or `pyright` on `core`, `inventory`, `orders`, `payments`.
- Commits are small and each phase ends with a tag: `phase-001`, `phase-002`, and so on.
- Docs for the product (not the blueprint) live in `docs/` inside the repo and are updated by the agent as features land.

## 5. How to report back

At the end of each phase, produce `PHASE-NNN-REPORT.md` containing: what was built, what was deliberately skipped, deviations from this blueprint with reasons, open questions, and the measured benchmark numbers for that phase.

## 6. Glossary

| Term        | Meaning                                                          |
| ----------- | ---------------------------------------------------------------- |
| Merchant    | The business that buys DJET Store                                |
| Shopper     | The merchant's customer                                          |
| Install     | One deployed instance for one merchant                           |
| Preset      | A vertical starting configuration (attributes, units, workflows) |
| Add-on      | An optional Django app toggled per install                       |
| Ledger      | The append-only table of stock movements                         |
| Minor units | Smallest currency unit, 1 EGP = 100 piastres                     |
| COD         | Cash on delivery                                                 |
