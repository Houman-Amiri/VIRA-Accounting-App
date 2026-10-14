# project brief — V.I.R.A Persian Accounting App

> **Consistent-context brief** for all work on this repository. It records the **actual selected stack** and the **non-negotiable constraints**. Keep it updated after every phase or user amendment. If anything conflicts with §2, **§2 wins**.

| | |
|---|---|
| **Status** | Phase 8 (Installer, Versioned Releases & In-App Delta Updates) ✅ complete — 2026-10-14 · 8-phase plan delivered end-to-end |
| **Master prompt** | [`MASTER_PROMPT.md`](MASTER_PROMPT.md) — compiled requirements; re-read before any phase work |
| **Source request** | [`VIRA_SQLite_No_Docker.md`](VIRA_SQLite_No_Docker.md) — incl. user amendment 2026-10-14 (Phase 8) |
| **Phase 1 docs** | [`docs/product-spec.md`](docs/product-spec.md) · [`docs/data-model.md`](docs/data-model.md) |
| **Phase 2 code** | [`backend/`](backend/) (FastAPI + SQLAlchemy 2.0 + Alembic) · [`scripts/`](scripts/) — 71 tests green, ruff + mypy clean |
| **Phase 3 code** | [`frontend/`](frontend/) (React 19 + TS + Vite SPA) — 40 Vitest tests green, `tsc` clean, production build + live proxy smoke |
| **Phase 6 hardening** | Deployment & DevOps — 127 pytest green (8 new ops tests), ruff + mypy clean; 52 Vitest green; CI/Release workflows + Dependabot, safe migration lifecycle, System & Ops page ([`docs/deployment.md`](docs/deployment.md)) |
| **Phase 7 hardening** | Enhancements & Localization — 144 pytest green (13 new search/storage tests), 63 Vitest green (i18n/fiscal/viewer/analytics); unified search, S3-capable storage, react-i18next fa namespaces, Jalali fiscal year + print-to-PDF, privacy-first Umami ([`docs/deployment.md`](docs/deployment.md) §5) |
| **Phase 8 hardening** | Installer & delta updates — 186 pytest green (50 new update-engine/channel tests), 70 Vitest green (7 new update dialog/badge); Inno «مسیر نصب» installer, schema-versioned latest.json, delta engine + transactional updater with rollback, mandated Persian update dialog ([`docs/deployment.md`](docs/deployment.md) Phase 8) |
| **Pricing source** | [`قیمت نهایی.xlsx`](قیمت%20نهایی.xlsx) — relations compiled/normalized in product-spec §4.3 |

---

## 1. What we are building

A **Persian-only (fa-IR, RTL) accounting & operations app** for a small 3D-printing business: manage **warehouse goods** (3D-printing filaments and produced models) with stockout alarms and scored supplier suggestions; manage **customer orders** with proforma invoices (Word + PDF) and searchable daily/weekly/monthly/annual sales reports; run **production** from order details against inventory, with a **Sales Price Calculations** engine built from the provided Excel model; present a **live landing page** (inventory charts + recent products) and a **fully dynamic supervising dashboard**. Underneath is a strict **double-entry ledger** on SQLite. The app is installed on Windows via an **Inno Setup** installer and updated in-app from **GitHub releases** with delta updates.

## 2. Non-negotiable constraints (always take precedence)

1. **SQLite only** — no PostgreSQL or any other DB server; no DB abstraction assuming server-specific SQL.
2. **No Docker** — no Docker/Compose/Dev Containers/images/runtimes; direct Windows installs with Python, Node.js, venvs, native scripts/services.
3. **Database file outside Git**: default `%LOCALAPPDATA%\VIRA\data\vira.sqlite3`, configurable via `SQLITE_DATABASE_PATH`.
4. **SQLite limits are design constraints**: scaled-integer money, app-level `Decimal` validation, short write transactions, WAL, SQLite-compatible SQL only.
5. **Canonical frontend** = React + TypeScript + Vite SPA backed by FastAPI. No HTMX/Alpine app; Jinja2 only for server-rendered PDFs.
6. **Maintain this `project brief.md`** with the actual selected stack and these constraints.
7. **Phased build**: work strictly per phase via `MASTER_PROMPT.md`; wait for the user's **"proceed"** between phases.
8. **Distribution & updates**: Inno Setup installer with a user-selectable install directory, downloadable from GitHub (Actions artifacts + Release assets); every version tagged `vX.Y.Z`; in-app **Check for updates** announcing *"A new update available, do you want to download and install?"*, installing **only changed parts** (delta updates), with **zero data loss** (see MASTER_PROMPT Phase 8).

## 3. Selected stack (actual)

| Layer | Selection |
|---|---|
| Backend | Python 3.12, **FastAPI**, **Pydantic v2**, **SQLAlchemy 2.0** (typed, `aiosqlite`), **Alembic**; `decimal.Decimal` (ROUND_HALF_EVEN), py-moneyed, Babel, jdatetime |
| Frontend | **React 19 + TypeScript 5+ (strict) + Vite**; TanStack Router/Query v5/Table v8/Virtual; Zustand; React Hook Form + Zod; **decimal.js**; Tailwind CSS + shadcn/ui (Radix); **Vazirmatn** + JetBrains Mono; react-i18next (fa-only), **date-fns-jalali**; cmdk; ECharts/Recharts; react-pdf; openapi-typescript + openapi-fetch |
| Database | **SQLite 3.45+** (WAL, STRICT, FK ON, busy_timeout 5 s): money ×10,000, FX ×100,000,000, UUIDv7 TEXT IDs, FTS5 optional with LIKE fallback |
| Domain libs | Polars/Pandas + openpyxl, ofxtools/mt940/camt, RapidFuzz, scikit-learn (light), WeasyPrint (PDF), python-docx (Word proformas), Pillow + python-magic (uploads), PaddleOCR/Tesseract (optional OCR) |
| Auth/security | pwdlib (Argon2id), Authlib/FastAPI-Users, pyotp + qrcode, cryptography (Fernet/AES-GCM), structlog, slowapi, pydantic-settings |
| Tests/QA | pytest, pytest-asyncio, Hypothesis, Vitest, RTL, Playwright, Bandit, pip-audit, npm audit, ruff, mypy, prettier, eslint |
| Ops (Windows-native) | `setup_windows.ps1`, `start_vira.bat/.ps1`, `stop_vira.bat/.ps1`; Task Scheduler backups; `sqlite3.Connection.backup()` + age/Restic; GitHub Actions (Windows/Ubuntu runners, **no service containers**); Dependabot; uv + pnpm lockfiles; **Inno Setup 6** + `vira-updater.exe` delta updater (manifest + bsdiff) |

## 4. Product scope (one line each — details in `docs/product-spec.md`)

- **Warehouse**: filament/model items (name, weight, unit, color, price, date, supplier name+address), movement-based stock, stockout alarms, scored supplier suggestion (price/quality/delivery).
- **Orders**: customers (name, phone, address), order lifecycle, **proforma invoice → Word + PDF**, sales reports daily/weekly/monthly/annual with search & filters.
- **Production**: BOM-driven production orders from order lines + inventory, consumption/production movements, **Sales Price Calculations** (normalized from `قیمت نهایی.xlsx`).
- **Landing page**: live inventory charts + recent products + KPIs (polling, RTL, themes).
- **Dashboard**: fully dynamic, configurable widgets supervising all modules.
- **Accounting core**: double-entry ledger (Phase 2–5) backing purchases/production/sales.

## 5. Key domain decisions (locked)

- **Money**: never float; scaled integers ×10,000 in SQLite; exact strings (`"1250.5000"`) over JSON; banker's rounding at display.
- **Currency**: canonical stored unit **Toman** (IRT), `1 Toman = 10 Rials` applied exactly once; UI default Toman with Persian numerals.
- **Calendar**: Jalali (Solar Hijri) in the UI everywhere; fiscal year starts **1 Farvardin**; stored dates Gregorian ISO 8601.
- **Localization**: strictly Persian-only `fa-IR`, permanent RTL; no language/numeral toggle; LTR-isolated money/numbers in RTL contexts.
- **Ledger**: ≥2 splits per entry, Σ debits = Σ credits; append-only (corrections via reversing entries); optimistic locking (`version_id` → 409).
- **Pricing**: normalized formula set (product-spec §4.3) — power used in energy cost, nylon included, label counted once, variant-aware commission, configurable buffer; sheet quirks documented and fixed.
- **Supplier score**: `0.40·price + 0.35·quality + 0.25·delivery` (weights configurable).
- **Order statuses**: `DRAFT → CONFIRMED → IN_PRODUCTION → READY → SHIPPED → COMPLETED` (+`CANCELLED` pre-shipment).
- **Updates**: delta-first (manifest + bsdiff), full-installer fallback, transactional apply + rollback, user data untouched.

## 6. Repository layout (target)

```
/backend            FastAPI, SQLAlchemy, Alembic, Python modules
/frontend           React, TS, Vite, TanStack modules
/scripts            PowerShell + .bat (setup, start/stop, migrate, backup, restore, health)
/.github/workflows  CI, release (Inno Setup, deltas, GitHub Releases)
/docs               planning docs (this phase)
project brief.md    ← this file (maintained)
MASTER_PROMPT.md    compiled requirements (maintained)
VIRA_SQLite_No_Docker.md  original request (reference)
قیمت نهایی.xlsx     pricing model source
```
No `/deploy` Dockerfiles, no `docker-compose.yml`, no `.devcontainer`. DB, backups, keys, uploads stay **outside** the repo.

## 7. Phase roadmap & status

| Phase | Scope | Status |
|---|---|---|
| 1 | Initiation & planning (this brief + specs) | ✅ 2026-10-14 |
| 2 | Core stack (back-end: ledger, DB, API, imports, reports, security) | ✅ 2026-10-14 |
| 3 | Core stack (frontend SPA) | ✅ 2026-10-14 |
| 4 | Database & persistence layer | ✅ 2026-10-14 |
| 5 | Integration, auth & security | ✅ 2026-10-14 |
| 6 | Deployment & DevOps (Windows-native) | ✅ 2026-10-14 |
| 7 | Enhancements & localization | ⏳ |
| 8 | Installer, release tags & in-app delta updates | ⏳ |

**Phase 2 highlights** (details in code + tests): exact scaled-integer money (`app/money.py`, never float); double-entry engine with atomic posting/reversal/void, optimistic locking, fiscal-period locks, immutable posted entries (SQLite triggers + service validation); STRICT-table schema via Alembic 0001 with audit trail (JSON snapshots, redaction, trigger-protected); FastAPI REST (health, auth with Argon2id + HttpOnly cookies + CSRF + TOTP, accounts, journal, reports with recursive-CTE rollups + Polars series, bank imports with FITID/hash idempotency + RapidFuzz/sklearn categorization, FX via Frankfurter, content-addressed receipt storage + OCR/PDF (WeasyPrint/Jinja2); APScheduler recurring entries; online backups with restore verification; `scripts/setup_windows.ps1`, `start/stop_vira.bat/.ps1`, `backup_vira.ps1`. Tests: pytest + httpx.AsyncClient + Hypothesis (71 green); ruff + mypy clean.

**Phase 5 highlights** (details in [`docs/security.md`](docs/security.md)): Alembic 0003 (`mfa_recovery_codes`, `api_keys`, `external_credentials`, `webhook_events`, immutable `security_audit_logs`); TOTP secrets envelope-encrypted (MultiFernet `APP_ENCRYPTION_KEY` with rotation) + 10 single-use Argon2id-hashed recovery codes; RBAC wired globally (auditor read-only 403, `ingest_api` keys scoped to draft journal + receipts); 5-minute HMAC sudo step-up gating period reopen / un-reconcile / DB-dump export / API-key CRUD; login rate limit 5/min with exponential lockout; Idempotency-Key auto-generated on every frontend POST/PATCH (stable across retries) + reconciliation finish; silent session refresh + 401 → draft-snapshot → `/login` (TanStack Router); HMAC-SHA256 webhooks with ±5-min freshness + event dedup; resilient httpx+tenacity external clients (timeouts, backoff, Retry-After); strict production boot validation; security headers (HSTS/CSP/XFO/nosniff/Referrer) + strict CORS; defusedxml XXE hardening; CSV formula-injection sanitization; structlog redaction; `/login` page + sudo dialog. Scans: Bandit 0 medium+, pip-audit clean, npm audit down to 1 unfixable dev-only advisory (braces).

**Phase 6 highlights** (details in [`docs/deployment.md`](docs/deployment.md)): GitHub Actions CI without service containers (backend: ruff/mypy/bandit/pip-audit + `uv lock --check` + fresh-SQLite migrations + pytest/Hypothesis; frontend: prettier/eslint/tsc + audit + Vitest + build; contract job regenerates OpenAPI from a live app and fails on drift; Playwright e2e; `windows-native` smoke job) + release workflow on annotated `vX.Y.Z` tags (package_release.ps1 → portable zip + latest.json + SHA256SUMS + Persian notes; Inno/delta steps wired for Phase 8) + Dependabot (uv/npm/github-actions only); safe SQLite migration lifecycle (`migrate_vira.py/.ps1`: single-process lock → verified online backup → `alembic upgrade head` → FK/revision/debit-credit gate → tested restore path); Sudo-protected System & Operations SPA page + API (version/commit/revision/scheduler/last-backup, one-click encrypted snapshot with path-traversal-guarded download, restore-verification drill, «بررسی به‌روزرسانی» via latest.json); rotating file logs (2 MB × 5) + `/health/ready` scheduler status; `uv.lock` + frozen-lockfile sync policy; ESLint 9 flat config + Prettier added.

**Phase 7 highlights** (Enhancements & Localization): unified search rewritten (`services/search.py`) — FTS5 + LIKE under one parameterized path with entry-number/memo coverage, Decimal numeric tokens mapped to scaled-INTEGER amount matches (no float money), RapidFuzz re-rank + dedupe + bounded pagination; pluggable storage (`services/storage.py`) — `StorageBackend` protocol with local (Phase-2-compatible) and S3-compatible backends (`STORAGE_PROVIDER=s3`, lazy boto3, SSE, sha256 content-addressed `ab/cd/` layout, 300-s presigned GET → `GET /documents/receipts/{id}` 302, dedup by hash), faceted `<ReceiptViewer/>` (react-pdf page flips + react-zoom-pan-pinch zoom/rotate/pan); Persian-only i18n (react-i18next, `/locales/fa/{common,ledger,reports,validation}.json` namespaces — no English strings, no language switcher), logical CSS properties (ms-/me-/ps-/pe-/border-s/text-start) audit complete, Vazirmatn + JetBrains Mono, LTR-isolated numerics via `.num`, Jalali everywhere with fiscal year = full Iranian year starting 1 Farvardin (`lib/fiscal.ts` + jalaali-js), Jalali print-to-PDF report headers; `date-fns-jalali` on-screen + print path (backend `jdatetime`/Babel wiring lands with the future server-side PDF pipeline); decimal.js/scaled-integer money audit re-verified with centralized `<Money/>`; privacy-first Umami (`lib/analytics.ts`) — script injected only on `VITE_UMAMI_*`, typed `useAnalytics()` with zero-PII redaction (query stripping, UUID masking, key whitelist) wired to the four workflow events; Ctrl+K command palette + journal/accounts filter bars query `GET /api/v1/search`.

**Phase 8 highlights** (Installer, Versioned Releases & In-App Delta Updates — the 8-phase plan is now complete): Inno Setup 6 installer (`installer/vira.iss`) with the mandatory «مسیر نصب» directory step (`DisableDirPage=no`, default `{autopf}\VIRA`, `/VERYSILENT /DIR=` automation), `InstallDir` recorded at `HKLM/HKCU\SOFTWARE\VIRA`, optional desktop/Start-menu/launch-at-login/backup-job tasks, and an uninstaller that never touches `%LOCALAPPDATA%\VIRA` user data without an unchecked opt-in; strict SemVer `vX.Y.Z` tagging with `CHANGELOG.md` and a single version source of truth; `latest.json` schema_version 1 (unknown versions refused) with `full_installer` + `deltas[]` + `files_manifest_sha256`, ETag-cached GitHub checks, 403/429 Persian retry-later, `APP_UPDATE_URL` mirror override and optional Ed25519 signatures (`scripts/sign_update.py`); delta engine (`update_engine.py`) — per-file SHA-256 manifests, manifest diffing, `VIRA-vX.Y.Z-delta-from-vA.B.C.zip` packages (`update.json` + `files/` + BSDIFF40 `patches/` for >256 KB files + `delete.json`), client selection delta → chain → full installer (a delta download is a small fraction of the setup, never a full re-download); transactional updater (`vira_updater.ps1` → `vira-updater.exe` via ps2exe): named mutex + lock file, graceful stop, rollback snapshot of every scheduled file, hash-verified apply + bsdiff patches, manifest rewrite, relaunch — any failure restores the previous version with the mandated Persian error «خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.» and the log path; mandated in-app UX: «بررسی به‌روزرسانی» (sudo) + non-blocking startup badge + RTL dialog «به‌روزرسانی جدید موجود است» / «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟» with «دانلود و نصب» / «بعداً» / «مشاهدهٔ جزئیات», download progress (delta size), verification status and restart-to-finish; zero data loss: pre-update SQLite backup + rollback snapshot retained until health checks pass, verified restore path tested; CI publishes the setup **both** as a GitHub Actions artifact and as an immutable Release asset alongside deltas, `latest.json`, `SHA256SUMS` and Persian notes, with a Windows smoke test (silent install honoring /DIR, delta upgrade asserting delta-sized bytes, data checksum identical, forced-failure rollback).

**Phase 3 highlights** (`frontend/`): React 19 + TypeScript strict + Vite, typed client generated from the backend OpenAPI (`openapi-typescript` + `openapi-fetch`, CSRF interceptor); decimal.js money math (never JS number), `<Money />` with ISO code + inflow/outflow colors + accounting negatives; Persian RTL fa-IR throughout (Vazirmatn + JetBrains Mono, tabular-nums, Persian digits, Jalali dates via `date-fns-jalali`); TanStack Router (URL params) + Query v5 + Zustand; TanStack Table v8 + Virtual (50k-row grid with pinned summary footer); journal multi-split form (RHF + Zod + useFieldArray, live Σdebit=Σcredit superRefine, auto-balance); cmdk + react-hotkeys-hook command palette (Ctrl+K); bank-import wizard (PapaParse + react-dropzone, client-side column mapping) + dual-pane reconciliation with confidence badges (amount/date/description/ref weights, auto ≥85%); statements with ECharts; pricing calculator normalized from `قیمت نهایی.xlsx` (all 14 output lines); receipt upload with OCR status. 40 Vitest tests green, `tsc` clean, Vite build green, live smoke (login → draft → post → balanced trial balance through the dev proxy). Playwright config + smoke specs included (browser download blocked in this sandbox — runs on dev machines).

**Phase 4 highlights** (persistence layer): SQLAlchemy `TypeDecorator`s (`ScaledMoneyType`/`ScaledFxRateType`) exposing `Decimal` while persisting scaled INTEGERs; Alembic `0002_persistence` — `currencies` registry, `reconciliation_sessions` (+ split link, `ON DELETE SET NULL`), `idempotency_keys`, `account_balance_snapshots`, `v_account_balances` rollup view, keyset index `(transaction_date DESC, id DESC)`, FTS5 `search_fts` + trigger sync (LIKE fallback tested); `Idempotency-Key` on journal creation (atomic claim + replay, 409 on reuse); keyset/cursor pagination (`X-Next-Cursor`); `GET /api/v1/search` (FTS5 + RapidFuzz, forced LIKE mode); reconciliation session API (create/link/complete/abandon + progress vs. ending−beginning); monthly snapshots reconciling with the view; encrypted backup bundles (Fernet + PBKDF2, receipts + manifest, restore verifies `integrity_check`/`foreign_key_check`/migration version/ledger balance) + `backup_vira.ps1 -InstallScheduledTask`; idempotent seeds for both personal + business charts, currencies registry, opening-balance equity (3900); concurrency tests (serialized single DRAFT→POSTED transition, BEGIN IMMEDIATE retries), overflow/`CHECK`/FK tests via raw SQL; benchmark on 25k entries/50k splits (keyset 0.15 ms, FTS5 0.22 ms vs LIKE 2.9 ms). **Toman/Rial resolved**: ledger stores Rials (IRR), UI displays Tomans ÷10 applied exactly once at the presentation edge (see `docs/data-model.md` §8).

## 8. Working agreements

- One phase at a time; deliver per the master prompt's Definition of Done; stop and wait for **"proceed"**.
- Re-read `MASTER_PROMPT.md` at the start of each phase; update this brief + master prompt when requirements change.
- Never commit DB files, secrets, backups, uploads, or large build artifacts.
- All user-facing text in professional Persian; tests and lint green before a phase is called done.
