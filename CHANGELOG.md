# Changelog

All notable changes to V.I.R.A are documented here. Versions follow strict
SemVer `MAJOR.MINOR.PATCH`; every released version has an immutable annotated
git tag `vX.Y.Z`. Releases are published on GitHub Releases with the Inno Setup
installer, delta packages, `latest.json`, `SHA256SUMS` and Persian notes.

## [Unreleased]

## [1.0.4] — 2026-10-15

v1.0.3 installed and ran correctly, but published **no delta packages** — the
delta builder guessed the previous release's portable-zip filename and silently
skipped every base it could not fetch, so updates fell back to the full
installer.

### Fixed
- **Delta discovery** — `build_deltas` now asks the GitHub API for each previous
  release's portable asset (the filename varied: `VIRA-v1.0.0.zip` vs
  `vira-v1.0.2-portable.zip`) instead of guessing, and its `latest.json`
  `deltas[]` entries point at assets that are actually published.
- **Smoke leg 2 is the real update path** — it downloads the previous release's
  portable install, applies the matching delta with the shipped updater, and
  asserts the install reaches the new version with rewritten manifests (and a
  delta strictly smaller than the setup). The old leg applied a delta onto a
  fresh same-version install, which never happens in the field.

### Verified
- v1.0.3's install experience: silent install, shortcut resolution via the
  Windows shell, first-run migrate+seed+credentials, healthy SPA on
  `http://127.0.0.1:8787` — all CI-gated (smoke legs 1 and 5).

## [1.0.3] — 2026-10-15

Fixes the broken installed experience reported after v1.0.2 (shortcut points
at a missing file; launch does nothing).

### Fixed
- **Shortcuts targeted a file that never existed.** The installer pointed
  Desktop/Start-Menu/Startup shortcuts and the finish-page «اجرای V.I.R.A» at
  `{app}\start_vira.cmd`, but no such file was ever created — hence
  «Missing Shortcut» and silent launch failures. `scripts/start_vira.cmd` now
  ships at the payload root: finds Python (bundled → dev venv → PATH), runs the
  safe migration + seed (idempotent), mints and shows owner credentials on
  first run (`%LOCALAPPDATA%\VIRA\first-run-credentials.txt`), starts uvicorn
  in a visible log window and opens `http://127.0.0.1:8787` when health is green.
- **Bundled CPython 3.11** (python-build-standalone via uv) is now staged with
  the app — the installed app runs on machines without a system Python.
- **SPA serving in the installed layout** — `spa_static_dir()` now resolves
  `{app}\static` (installed) as well as `<repo>/frontend/dist` (dev); before,
  the mounted path pointed outside the install directory and `/` was a 404.
- **`migrate_vira.py` on installed payloads** — `backend/alembic(.ini)` is
  staged alongside the app so first-run migrations work.
- **Delta baseline integrity** — `gen_delta` now packs `install_manifest.json`
  + `version.json` into every delta (the updater rewrites them after apply;
  without them the next delta would diff against a stale baseline).
- **Delta patches without `tools\bspatch.exe`** — `scripts/bspatch.py`
  (pure-Python, wraps the tested engine applier) is the updater's fallback,
  run by the bundled interpreter.
- **New smoke leg 5** resolves every installed shortcut via the Windows shell
  (any missing target fails CI), then really launches the app and asserts
  `/api/v1/health/live`, the SPA at `/`, and the first-run credentials file.

## [1.0.2] — 2026-10-15

First **published** release. `v1.0.0` and `v1.0.1` tags exist but were never
published (pipeline debugging; tags are immutable, so each fix shipped as a
new patch version). Validated end-to-end via `[release-dry-run]` runs before
tagging: Inno Setup compile, `vira-updater.exe` (ps2exe), delta generation,
and the Windows install/upgrade/rollback smoke test all pass.

### Fixed — release pipeline
- `InitializeUninstall` must be a Boolean function (Inno compile error).
- `x64` instead of `x64compatible` for broad Inno 6 compatibility.
- Smoke harness: forced-failure rollback fires after the snapshot (the thing
  being tested); updater `Fail` throws (catchable) instead of `exit`; the
  forced-failure stage carries its own `update.json`; `/DIR` quoted.

## [1.0.1] — 2026-10-15 (never published)

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
