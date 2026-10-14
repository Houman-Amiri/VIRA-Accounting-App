# Changelog

All notable changes to V.I.R.A are documented here. Versions follow strict
SemVer `MAJOR.MINOR.PATCH`; every released version has an immutable annotated
git tag `vX.Y.Z`. Releases are published on GitHub Releases with the Inno Setup
installer, delta packages, `latest.json`, `SHA256SUMS` and Persian notes.

## [Unreleased]

## [1.0.1] — 2026-10-15

First **published** release — the complete 8-phase plan with a green CI/CD
pipeline. The `v1.0.0` tag exists but was never published (the workflow file
was invalid at load time; tags are immutable, so fixes ship as `v1.0.1`).

### Fixed — CI/CD pipeline (all five jobs green)
- Workflow validation: `runner.temp` is illegal in job-level `env` — moved to
  step-level env (every run before this failed at load time).
- Declared `bandit` + `pip-audit` in the dev extra (`uv run` died command-not-found).
- `uv sync --frozen` installs no extras — CI syncs with `--all-extras`.
- Prettier: 16 files formatted that the Phase 6 check never wrote.
- Dev-mode boot: `optimizeDeps.exclude` on react-dropzone/react-pdf served raw
  CJS deps (`attr-accept`, `warning`) with no default export — the app never
  mounted in dev (blank page). Full prebundling; pdf.worker via `?url`;
  `pdfjs-dist` as a direct dependency.
- Journal form: the live zero-balance error never rendered (RHF 7.90
  useFieldArray swallows array-level resolver errors) — rendered from the
  computed totals; zod remains the submit gate.
- E2E: deterministic `/login` flow with seeded owner user, account selection
  in the journal test, webServer 120 s timeouts.

## [1.0.0] — 2026-10-15 (never published)

(Superseded by 1.0.1 before publication — see above.) First public release
of the complete 8-phase plan (Persian accounting, Windows-native, SQLite-only).

### Added — Phases 1–7
- Phase 1–2: product spec + data model, FastAPI backend (SQLAlchemy 2.0 +
  Alembic), scaled-INTEGER money (×10 000; FX ×1e8) with decimal.js at the
  presentation edge, Persian RTL Jalali UI (React 19 + TS + Vite + TanStack).
- Phase 3–4: full SPA (journal, accounts, bank import, reconciliation,
  statements, price calculator, receipts), persistence layer (TypeDecorator
  money columns, FTS5 search, idempotency keys, keyset pagination,
  reconciliation sessions, monthly snapshots, encrypted backups).
- Phase 5: RBAC + TOTP/recovery codes + 5-minute sudo step-up, login rate
  limiting, HMAC webhooks, resilient external clients, security headers,
  Idempotency-Key on every mutation, draft recovery on 401.
- Phase 6: GitHub Actions CI/Release without service containers, safe SQLite
  migration lifecycle (migrate_vira.py/.ps1), sudo-gated System & Operations
  page/API, rotating logs, `/health/ready`, Dependabot, ESLint 9 + Prettier.
- Phase 7: unified search (FTS5 + LIKE parameterized, Decimal numeric tokens,
  RapidFuzz), pluggable storage (local + S3-compatible, sha256 content-addressed,
  presigned delivery, faceted receipt viewer), Persian-only react-i18next
  namespaces, Jalali fiscal year (1 Farvardin) + Jalali print-to-PDF headers,
  privacy-first Umami analytics with zero-PII redaction.

### Added — Phase 8: Installer, Versioned Releases & In-App Delta Updates
- Inno Setup 6 installer (`installer/vira.iss`) with the mandatory «مسیر نصب»
  (select where to install) page, `InstallDir` recorded in `HKLM/HKCU\SOFTWARE\VIRA`,
  optional tasks (desktop/Start menu/launch-at-login/backup job), and an
  uninstaller that keeps `%LOCALAPPDATA%\VIRA` user data unless explicitly opted in.
- Delta update engine (`backend/app/services/update_engine.py`): per-file
  SHA-256 manifests, manifest diffing, `VIRA-vX.Y.Z-delta-from-vA.B.C.zip`
  packages (`update.json` + `files/` + bsdiff `patches/` + `delete.json`),
  client-side selection (delta → delta chain → full installer), BSDIFF40 apply.
- Update channel (`backend/app/services/update.py`): GitHub Releases +
  `latest.json` (schema_version 1, unknown versions refused), ETag caching,
  403/429 Persian retry-later, `APP_UPDATE_URL` mirror override, optional
  Ed25519 signature verification (`scripts/sign_update.py`).
- Transactional updater helper (`scripts/vira_updater.ps1` → `vira-updater.exe`):
  mutex + lock file, graceful stop, rollback snapshot, verified apply, manifest
  rewrite, relaunch; any failure restores the previous version
  («خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.»).
- In-app update UX: «بررسی به‌روزرسانی» + startup badge + mandated dialog
  «به‌روزرسانی جدید موجود است» / «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z).
  آیا می‌خواهید دانلود و نصب شود؟» with «دانلود و نصب» / «بعداً» / «مشاهدهٔ جزئیات»,
  download progress, verification status and restart-to-finish step.
- CI: release workflow compiles the installer + `vira-updater.exe`, generates
  deltas vs the last K = 3 tags, uploads the setup as a GitHub Actions artifact
  and as an immutable Release asset; Windows smoke test (silent install, delta
  upgrade with size assertion, data-preservation checksum, forced-failure
  rollback).
