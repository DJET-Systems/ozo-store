# ADR-0004: One Storefront Engine, Four Vertical Presets, Extensible

- **Date:** 2026-11-19
- **Status:** Accepted (Founder decision D-Q8)
- **Context:** Seven reference UI mockups (`docs/ui-references/`) define a clean default storefront look alongside tailored experiences for four target verticals: Mobile & Electronics, Clothing, Food (Arabic RTL default), and Mini-Market. Maintaining four separate template trees would multiply maintenance and break the add-on/preset architecture.
- **Decision:** Build one server-rendered storefront template + HTMX engine parameterized by (1) CSS custom property design tokens (`--bg`, `--accent`, `--radius-*`, font family), (2) composable section lists (`StoreSettings.home_sections`), (3) polymorphic product-card display flags (`aspect_ratio`, condition badge, size strip, unit-step stepper, sold-out-today), and (4) explicit `_ar`/`_en` columns on models (`D-Q4`). Each vertical preset ships as a declarative `preset.yaml` + fixtures under `apps/presets/<code>/`.
- **Consequences:** All four launch presets and future verticals share one fast, tested, RTL-safe rendering engine with zero code duplication.
