# PHASE-007-REPORT — Staff, Role-Based Access Control (RBAC), and Dashboard Shell

- **Date:** 2026-11-19
- **Milestone:** M2 (Phase 007 — Staff, RBAC, and Dashboard Shell & Phase 014 Security Baseline)
- **Status:** Complete
- **Branch:** `feature/milestone-m2-staff-rbac-dashboard`
- **Git Tag:** `phase-007`

---

## 1. What Was Built

### 1. RBAC Registry & Service Guards ([apps/core/rbac.py](file:///home/ansgrb/backyard/djet-store/apps/core/rbac.py))
- **Explicit Permission Strings:** 22 granular permission strings covering orders (`orders.view`, `orders.create`, `orders.cancel`, `orders.edit`), catalog (`catalog.view`, `catalog.edit`, `catalog.edit_price`), inventory (`inventory.view`, `inventory.adjust`, `inventory.count`, `inventory.transfer`), purchasing (`purchasing.view`, `purchasing.create`, `purchasing.approve`), reports & costs (`reports.view`, `reports.view_costs`), settings (`settings.view`, `settings.edit`), staff administration (`staff.view`, `staff.manage`, `audit.view`), and exports (`data.export`).
- **6 Built-in Roles:**
  - `Owner`: Full access to all operations, staff management, settings, and exports (`*`).
  - `Manager`: Operational lead managing orders, catalog, stock, and costs (`reports.view_costs`); blocked from staff management, payment settings, and customer exports.
  - `Cashier`: Front-desk sales (create/view orders, catalog, stock); strictly blocked from canceling orders, editing prices, stock adjustments, and viewing costs/margins.
  - `Warehouse`: Stock operations (receive, count, adjust, transfer); blocked from editing catalog prices, customer exports, and cost data.
  - `Accountant`: Financial reconciliation (orders, reports, costs, exports, audit log); blocked from stock adjustments and catalog edits.
  - `Support`: Customer support (orders view and edit); blocked from stock adjustments, prices, costs, and exports.
- **Customization Invariant:** Built-in roles track `is_builtin` and `modified_by_merchant`. The `sync_builtin_roles()` sync function updates built-in definitions idempotently without silently overwriting merchant edits.
- **Deny by Default:** `authorize(actor, perm)` enforces authorization at the service layer; raises `PermissionDenied` if unauthenticated or under-privileged.
- **View Decorator:** `@requires_permission(perm)` enforces authentication, session validity, 2FA compliance, and permission checks on dashboard views.

### 2. Staff Security, Lockout & Authentication ([apps/core/models.py](file:///home/ansgrb/backyard/djet-store/apps/core/models.py), [apps/dashboard/auth_views.py](file:///home/ansgrb/backyard/djet-store/apps/dashboard/auth_views.py))
- **Password Hardening:** Argon2id primary hasher with PBKDF2 fallback, minimum 12-character length requirement enforced across all accounts.
- **Brute-Force Rate Limiting & Lockout:** 5 consecutive failed login attempts trigger an automatic 15-minute account lock (`locked_until`) and log `auth:account_locked` in `AuditLog`. Additional attempts while locked are rejected and logged (`auth:lockout_attempt`). Successful logins reset failed attempt counters.
- **Session Security:** Session keys rotated via `request.session.cycle_key()` upon successful authentication and logout, preventing session fixation.
- **Single-Use Invitations ([StaffInvite](file:///home/ansgrb/backyard/djet-store/apps/core/models.py)):** Single-use tokens hashed with SHA-256 before storage with a 48-hour expiration window. Replaying used or expired tokens is strictly rejected.

### 3. RFC 6238 TOTP 2FA & Emergency Recovery Codes ([apps/core/totp.py](file:///home/ansgrb/backyard/djet-store/apps/core/totp.py))
- **Pure-Python TOTP Engine:** Implements RFC 6238 HMAC-SHA1 dynamic truncation generating 6-digit tokens over 30-second time steps.
- **Clock Drift Tolerance:** Allows $\pm 1$ time-step window ($T-30$s, $T$, $T+30$s) while rejecting out-of-window attempts.
- **Mandatory 2FA Enforcement:** Staff accounts with the `Owner` or `Manager` role are required to have 2FA enabled. Attempting to access operational endpoints without active 2FA automatically redirects the user to `/auth/2fa/setup/`.
- **Single-Use Recovery Codes:** Generates 10 cryptographically secure alphanumeric recovery codes (`XXXX-XXXX`). Codes are consumed atomically upon use and logged to `AuditLog`.
- **Secret Encryption:** TOTP secrets are encrypted at rest using AES-CBC/HMAC derived from Django secret keys via `EncryptedCharField`.

### 4. Merchant Dashboard Surface Shell ([apps/dashboard](file:///home/ansgrb/backyard/djet-store/apps/dashboard))
- **Surface Isolation:** Isolated under `config.urls_dashboard` with `__Host-djet_admin_sid` session cookies, `Strict` SameSite, and session-backed CSRF.
- **RTL & LTR Support:** Native support for Arabic and English using CSS logical properties and HTML `dir` attribute.
- **Operational Screens:**
  - `today_view`: Real-time morning KPI cards (Orders to Pack, Low Stock SKUs, Out of Stock count, Active Products, Fulfillment Nodes), quick action shortcuts, and recent audit activity.
  - `orders_list_view`: Orders table shell with search and status filters.
  - `products_list_view`: Catalog and variants table with sensitive cost/margin masking.
  - `inventory_list_view`: Stock levels by location with average unit cost masking.
  - `purchasing_list_view`: Suppliers and purchase orders shell.
  - `reports_view`: Operational sales overview; cost and gross margin breakdown cards are restricted behind `reports.view_costs`.
  - `settings_view`: Store configuration, currency, and security policy display.
  - `staff_list_view` & `staff_invite_view`: Staff user table, pending invite list, and single-use invite generator.
  - `roles_list_view`: Roles and permissions viewer.
  - `audit_list_view`: Immutable audit log inspector.
  - `export_data_view`: Streaming CSV export for catalog, inventory, and audit data. Sensitive cost and margin columns are excluded when `reports.view_costs` is missing.
  - `support_view`: Audited diagnostic support channel recording operator identity, IP, and timestamp.
  - Built-in Django `/admin/` is not mounted on merchant URL configurations and returns 404 in production.

---

## 2. Measured Verification Output

### Static Analysis, Types & Quality Gates
- **Ruff:** `uv run ruff check .` and `uv run ruff format --check .` passed (`0` errors, `110` files formatted).
- **Mypy:** `uv run mypy apps tests` passed with `Success: no issues found in 108 source files` (strict on `core`, `inventory`, `orders`, `payments`).
- **Import Linter:** `uv run lint-imports` passed (`Contracts: 2 kept, 0 broken`). Core apps never import addons; dependency layers preserved.
- **Bandit:** `uv run bandit -c pyproject.toml -r apps config` passed (`0` issues across 3,858 lines of code).
- **Pip-Audit:** `uv run pip-audit --skip-editable` passed (`No known vulnerabilities found`).
- **Django Checks:** `uv run python manage.py check` passed with `0` issues.
- **Database Migrations:** `uv run python manage.py makemigrations --check --dry-run` passed with `No changes detected`.

### Automated Test Suite Execution
```
============================= test session starts ==============================
platform linux -- Python 3.14.5, pytest-9.2.0, pluggy-1.7.0
django: version: 6.1.3, settings: config.settings.test (from ini)
rootdir: /home/ansgrb/backyard/djet-store
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.14.7, django-4.14.0, hypothesis-6.170.15
collected 91 items

tests/test_cost_data_masking.py ...                                      [  3%]
tests/test_dashboard_auth_and_lockout.py .....                           [  8%]
tests/test_db_immutability.py ....                                       [ 13%]
tests/test_healthz.py ....                                               [ 17%]
tests/test_ledger_services.py ............                               [ 30%]
tests/test_rbac_matrix.py ..........                                     [ 41%]
tests/test_reconciliation.py ..                                          [ 43%]
tests/test_settings_and_crypto.py ....                                   [ 48%]
tests/test_surface_isolation.py ...                                      [ 51%]
tests/test_totp_and_2fa.py .....                                         [ 57%]
tests/test_url_authorization.py ..............                           [ 72%]
tests/test_concurrency.py .                                              [ 73%]
tests/test_demo_generator.py ....                                        [ 78%]
tests/test_forbidden_writers.py .                                        [ 79%]
tests/test_import_contracts.py ..                                        [ 81%]
tests/test_money.py .............                                        [ 95%]
tests/test_settings_security.py ...                                      [ 98%]
tests/test_surface_isolation.py .                                        [100%]

============================== 91 passed in 6.36s ==============================
```

---

## 3. Phase 014 Security Baseline Compliance

| Control | Implementation | Verification |
|---|---|---|
| **Deny by default** | Permissions verified in views (`@requires_permission`) and services (`authorize`) | [tests/test_rbac_matrix.py](file:///home/ansgrb/backyard/djet-store/tests/test_rbac_matrix.py), [tests/test_url_authorization.py](file:///home/ansgrb/backyard/djet-store/tests/test_url_authorization.py) |
| **Password policy** | Argon2id + 12-character minimum length validator | [tests/test_dashboard_auth_and_lockout.py](file:///home/ansgrb/backyard/djet-store/tests/test_dashboard_auth_and_lockout.py) |
| **Brute-force lockout** | 5 failed attempts $\rightarrow$ 15-minute lock + audit log | [tests/test_dashboard_auth_and_lockout.py](file:///home/ansgrb/backyard/djet-store/tests/test_dashboard_auth_and_lockout.py) |
| **2FA / MFA** | RFC 6238 TOTP with mandatory enforcement for Owner/Manager | [tests/test_totp_and_2fa.py](file:///home/ansgrb/backyard/djet-store/tests/test_totp_and_2fa.py) |
| **Data masking** | Cost, supplier price, and margin stripped in HTML & CSV | [tests/test_cost_data_masking.py](file:///home/ansgrb/backyard/djet-store/tests/test_cost_data_masking.py) |
| **Session security** | Key rotation on login/logout; `__Host-` prefix with `Strict` SameSite | [tests/test_surface_isolation.py](file:///home/ansgrb/backyard/djet-store/tests/test_surface_isolation.py), [tests/test_dashboard_auth_and_lockout.py](file:///home/ansgrb/backyard/djet-store/tests/test_dashboard_auth_and_lockout.py) |
| **Audit logging** | Append-only ledger recording logins, lockouts, 2FA, invites, exports | [tests/test_db_immutability.py](file:///home/ansgrb/backyard/djet-store/tests/test_db_immutability.py), [tests/test_dashboard_auth_and_lockout.py](file:///home/ansgrb/backyard/djet-store/tests/test_dashboard_auth_and_lockout.py) |
