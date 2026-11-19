## Summary

<!-- Describe what this PR changes and which Milestone / Phase it belongs to. -->

## Verification

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run mypy apps/core apps/inventory apps/orders apps/payments` passes
- [ ] `uv run lint-imports` passes
- [ ] `uv run pytest` passes against PostgreSQL 18

## Security Checklist (Phase 014 §6)

- [ ] New endpoints require authentication and a named permission, or are intentionally public and rate limited.
- [ ] Inputs validated on the server; outputs escaped; no raw SQL string building.
- [ ] No secrets in code, logs, fixtures or test snapshots.
- [ ] New webhook or file-handling code follows Phase 014 §§2–3.
- [ ] Sensitive fields are permission-gated and excluded from exports for lower roles.
- [ ] Audit log entries added for new privileged actions.
- [ ] Negative tests exist (unauthorised, replayed, oversized, malformed).
- [ ] Dependencies added are pinned, hashed, licence-checked and justified.
