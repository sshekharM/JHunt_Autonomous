# CI Map

Extracted from CI configs at 2026-09-23T06:44:50.330Z. Line-based extraction — verify anything surprising against the source file.

## .github/workflows/deploy.yml

| category | command |
|---|---|

## .github/workflows/security.yml

| category | command |
|---|---|

## Harness alignment

- CI enforces **no coverage** — the harness ratchet (80% floor) is stricter than this project's own bar. Confirm that is intended before /auto runs.
- CI runs no linter — the harness lint-on-save is the only lint gate.
- CI runs **no tests** — every regression guarantee comes from harness gates alone.
