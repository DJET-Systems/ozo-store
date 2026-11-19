# ADR-0002: Dual Web Surface Processes and `__Host-` Dashboard Cookies

- **Date:** 2026-11-19
- **Status:** Accepted (Founder decision D-Q5)
- **Context:** `002` §2 and `007` §1 require the storefront (`shop.<domain>`) and dashboard (`admin.<domain>`) to use separate URL routing, separate session cookies, and separate CSRF scopes so storefront XSS cannot ride a staff session. In Django, `ROOT_URLCONF`, `SESSION_COOKIE_NAME`, and `CSRF_*` are process-global settings. Furthermore, subdomains of the same apex (`shop.example.com` and `admin.example.com`) are same-site, so `SameSite=Strict` alone does not prevent cookie-tossing from `shop.` with `Domain=.example.com`.
- **Decision:** Run two isolated Gunicorn services from the same Docker image (`web-store` using `config.settings.storefront` and `web-admin` using `config.settings.dashboard`). Configure `web-admin` with `__Host-djet_admin_sid` (`Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, `SESSION_COOKIE_DOMAIN=None`), `CSRF_USE_SESSIONS=True`, and `CSRF_TRUSTED_ORIGINS` restricted strictly to `https://<ADMIN_DOMAIN>`.
- **Consequences:** Subdomain cookie-tossing cannot overwrite `__Host-` cookies, heavy dashboard reporting cannot starve storefront workers, and `web-admin` can later be IP-allowlisted at Caddy with zero code changes.
