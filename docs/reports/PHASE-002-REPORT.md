# PHASE-002-REPORT — Architecture, Deployment Skeleton, and CI Gates

- **Date:** 2026-11-19
- **Milestone:** M0 (Foundation — closes Phases 001 & 002)
- **Status:** Complete

---

## 1. What Was Built

1. **Modular monolith layout (`002` §3):**
   - Registered all 14 domain apps under `apps/`: `core`, `catalog`, `inventory`, `customers`, `orders`, `payments`, `shipping`, `purchasing`, `notifications`, `reports`, `storefront`, `dashboard`, `presets`, `addons`.
   - Locked `AUTH_USER_MODEL = "core.StaffUser"` with initial migration [0001_initial.py](file:///home/ansgrb/backyard/djet-store/apps/core/migrations/0001_initial.py).
2. **Dual-surface runtime isolation ([ADR-0002](file:///home/ansgrb/backyard/djet-store/docs/adr/0002-dual-web-surface-and-host-cookies.md)):**
   - Separate settings overlays ([storefront.py](file:///home/ansgrb/backyard/djet-store/config/settings/storefront.py) and [dashboard.py](file:///home/ansgrb/backyard/djet-store/config/settings/dashboard.py)) and separate URL confs ([urls_storefront.py](file:///home/ansgrb/backyard/djet-store/config/urls_storefront.py), [urls_dashboard.py](file:///home/ansgrb/backyard/djet-store/config/urls_dashboard.py)).
   - Storefront uses `djet_store_sid` (`SameSite=Lax`, `HttpOnly`). Dashboard uses `__Host-djet_admin_sid` (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, `SESSION_COOKIE_DOMAIN=None`), `CSRF_USE_SESSIONS=True`, and `CSRF_TRUSTED_ORIGINS` restricted to the admin origin.
   - Built-in Django `/admin/` disabled (`404`) on both surfaces.
   - Fail-closed 12-factor environment parser ([env.py](file:///home/ansgrb/backyard/djet-store/config/settings/env.py)) and production startup security checks ([checks.py](file:///home/ansgrb/backyard/djet-store/apps/core/checks.py)).
3. **PostgreSQL role separation (`014` §2, `D17`):**
   - [init-roles.sh](file:///home/ansgrb/backyard/djet-store/deploy/postgres/init-roles.sh) provisions `djet_app` and `djet_ro` alongside `djet_migrator`.
   - Idempotent `python manage.py apply_db_grants` applies least-privilege grants and prepares append-only protections for ledger/audit tables.
4. **Hardened Docker Compose & Caddy topology ([compose.yml](file:///home/ansgrb/backyard/djet-store/deploy/compose.yml), [Caddyfile](file:///home/ansgrb/backyard/djet-store/deploy/Caddyfile), [Dockerfile](file:///home/ansgrb/backyard/djet-store/Dockerfile)):**
   - Services: `db` (`postgres:18-alpine`, mounted at `/var/lib/postgresql`, internal `backend` network only), `migrate` (one-shot migrator + `apply_db_grants` + `collectstatic`), `web-store`, `web-admin`, `worker` (Procrastinate), `caddy` (`caddy:2.9-alpine` with local `tls internal`, security headers, HTTP/2 + HTTP/3, zstd/gzip, immutable `/static/` caching), and `backup` (sidecar stub).
   - App containers run as non-root UID `10001` (`djet`), `read_only: true` with `/tmp` tmpfs, `cap_drop: ALL`, `no-new-privileges: true`, and memory/CPU resource limits.
5. **Health & readiness endpoints ([apps/core/views.py](file:///home/ansgrb/backyard/djet-store/apps/core/views.py)):**
   - `/healthz`: verifies DB connectivity and unapplied migrations; returns HTTP 200 JSON (`Cache-Control: no-store`) or HTTP 503 when unhealthy.
   - `/readyz`: verifies DB and `procrastinate_jobs` readiness.
6. **Architecture & CI gates ([pyproject.toml](file:///home/ansgrb/backyard/djet-store/pyproject.toml), [ci.yml](file:///home/ansgrb/backyard/djet-store/.github/workflows/ci.yml)):**
   - `import-linter` contracts enforcing layer order and barring core apps from importing `apps.addons`.
   - CI pipeline running `ruff`, `mypy` (strict on `core`, `inventory`, `orders`, `payments`), `lint-imports`, `bandit`, `pip-audit`, `pytest` on PostgreSQL 18, and Docker Compose HTTPS smoke verification.
   - Tests in `tests/` (`test_healthz.py`, `test_surface_isolation.py`, `test_import_contracts.py`, `test_demo_generator.py`, `test_settings_security.py`) plus `tests/conftest.py` thread-safe concurrency helper.

---

## 2. Measured Verification Output

### Static Analysis & Security Gates (post-final edit)
- `ruff check .` & `ruff format --check .`: passed (`0` lint errors, all files formatted).
- `mypy apps/core apps/inventory apps/orders apps/payments`: `Success: no issues found in 22 source files`.
- `lint-imports`: `Analyzed 82 files, 21 dependencies`, `Contracts: 2 kept, 0 broken`.
- `bandit -c pyproject.toml -r apps config`: `No issues identified`.
- `pip-audit --skip-editable`: `No known vulnerabilities found` (caught and upgraded `cryptography` `46.0.7` → `50.0.2` to clear 7 CVEs).
- `pytest` against `postgres:18-alpine`: `17 passed` (including synthetic `core -> addons` contract failure verification).

### Live Docker Compose HTTPS Verification
- All services reached `healthy` / `Exited (0)` (`db`, `migrate`, `web-store`, `web-admin`, `worker`, `caddy`, `backup`).
- `https://shop.djet.localhost/healthz`: `{"status": "ok", "surface": "storefront", "database": "ok", "migrations": "ok"}` (also `HEAD` → `HTTP/2 200`).
- `https://shop.djet.localhost/readyz`: `{"status": "ok", "surface": "storefront", "worker_ready": true}`.
- `https://admin.djet.localhost/healthz`: `{"status": "ok", "surface": "dashboard", "database": "ok", "migrations": "ok"}`.
- `https://shop.djet.localhost/?touch_session=1`: `HTTP/2 200`, `Set-Cookie: djet_store_sid=...; HttpOnly; Path=/; SameSite=Lax; Secure`, `Referrer-Policy: strict-origin-when-cross-origin`.
- `https://admin.djet.localhost/?touch_session=1`: `HTTP/2 200`, `Cache-Control: no-store`, `Set-Cookie: __Host-djet_admin_sid=...; HttpOnly; Path=/; SameSite=Strict; Secure`, `Referrer-Policy: no-referrer`.
- `/static/storefront/base.css` and `/static/dashboard/base.css`: `HTTP/2 200`, `Cache-Control: public, max-age=31536000, immutable`.
- `/admin/` on both surfaces: `HTTP 404`.

---

## 3. Deliberately Skipped / Deferred

- **Custom `xcaddy` build with `cache-handler` & `caddy-cbrotli`:** deferred to Milestone M4 (Phase 005) where storefront edge caching and purge hooks are introduced ([ADR-0003](file:///home/ansgrb/backyard/djet-store/docs/adr/0003-edge-cache-and-cart-csrf.md)). Phase 002 uses official `caddy:2.9-alpine` with `zstd` + `gzip`.
- **Backup restic schedule & off-site sync:** `backup` service runs as a standby sidecar stub until Milestone M12 (Phase 013).
- **Trivy container scan & Syft SBOM generation:** scheduled alongside release packaging in Milestone M12 / M13 (CI currently covers `bandit` + `pip-audit`).

---

## 4. Deviations from Blueprint

- **[ADR-0002](file:///home/ansgrb/backyard/djet-store/docs/adr/0002-dual-web-surface-and-host-cookies.md):** Two web services (`web-store` + `web-admin`) from one Docker image instead of a single `web` container, enabling isolated cookie/CSRF settings and `__Host-` admin cookies.
- **PostgreSQL 18 volume path:** Mounted `pg_data` at `/var/lib/postgresql` rather than `/var/lib/postgresql/data` as required by PostgreSQL 18+ Docker images.

---

## 5. Open Questions

None. Ready to proceed to Milestone M1 (Phase 003 — Money, AuditLog, and the Stock Ledger).
