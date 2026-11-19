# ADR-0003: Edge Micro-Caching vs. Add-to-Cart CSRF

- **Date:** 2026-11-19
- **Status:** Accepted
- **Context:** `005` §3 caches anonymous catalogue and product HTML pages at Caddy, while `005` §11 requires add-to-cart to work with JavaScript disabled. Embedding a Django per-session CSRF hidden token into cached product HTML breaks either cacheability (if `Vary: Cookie` / uncached) or form submission (if one visitor's CSRF token is cached and served to others).
- **Decision:** Keep full Django CSRF tokens on checkout, account, and all dashboard endpoints (never edge-cached). Treat anonymous cart mutations (`POST /cart/add`, `/cart/update`) as a low-risk CSRF class enforced via `SameSite=Lax` cookies plus a dedicated middleware/decorator verifying `Origin` / `Sec-Fetch-Site: same-origin` headers. Caddy caches GET/HEAD storefront catalogue responses only when no session or cart cookie is present.
- **Consequences:** Preserves >95% edge cache hit rates on anonymous product pages while keeping no-JS add-to-cart functional and protected against cross-origin form submission.
