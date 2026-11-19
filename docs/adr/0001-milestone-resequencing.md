# ADR-0001: Milestone Re-Sequencing

- **Date:** 2026-11-19
- **Status:** Accepted (Founder decision D-Q1)
- **Context:** Blueprint rule #1 requires finishing phase `N` before starting phase `N+1`. Cross-reading `000`–`016` revealed circular dependencies: `004` dashboard CRUD depends on `007` RBAC/shell; `005` DoD requires `006` cart; `003` seed requires `004` variants; `006` checkout requires `008` shipping zones; `003`/`004` DoDs require `015` concurrency and large-dataset benchmarks.
- **Decision:** Group the 16 blueprint phases into 14 dependency-ordered milestones (`M0`–`M13`). Each milestone still executes every deliverable, Definition of Done check, `PHASE-NNN-REPORT.md`, and git tag `phase-NNN` of the phase(s) it closes.
- **Consequences:** Enables strict incremental verification without stubbing auth or skipping tests, while preserving full traceability to the original numbered phases.
