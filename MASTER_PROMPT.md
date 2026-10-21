# V.I.R.A — Master Prompt (Compiled Requirements)

> **Purpose.** This file is the compiled master prompt for the Persian Accounting App **V.I.R.A**, distilled from `VIRA_SQLite_No_Docker.md` (source of truth for the original request) plus subsequent user amendments (latest: 2026-10-14 — Inno Setup installer, release tags, and in-app delta updates, compiled as Phase 8). It exists so the implementing AI can re-read it at any time and stay aligned across all phases without re-parsing the raw request file.
>
> **Rule of precedence.** If any later instruction, section, or implementation detail conflicts with **§2 Non-Negotiable Architecture Constraints**, the constraints win.
>
> **Execution protocol.** The app is built **separately in phases** (§4). Phase 1 starts only when the user says **"proceed"**. After each phase, wait for the user's go-ahead before starting the next.

---

## 1. Role

You are a **world-class Iranian full-stack Windows app developer** — expert in programming, security, database design, and UI/UX — working for the **V.I.R.A** company, which is demanding an accounting application.

---

## 2. Non-Negotiable Architecture Constraints (apply in every phase)

1. **SQLite only.** No PostgreSQL, no other database server, no DB abstraction that assumes server-specific SQL features.
2. **No Docker of any kind.** No Docker, Docker Compose, Dev Containers, container images, or container runtimes. Install and run directly on Windows using Python, Node.js, a Python virtual environment, and native Windows scripts/services.
3. **Database file location.** Local SQLite file stored **outside the Git repository**, defaulting to `%LOCALAPPDATA%\VIRA\data\vira.sqlite3` (single Windows user). Path configurable via `SQLITE_DATABASE_PATH`.
4. **SQLite limitations are design constraints.** Integer-scaled money storage, application-level `Decimal` validation, short write transactions, WAL mode, SQLite-compatible SQL only. Treat SQLite typing, locking, and trigger limits as hard boundaries.
5. **Canonical frontend** is the **React + TypeScript + Vite SPA** (Phase 3), backed by **FastAPI**. Never build a separate HTMX/Alpine frontend. Jinja2 is allowed **only** for server-rendered PDF documents.
6. **`project brief.md`** must be created and maintained inside the repo, containing the actual selected stack and these non-negotiable constraints (Phase 1 deliverable).
7. **Phased build + master prompt.** Compile requests into this master prompt and keep it in the repo. Wait for the user's **"proceed"** before starting each phase, beginning with Phase 1.
8. **Distribution & updates.** Ship the app as an **Inno Setup** installer with a user-selectable install directory, downloadable from GitHub (Actions artifacts + versioned Release assets); tag every version with `vX.Y.Z`; provide an in-app **Check for updates** system that fetches releases from GitHub, announces "A new update available, do you want to download and install?", installs **only the changed parts** (never a full re-download when a delta exists), and **never loses user data** (see Phase 8). No container-based packaging or update channels.

---

## 3. Product Vision & Domain (Phase 1 core idea)

**V.I.R.A** is an accounting app to manage a small 3D-printing business: **warehouse goods (3D-printing filaments and produced models), customer orders, and production**.

### 3.1 Warehouse (انبار)
- Item attributes: **filament name, weight, entity/unit, color, price, date, supplier name and address**.
- Features:
  - **Stockout / inventory shortage alarm.**
  - **Supplier suggestion** to buy from, based on a user-given supplier score covering **price, quality, and delivery time** of their shipments.

### 3.2 Orders (سفارش‌ها)
- Order attributes: **date, customer full name, phone number, address, order details, status**.
- Features:
  - **Sales Proforma Invoice** with **Word and PDF export**.
  - **Sales reports** — daily, weekly, monthly, annual — with **search and filter** ability.

### 3.3 Production (تولید)
- Production is based on **order details** and **warehouse inventory**.
- Feature: a **Sales Price Calculations page** based on the repo Excel file `قیمت نهایی.xlsx` (read all cells, extract texts and formulas, compile every relation, and implement it as perfectly as possible — see **Annex A** for the extracted cell/formula map).

### 3.4 Landing page & Dashboard
- A **live-looking landing page** that simultaneously shows:
  - **Warehouse inventory** presented in a **beautiful chart** plus **recent products with some details**.
- The core data entities are **"products to sell"** and **warehouse inventory items**.
- A **fully dynamic dashboard** that **controls and supervises everything**.

---

## 4. Phase Plan (compiled)

### Phase 1 — Initiation & Planning
1. Write the **main idea / product spec** (Warehouse, Orders, Production as in §3).
2. Specify the **live landing page** with inventory charts + recent products.
3. Define **core data entities, fields, and relationships**: "products to sell", warehouse inventory items, and the fully dynamic supervising dashboard.
4. Write **`project brief.md`** for consistent AI context (actual selected stack + §2 constraints).

### Phase 2 — Core Stack (Back-end)

| # | Module | Mandated choices & rules |
|---|--------|--------------------------|
| 1 | **Core ledger & double-entry engine** | `decimal.Decimal` with `ROUND_HALF_EVEN`; **never `float`** for money. Money stored as `INTEGER` scaled ×10,000; FX rates ×100,000,000. `py-moneyed` + `Babel` for ISO 4217 currency pairing and locale formatting. Pydantic v2 enforces: every `JournalEntry` ≥ 2 `TransactionSplit` lines; Σ debits = Σ credits per currency before posting. Optional `beancount` compatibility. |
| 2 | **Database & immutable audit trail** | SQLite 3.45+ only, file outside repo. Pragmas: `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout≈5000ms`, verified at startup. `STRICT` tables where compatible. SQLAlchemy 2.0 typed (`Mapped`, `mapped_column`) + `aiosqlite` + **Alembic** versioned migrations (test upgrade **and** downgrade on temp SQLite files). Append-only ledger: reconciled/locked transactions never hard-deleted or silently overwritten; corrections via contra/reversing entries. Audit snapshots as JSON `TEXT` with UTC ISO-8601; protect audit records from ordinary update/delete; record actor, action, table, record ID, timestamp; redact secrets. |
| 3 | **API layer** | **FastAPI** modular routers, DI for DB sessions/auth/ledger services, Pydantic v2 serialization, OpenAPI/Swagger documented JSON REST. |
| 4 | **UI direction** | React + Vite SPA is canonical (Phase 3). Jinja2 HTML templates **only** for invoices/printable PDFs. Design system: Tailwind + shadcn/ui (Radix), full Persian RTL, accessible keyboard interaction, financial data tables, status badges, modals, responsive, dark/light themes. |
| 5 | **Bank statements** | Ingestion via Polars or Pandas + openpyxl (CSV/XLSX; normalize dates, strip payee noise, map columns). Parse OFX/QFX (`ofxtools`), MT940/CAMT.053 (`mt940`, `camt`) with **FITID** idempotency. Optional automated feeds via `httpx` (GoCardless Bank Account Data / Plaid / SimpleFIN). Smart categorization/auto-match via `RapidFuzz` + lightweight scikit-learn classifier. |
| 6 | **Reporting & dashboards** | Balance Sheet, Income Statement, Cash Flow, Trial Balance via SQL `WITH RECURSIVE` account-tree rollups + Polars. Interactive charts (Plotly or Apache ECharts): Net Worth trendlines, Income→Expense Sankey, Cash Flow waterfalls, budget burn-down. |
| 7 | **Receipts, OCR & PDF invoicing** | PDF generation with **WeasyPrint** from styled HTML/CSS. OCR: PaddleOCR or Tesseract locally; optional structured extraction via Instructor + LiteLLM into strict Pydantic models (merchant, date, subtotal, tax, total, currency, line_items). Attachments stored content-addressed by **SHA-256**, linked to `JournalEntry`. |
| 8 | **Multi-currency & scheduling** | APScheduler or Huey for recurring journal entries (rent, subscriptions, depreciation, payroll) via cron intervals. Daily FX from Frankfurter API (`httpx`) stored in `ExchangeRate` for realized/unrealized FX gain/loss. |
| 9 | **Testing** | `pytest` + `httpx.AsyncClient` (unit/integration, isolated test transactions). `Hypothesis` property tests: randomized multi-split transactions, edge-case decimals, currency conversions — mathematically prove double-entry balance invariants and precision retention. |
| 10 | **Security, backups & self-hosting** | Argon2id (`pwdlib`), HttpOnly session cookies, CSRF, optional TOTP (`pyotp`); FastAPI-Users / Authlib. Native Windows deployment: `start_vira.bat` / `stop_vira.bat` (or PowerShell), optional Task Scheduler startup. Bind `127.0.0.1` by default; LAN only via explicit setting + Firewall rule; remote access documented via native **Tailscale**. Secrets in env vars / Windows Credential Manager — never in repo or plaintext DB. Backups via `sqlite3.Connection.backup()` (never a naive `.db` copy ignoring WAL), scheduled with Task Scheduler, optional `age`/`Restic` encryption. Restore-verification scripts: restore to temp path → `PRAGMA integrity_check` + `PRAGMA foreign_key_check` → accounting-invariant checks. |

### Phase 3 — Core Stack (Frontend)

| # | Module | Mandated choices & rules |
|---|--------|--------------------------|
| 1 | **Framework & types** | React 19 + TypeScript 5+ + Vite; strict TS (`"strict": true`, `"noImplicitAny": true`). API types generated from FastAPI `openapi.json` via `openapi-typescript` + `openapi-fetch`. `decimal.js` for all client money math — **never native JS `number` for monetary calculations**. Money in API payloads as exact strings (`"1250.5000"`). |
| 2 | **Routing & state** | **TanStack Router** (URL search params = single source of truth for filters/date ranges/pagination, validated with Zod/Valibot). **TanStack Query v5** for fetching, optimistic updates (e.g., Cleared toggles), cache invalidation across balances/registers/reports. **Zustand** for ephemeral UI state (split panes, reconciliation sessions, sidebar, shortcut modes). |
| 3 | **Design system** | Tailwind + shadcn/ui (Radix): dialogs, popovers, command palettes, date-range pickers, comboboxes; dark/light themes. **Vazirmatn** for text and all numbers (user amendment, 2026-10-17); `tabular-nums` on all financial figures. Reusable `<Money />` component: ISO 4217 formatting, inflow/outflow coloring, accounting parentheses `($1,234.56)` for negatives. |
| 4 | **Data grids** | **TanStack Table v8 + TanStack Virtual** — smooth 50,000+ row account registers at 60 FPS, column resizing, multi-column sorting, pinned summary footers (Cleared Balance, Unreconciled Delta, Working Balance), row selection, inline editing. |
| 5 | **Journal entry form** | React Hook Form + Zod + decimal.js; `useFieldArray` dynamic multi-split rows (Account, Memo, Debit, Credit, Currency); `.superRefine()` blocks submit unless Σ debits − Σ credits = 0 and ≥ 2 populated splits. Smart auto-balance into next empty Debit/Credit on focus; fuzzy searchable hierarchical account combobox. |
| 6 | **Keyboard-first** | `cmdk` + `react-hotkeys-hook`: `Cmd/Ctrl+K` command center (navigate, import, switch report periods, create transactions). Spreadsheet-style arrow/`Tab`/`Enter` cell traversal in grids and split forms. |
| 7 | **Bank import & reconciliation** | `PapaParse` + `react-dropzone` for client-side CSV header preview/column mapping before upload. Side-by-side dual-pane reconciliation: bank rows vs suggested ledger matches, confidence badges, one-click match/create, live `Difference to Reconcile` header. |
| 8 | **Statements & charts** | Expandable tree tables (Balance Sheet, P&L, Cash Flow, Trial Balance) with click-to-drill-down drawers into journal entries. Charts via Apache ECharts or Recharts: Net Worth areas, income→expense Sankey, cash-flow waterfalls, budget gauges. |
| 9 | **Receipt viewer** | `react-pdf` + `react-zoom-pan-pinch`: receipts side-by-side with OCR-extracted fields for human-in-the-loop verification. |
| 10 | **Testing** | Vitest + React Testing Library (decimal.js math, Zod validators), Playwright E2E for full bookkeeping workflows. Audit and fix accessibility and responsive issues. |

### Phase 4 — Core Stack (Database & Persistence)

- **Engine config:** SQLite 3.45+; WAL, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`; prefer `STRICT` tables; verify at startup.
- **File:** `%LOCALAPPDATA%\VIRA\data\vira.sqlite3`, configurable `SQLITE_DATABASE_PATH`; parent dir created securely; never commit DB, WAL/SHM, backups, or attachments.
- **Type rules:** IDs = `TEXT` UUIDv7; dates = ISO `YYYY-MM-DD` `TEXT`; timestamps = UTC ISO-8601 `TEXT`; JSON = validated JSON `TEXT`; booleans = `INTEGER` 0/1 with `CHECK`. Money = scaled `INTEGER` (×10,000, 4 decimals); FX rate = scaled `INTEGER` (×100,000,000). Central SQLAlchemy `TypeDecorator` exposes `Decimal` to services. Never `REAL`/float/JS-number for money; quantize + overflow-check before writes; totals within signed 64-bit range.
- **Core tables:**
  - `accounts` — `id`, unique `code`, `name`, `account_type` (`ASSET|LIABILITY|EQUITY|INCOME|EXPENSE` CHECK), `normal_balance` (`DEBIT|CREDIT` CHECK), `currency`, self-FK `parent_id`, materialized `path` (e.g. `1000.1010`), `is_placeholder`, `is_active` (0/1), `version_id`. **No posting to placeholder accounts.**
  - `journal_entries` — `id`, unique sequential `entry_number`, `transaction_date`, `posted_at`, `payee`, `description`, `status` (`DRAFT|POSTED|VOIDED`), `reversed_entry_id` self-FK, `metadata_json`, `version_id`.
  - `transaction_splits` — `id`, FKs `journal_entry_id`/`account_id` (`ON DELETE RESTRICT`), `memo`, `debit`/`credit` scaled INT default 0, `currency`, `exchange_rate` scaled INT default 100000000, `functional_debit`/`functional_credit` scaled INT, `reconciliation_status` (`UNRECONCILED|CLEARED|RECONCILED`). Row CHECK: `debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0) AND (debit > 0 OR credit > 0)`.
  - `fiscal_periods` — `start_date`, `end_date`, `is_closed`, `closed_at`; reject writes into closed periods (service checks + SQLite triggers; split triggers join parent entry for the date).
  - `audit_logs` — `id`, `table_name`, `record_id`, `action`, `old_data`/`new_data` JSON TEXT, `changed_at`, `actor_id`; immutable; redact secrets.
  - `exchange_rates` — `base_currency`, `quote_currency`, `rate_date`, `rate` (×1e8), `source`; `UNIQUE (base, quote, date)`.
  - `bank_import_batches`, `bank_statement_lines` — dedup via `UNIQUE (account_id, external_fitid)` and fallback SHA-256 `dedup_hash`; each batch committed atomically; repeat uploads never duplicate entries.
  - `reconciliation_sessions` — account, statement date, beginning/ending balances (scaled), status, completion time; linked splits preserved for audit.
  - `idempotency_keys` — `key` (unique TEXT UUID), `request_hash`, `response_status`, `response_body`, `created_at`, `expires_at`; atomic claim+store so retries never duplicate.
  - `account_balance_snapshots` (monthly rollups) + useful views.
- **Posting validation (authoritative + atomic):** before `DRAFT → POSTED`, one ledger service validates inside one write transaction: ≥ 2 valid splits and exact integer-scaled functional debits = credits; optional `BEFORE UPDATE OF status` trigger as secondary guard. Insert/update splits, verify invariants, flip status, commit — all-or-nothing. SQLite has no deferrable constraint triggers; no partially written/unbalanced posted entries. Test concurrent posting and integer overflow.
- **Immutability:** posted/reconciled rows reject deletion or amount/account changes (services + triggers); corrections = reversing `JournalEntry` via `reversed_entry_id`.
- **Concurrency:** SQLAlchemy `version_id_col` on `journal_entries` and `accounts`; clients send `version_id` on update; mismatch → HTTP 409. `BEGIN IMMEDIATE` for ledger writes, busy-timeout + bounded retries on `database is locked`; single-writer design (no advisory locks).
- **Indexing & search:** B-tree indexes `transaction_splits (account_id, journal_entry_id)`, `journal_entries (transaction_date DESC, id DESC)`; keyset/cursor pagination (stable tie-breakers, no unbounded OFFSET). Search: parameterized `LIKE` + FTS5 when available, tested `LIKE` fallback; RapidFuzz over bounded candidates. No pg_trgm/GIN/ILIKE/search server.
- **Migrations:** Alembic for all schema changes; test upgrade/downgrade on temp files; batch migrations for SQLite table rebuilds; preserve indexes/triggers/data/FKs. Deterministic naming: `ix_`, `uq_`, `ck_`, `fk_`.
- **Seeding:** idempotent seed scripts — chart of accounts (personal-finance & small-business), supported currencies, opening-balance equity; safe to run repeatedly.
- **Testing & backups:** pytest + Hypothesis against **on-disk temp SQLite** files, exercising real CHECKs, FKs, triggers, migrations, scaled-decimal conversion, import idempotency, locking, double-entry invariants. Backups via online backup API + encryption + receipt-storage copy; restore to temp and verify `integrity_check`, `foreign_key_check`, migration version, and debit/credit equality.

### Phase 5 — Integration, Auth & Security

1. **Auth:** Argon2id (`pwdlib`, OWASP params); stateful HttpOnly/Secure/SameSite session cookies (Authlib) with silent refresh in `openapi-fetch`; 401 → snapshot unsaved drafts → redirect `/login` via TanStack Router. TOTP MFA (RFC 6238, `pyotp` + `qrcode`); 10 single-use recovery codes shown once, stored as Argon2id hashes.
2. **Authorization:** role scopes via FastAPI `Depends()` — `owner` (full), `bookkeeper` (entries/imports/reconcile; no period unlocks/account deletes), `auditor` (read-only, all mutations 403), `ingest_api` (API key, draft-posting/receipt-upload only). **Sudo step-up** (password/TOTP, 5-minute elevated token) for: reopening closed fiscal periods; voiding/un-reconciling completed reconciliation sessions; unencrypted DB/ledger exports; managing Open Banking credentials/API keys.
3. **Contract & errors:** OpenAPI 3.1 → generated `schema.d.ts` (`openapi-typescript`/`openapi-fetch`); money serialized as fixed-scale strings; dates ISO 8601; timestamps UTC `Z`; IDs UUIDv7 strings. Errors as **RFC 9457 Problem Details** (`application/problem+json`) with deterministic codes (`UnbalancedJournalEntryError`, `ClosedFiscalPeriodError`, `DuplicateBankImportError`…) mapped to specific form rows/toasts.
4. **Idempotency & OCC:** `Idempotency-Key` header (client UUID per POST/PATCH) + FastAPI middleware backed by `idempotency_keys` caching responses 24 h; `version_id`/ETag optimistic locking → 409 on conflict with UI diff/refresh prompt (never silent overwrite).
5. **Encryption & config:** field-level AES-256-GCM/Fernet (`cryptography`, `MultiFernet` key rotation) for banking tokens, webhook secrets, LLM/OCR keys, full IBANs/routing/tax IDs; `APP_ENCRYPTION_KEY` from env/Windows Credential Manager only. `pydantic-settings` validates all config at startup; refuse boot on missing/default/weak production secrets.
6. **External APIs & webhooks:** `httpx.AsyncClient` + `tenacity` (timeouts, backoff+jitter, `Retry-After`) for GoCardless/Plaid/SimpleFIN/Frankfurter/vision endpoints. Webhook HMAC-SHA256/JWS verification via `hmac.compare_digest`; reject timestamps older than 5 minutes; dedupe `event_id` before queuing. OCR local by default; external Vision LLM only via explicit opt-in, metadata-stripped.
7. **Uploads:** magic-byte validation (`python-magic`) — never trust browser Content-Type; receipts `.pdf .png .jpg .webp` ≤ 10 MB, statements `.csv .ofx .qfx .mt940 .xlsx` ≤ 25 MB; strip EXIF GPS via Pillow; sanitize CSV cells starting `= + - @` (formula injection); store outside web root renamed by SHA-256; serve via authenticated streaming endpoint (or short-lived signed URLs) with `X-Content-Type-Options: nosniff` + `Content-Security-Policy: sandbox`.
8. **Transport:** CORS restricted to `FRONTEND_ORIGIN` with credentials, explicit methods/headers (no `*` in production); CSRF double-submit `X-CSRF-Token` on all state-changing verbs; HSTS, CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`; rate limits (`slowapi`/token bucket) on `/api/v1/auth/login` (5/min + exponential lockout), `/auth/totp`, `/imports/upload`, `/ocr/extract`.
9. **Audit & logs:** `security_audit_logs` for `LOGIN_SUCCESS/LOGIN_FAILED/MFA_CHALLENGE_FAILED/SUDO_ELEVATION/PERIOD_UNLOCKED/BACKUP_EXPORTED/API_KEY_CREATED` (UTC, actor, IP, User-Agent). `structlog` pipeline **must** scrub `password, token, authorization, cookie, secret, iban, account_number` from logs/tracebacks.
10. **Windows runtime verification:** least-privilege native processes; SQLite + receipts under app-data dir with restrictive ACLs, never shared over SMB; loopback default, explicit Firewall + Tailscale docs; security tests (pytest + Playwright + Bandit + `pip-audit` + `npm audit`): 401/403 for unauth/auditor mutations, idempotent retries don't duplicate, stale `version_id` → 409, locked periods reject writes, backups restorable.

### Phase 6 — Deployment & DevOps (GitHub Web workflow, Windows-native)

- **Monorepo:** `/backend` (FastAPI/SQLAlchemy/Alembic), `/frontend` (React/TS/Vite/TanStack), `/scripts` (PowerShell + `.bat` setup/launch/migrate/backup/restore/health-check), `/.github/workflows`. **No** `/deploy` Dockerfiles, no `docker-compose.yml`, no `.devcontainer`.
- **Hygiene:** `.gitattributes` (consistent EOL), `.gitignore` (`.env`, `*.sqlite*`, `*.db`, `*-wal`, `*-shm`, backups, keys, uploads, venvs, `node_modules`, build output). Keep `uv.lock` + `pnpm-lock.yaml` in sync with `pyproject.toml`/`package.json`; CI detects stale lockfiles (fail clearly or open a dependency-sync PR; no unreviewed bot rewrites of source).
- **OpenAPI workflow:** `pnpm openapi-ts` script; CI boots FastAPI with temp SQLite, fetches `openapi.json`, generates `schema.d.ts`, runs `tsc --noEmit`, then builds. Documented GitHub Actions steps for generating Alembic migrations; review + tests required before schema changes touch user data.
- **Dev env:** Python 3.12 + `uv`, Node.js 22 + `pnpm`, documented versions; `setup_windows.ps1` (venv, backend/frontend deps, app-data dirs, SQLite validation, Alembic). `start_vira.bat/.ps1`, `stop_vira.bat/.ps1` (backend + built SPA via FastAPI, or Vite in dev; clear logs, surfaced failures). Optional Task Scheduler for startup/login launch and backups. Default DB `%LOCALAPPDATA%\VIRA\data\vira.sqlite3`.
- **Builds:** backend via `uv sync` into local venv (document Windows prerequisites for WeasyPrint/OCR/file-inspection; if a dep is Windows-incompatible, pick and document a native alternative — never a Linux container). Frontend: `pnpm install --frozen-lockfile`, generate API types, `pnpm lint`, `pnpm typecheck`, `pnpm build`. Serve compiled assets through FastAPI or a native static server; same origin preferred, document CORS/CSRF otherwise. Build `vira-updater.exe` and compile the Inno Setup installer (Phase 8) in CI; installed app runs self-contained (no separate Python/Node needed). Never build/publish Docker images.
- **CI (GitHub-hosted Windows or Ubuntu, no service containers):** ruff, mypy, bandit, pip-audit → prettier, eslint, `tsc --noEmit`, npm audit → fresh temp SQLite + `alembic upgrade head` + pytest + Hypothesis → React production build + Playwright against native processes → upload reports/artifacts (never container images). Dependabot for `pip/uv`, `npm/pnpm`, `github-actions` only.
- **Secrets & release:** secrets in Windows Credential Manager / restricted env config (GH Actions secrets only for CI or a deliberate deploy workflow; never committed). Release workflow (tag-triggered on annotated `vX.Y.Z` tags, immutable SemVer): tests → frontend/backend builds → Inno Setup installer (`iscc`) → delta packages vs last 3 tags → upload setup as GitHub Actions artifact **and** Release assets (`VIRA-Setup-vX.Y.Z.exe`, delta zips, `latest.json`, `SHA256SUMS`, Persian notes) → versioned GitHub Release; deployment to the Windows machine is a reviewed explicit step (release artifact or secured self-hosted runner). **No automatic unreviewed production migrations:** backup → migrate → health + accounting-invariant checks → mark success; on failure stop service and follow tested restore procedure. Self-hosted runners: restricted permissions, protected environments, never run untrusted PR code.
- **Migration lifecycle:** `sqlite3.Connection.backup()` snapshot outside DB dir + `integrity_check` before every production migration; single migration process guarded by local lock file/named mutex; afterwards `foreign_key_check`, expected Alembic revision, debit/credit invariant check before traffic; account for table rebuilds; tested downgrade/restore path.
- **Backups & ops UI:** Task Scheduler daily online backup + receipt-storage copy, encrypted (`age`/`Restic`), optional external/S3 upload. Sudo-protected **System & Operations** area in React: app version/git commit, Alembic revision, last backup status/time/size, one-click encrypted snapshot download, restore-verification (temp restore + integrity + FK + Σ debits = Σ credits), and the Persian «بررسی به‌روزرسانی» (Check for updates) action + current/latest version status driven by Phase 8.
- **Health & logging:** `/api/v1/health/live` and `/api/v1/health/ready` (DB connectivity, Alembic revision, writable receipt storage, scheduler status). Log rotation + crash recovery for native processes; no secrets/PII in logs; loopback default with documented Firewall/Tailscale for private remote access.

### Phase 7 — Enhancements & Localization

1. **SQLite-native search:** no external search engine. FTS5 when compiled in, tested `LIKE` fallback; unified search over `journal_entries.payee/description/entry_number`, `transaction_splits.memo`, `accounts.code/name`; numeric tokens parsed with `Decimal` and compared to scaled integers via shared money utilities (never float); RapidFuzz over bounded candidates. Powers the filter bar and `Ctrl+K` palette.
2. **Upload pipeline (FastAPI `UploadFile` + `python-multipart`):** drag-and-drop receipts (`.pdf .png .jpg .webp`) and statements (`.csv .xlsx .ofx .qfx .mt940`); magic-byte MIME checks, size caps (10/25 MB), EXIF stripping (Pillow), SHA-256 content-addressed dedup; pluggable `StorageBackend` protocol via `STORAGE_PROVIDER=local|s3` (`pydantic-settings`): `local` → `%LOCALAPPDATA%\VIRA\receipt_storage` partitioned `ab/cd/<sha256>.ext` outside the repo with restrictive ACLs; `s3` → any S3-compatible (MinIO/R2/B2/AWS) via `boto3`, SSE + authenticated streaming/presigned delivery to `<ReceiptViewer />`.
3. **Persian-only UI, RTL, Jalali:**
   - Strictly Persian-only `fa-IR` with `react-i18next` namespace-split JSON (`/locales/fa/{common,ledger,reports,validation}.json`). **No English translations, no language switcher, no multilingual infrastructure.**
   - `<html lang="fa" dir="rtl">` permanently; Tailwind logical utilities (`ms-* me-* ps-* pe-* border-s text-start text-end`) everywhere — components, sidebars, tables, forms, dialogs, dashboards, reconciliation panes — natural Persian reading order with no per-component RTL patches. All UI text in professional Persian accounting terminology.
   - **Vazirmatn for text and all numbers** (user amendment, 2026-10-17); `tabular-nums`; **Persian numerals `۰۱۲۳۴۵۶۷۸۹` by default** everywhere (no toggle). Money, arithmetic, account codes, decimal values, IDs, negatives rendered with isolated LTR (`dir="ltr"`, `unicode-bidi: isolate`) in RTL contexts. Internal values stay machine-readable; Persian formatting at presentation layer only.
   - **Calendar policy, revised by the user on 2026-10-16:** Jalali (Solar Hijri) is the default (`date-fns-jalali` + fa-IR), with a persistent **Settings → Date & calendar → Jalali / Gregorian** selector. This supersedes the former ban on Gregorian selection; the UI remains Persian-only and RTL. Order and new-journal-entry forms must accept the selected calendar, not merely show a Jalali hint under Gregorian input; related lists/filters and shared date formatters must agree. Derive today and display timestamp instants in **`Asia/Tehran`**, independent of browser/server timezone. Store date-only values canonically as Gregorian ISO `YYYY-MM-DD` without timezone day shifts, and actual instants as UTC timestamps; convert at the edges without rewriting existing records. Backend/PDF formatting must follow the selected calendar where applicable (`jdatetime` + Babel for Jalali). Iranian fiscal years still begin **1 Farvardin**, regardless of display preference; test leap years and Tehran-midnight boundaries.
   - **Currency:** centralized `<Money />` with `decimal.js`; support `IRR` (Rial) and `IRT` (Toman) with explicit rule **1 Toman = 10 Rials**, never implicit or double conversion. Document canonical stored unit (Rial vs Toman) and keep calculations/entries/balances/reconciliation/taxes/reports consistent. UI defaults to **Toman (تومان)**; Persian numerals, separators, negative formatting, clear labels. Exact decimal precision end-to-end; no floating point.
4. *(Section 4 of Phase 7 is missing from the source document — see §5 Known gaps. Carry over any requirement the user supplies later.)*
5. **Privacy-first analytics (Umami):** inject tracker only when `VITE_UMAMI_WEBSITE_ID` + `VITE_UMAMI_SCRIPT_URL` are set; typed `useAnalytics()` bound to TanStack Router navigation + key workflows (`journal_entry_created`, `bank_statement_imported`, `reconciliation_completed`, `report_viewed`); client-side sanitizer around `window.umami.track()` strips query params, masks route UUIDs, and **forbids** transmitting monetary figures, account names, payee descriptions, or receipt filenames.

---


### Phase 8 — Installer, Versioned Releases & In-App Delta Updates
*(User amendment 2026-10-14; completes the "8 phases" the source intro promised.)*

- **Inno Setup 6 installer** (`VIRA-Setup-vX.Y.Z.exe`, built with `iscc` in CI): wizard **must** show an explicit «مسیر نصب» / "select where to install" step (`DisableDirPage=no`, default `{autopf}\VIRA`, chosen dir recorded in registry `HKLM/HKCU\SOFTWARE\VIRA\InstallDir`); bundles FastAPI backend (PyInstaller one-folder or embedded CPython) + built SPA + scripts + `vira-updater.exe` + `version.json` + `install_manifest.json` (per-file SHA-256 baseline); standard tasks (shortcuts, launch-at-login, Task Scheduler backup job); uninstaller never deletes `%LOCALAPPDATA%\VIRA` user data (opt-in data wipe only). Published **both** as a GitHub Actions artifact and as a GitHub Release asset.
- **Versioning & tags:** strict SemVer `MAJOR.MINOR.PATCH` from a single source of truth stamped into `version.json`/installer/OpenAPI/UI; **every version gets an annotated git tag `vX.Y.Z` (immutable — never moved/reused)** → tag-triggered release workflow (tests → build → installer → deltas vs last K=3 tags → publish). Release = setup + delta zips + `latest.json` + `SHA256SUMS` + Persian `notes_fa`; maintain `CHANGELOG.md`.
- **Update channel `latest.json`:** `{schema_version, version, pub_date, min_app_version, notes_fa/en, full_installer{url,sha256,size}, deltas[{from_version,url,sha256,size}], files_manifest_sha256}`; client reads GitHub `GET /repos/<owner>/<repo>/releases/latest` + asset; ETag caching, graceful 403/429 handling, optional `APP_UPDATE_URL` mirror; no GitHub tokens in the app.
- **In-app UX:** Persian-only «بررسی به‌روزرسانی» button in sudo-protected System & Operations (`owner`, step-up auth) + non-blocking startup badge (never auto-install); dialog conveying exactly *"A new update available, do you want to download and install?"* — «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟» with «دانلود و نصب»/«بعداً»/«مشاهدهٔ جزئیات»; download progress + verification + restart-to-finish; Persian failure message («خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.»); strings in `/locales/fa/`.
- **Delta engine (no full re-download):** per-file SHA-256 manifests; per-base delta zips for last 3 releases (`VIRA-vX.Y.Z-delta-from-vA.B.C.zip`) = `update.json` + `files/` (small changed files) + `patches/` (bsdiff for binaries >256 KB) + `delete.json` + member hashes; matching delta → download only it (assert bytes ≈ delta size); too old → full-installer fallback (`/SILENT` into recorded `InstallDir`); chained hops verified per hop. Alternatives (zsync/MSIX) allowed only if Windows-native, non-container, no-full-download, no-data-loss; manifest+bsdiff is the reference design.
- **`vira-updater.exe` transactional helper:** main app stages verified package in `%LOCALAPPDATA%\VIRA\updates\<version>\`, stops FastAPI/scheduler, spawns helper (named mutex + lock file; UAC only if `{app}` needs it). Apply = snapshot changed files to `{app}\rollback\prev\` → copy/bspatch/delete → rewrite `install_manifest.json`+`version.json` → relaunch; **any failure** → restore snapshot + manifests + relaunch previous version + Persian error/log path; keep rollback until healthy (`/api/v1/health/ready` + invariants). Post-update: standard migration lifecycle (online backup → `alembic upgrade head` → `integrity_check`/`foreign_key_check` → Σ debits = Σ credits).
- **No data loss (non-negotiable):** SQLite DB/WAL/SHM, receipts, keys, config, logs, backups live in `%LOCALAPPDATA%\VIRA\` (outside `{app}`); pre-update online backup `backups/pre-update-<version>.sqlite3`; tested restore path; a failed update always returns a working previous version with all data intact.
- **Update security:** TLS + SHA-256 verification of every package **before** staging/writing; recommended Ed25519/minisign signature over `latest.json` with baked-in public key; refuse unknown `schema_version`; rate-limit-aware GitHub API; never execute unverified package content.
- **CI verification:** Windows job runs `/VERYSILENT /DIR=<temp>` smoke install, real delta upgrade from previous version (bytes ≈ delta size), DB-checksum data preservation, forced-failure rollback; installer is uploaded as workflow artifact + Release asset ("downloadable from GitHub artifacts").
- **Acceptance:** setup downloadable from GitHub with visible "select where to install" step; every release tagged `vX.Y.Z`; in-app check fetches from GitHub, announces the required message, installs only changed parts; zero data loss always.

## 5. Known Gaps in the Source Document

1. The source intro promised **8 phases** while the original file defined only 1–7. **Resolved 2026-10-14:** the user supplied the missing **Phase 8** (Inno Setup installer, release tags, in-app delta updates) and it is compiled in §4 above (also written into `VIRA_SQLite_No_Docker.md`).
2. Phase 7 still jumps from **§3 to §5** (§4 is missing in the source document). Ask the user for Phase 7 §4 content if the gap matters; carry over any supplied requirement then.

---

## 6. Consolidated Technology Matrix

| Layer | Choices |
|-------|---------|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (`Mapped`/`mapped_column`, `aiosqlite`), Alembic, decimal.Decimal (ROUND_HALF_EVEN), py-moneyed, Babel, jdatetime |
| Frontend | React 19, TypeScript 5+ strict, Vite, TanStack Router/Query v5/Table v8/Virtual, Zustand, React Hook Form + Zod, decimal.js, Tailwind CSS + shadcn/ui (Radix), Vazirmatn (text and all numbers), react-i18next (fa only), date-fns-jalali, cmdk, react-hotkeys-hook, ECharts/Recharts, Plotly, react-pdf, react-zoom-pan-pinch, PapaParse, react-dropzone, openapi-typescript + openapi-fetch, Umami (optional) |
| Database | SQLite 3.45+ only (WAL, STRICT tables, scaled INTEGER money ×10⁴, FX ×10⁸, UUIDv7 TEXT IDs, FTS5 optional) |
| Data/Finance | Polars or Pandas + openpyxl, ofxtools, mt940, camt, RapidFuzz, scikit-learn (light classifier), optional beancount |
| Docs/PDF | Jinja2 (PDF templates only), WeasyPrint; Word + PDF proforma export |
| OCR/Files | PaddleOCR or pytesseract, Pillow, python-magic, Instructor + LiteLLM (optional), SHA-256 content-addressed storage (local or S3 via boto3) |
| Jobs/FX | APScheduler or Huey; httpx + tenacity; Frankfurter.app FX; GoCardless/Plaid/SimpleFIN (optional bank feeds) |
| Auth/Security | pwdlib (Argon2id), Authlib / FastAPI-Users, pyotp + qrcode, cryptography (Fernet/AES-GCM MultiFernet), structlog, slowapi, pydantic-settings |
| Testing | pytest, pytest-asyncio, httpx.AsyncClient, Hypothesis, Vitest, React Testing Library, Playwright, Bandit, pip-audit, npm audit, ruff, mypy, prettier, eslint |
| Ops (no Docker) | Windows-native processes/scripts (`start_vira.bat/.ps1`, `stop_vira.bat/.ps1`, `setup_windows.ps1`), Windows Task Scheduler, optional service wrapper + Tailscale, `sqlite3.Connection.backup()`, age/Restic encryption, GitHub Actions (Windows/Ubuntu runners, no service containers), Dependabot (pip/uv, npm/pnpm, github-actions), uv + pnpm lockfiles, **Inno Setup 6 installer** (user-selectable install dir) + **`vira-updater.exe`** delta updater (manifest + bsdiff), SemVer git tags `vX.Y.Z` → GitHub Releases (`latest.json` channel) |

---

## 7. Financial Integrity Rules (quick reference)

1. **Never `float`/JS `number` for money** — Python `Decimal` + `decimal.js`, exact strings over JSON (`"1250.5000"`).
2. **Scaled integers in SQLite** — amount × 10,000; FX rate × 100,000,000; central `TypeDecorator`; bounds + quantize before writes; 64-bit overflow guards.
3. **Double-entry invariants** — ≥ 2 splits; Σ debits = Σ credits per currency/currency-rate path; validated in Pydantic **and** atomically in the ledger service before `POSTED`.
4. **Rounding** — `ROUND_HALF_EVEN` (banker's) at the application layer; documented rounding policy for FX; persist exact scaled results.
5. **Immutability** — posted/reconciled data is append-only; corrections via reversing entries (`reversed_entry_id`); audit trail immutable and redacted.
6. **Currency** — every amount paired with ISO 4217 code (py-moneyed); no cross-currency math without explicit rate; IRR/IRT rule 1 Toman = 10 Rials applied exactly once; UI default Toman.
7. **Idempotency & concurrency** — `Idempotency-Key` + response cache; `version_id` optimistic locking (409); short `BEGIN IMMEDIATE` writes; bounded locked-retries.

---

## 8. Definition of Done (per phase)

- All mandated libraries/constraints of the phase implemented; §2 constraints untouched.
- Tests green (pytest/Hypothesis and/or Vitest/Playwright as applicable); lint/type checks pass (ruff, mypy, tsc).
- No `float` money, no Docker artifacts, no secrets/DB files committed.
- Docs updated (`project brief.md`, README, scripts usage); user-facing text in Persian where UI exists.
- Any release-related deliverable follows Phase 8: tagged `vX.Y.Z`, Inno installer (selectable dir) as GitHub artifact + Release asset, delta-safe updates, zero data loss.
- **Stop and wait for the user's "proceed" before the next phase.**

---

## Annex A — `قیمت نهایی.xlsx` Extracted Relations (preliminary)

Source: `قیمت نهایی.xlsx`, single `Sheet1`, cells A1:F35. This is the basis for the **Sales Price Calculations page** (Phase 1 → Production). Repair phase 4 user decision: preserve the authored formulas literally, including their dimensional quirks; do not silently normalize them. All amounts in **Toman**.

### A.1 Constants («ثابتها»)

| Cell | Name (fa) | Meaning | Value | Unit |
|------|-----------|---------|-------|------|
| B2 | توان مصرفی پرینتر | Printer power draw | 1.3 | kW |
| B3 | قیمت هر گرم فیلامنت | Filament price per gram | 3000 | Toman |
| B4 | قیمت هر کیلو وات برق | Electricity price per kWh | 1400 | Toman |
| B5 | اسطحلاک (=استهلاک) پرینتر در هر ساعت | Printer depreciation per hour | 10000 | Toman/h |
| B6 | ضریب سود | Profit coefficient (used as **multiplier**, despite «درصد» label) | 2.5 | × |
| B7 | کمیسیون دیجی‌کالا | Digikala marketplace commission | 13.1 | % |
| B8 | نایلون بسته بندی | Packaging nylon | 2000 | Toman |
| B9 | حلقه و زنجیر | Ring & chain (chain variant) | 8000 | Toman |
| B10 | هزینه ارسال محموله | Shipment cost (per order/shipment) | 150000 | Toman |

*(B8 and B2 are defined but unused. Repair phase 4: the user selected literal spreadsheet parity; leave both unused.)*

### A.2 Product specs («مشخصات محصول»)

| Cell | Name | Value | Unit |
|------|------|-------|------|
| B13 | وزن محصول — product weight | 240 | g |
| B14 | زمان پرینت محصول — print time | 10 | h |
| B15 | تعداد — quantity | 1 | pcs |
| B23 | هزینه لیبل — label cost (input) | 8000 | Toman |

### A.3 Cost formulas («هزینه ها»)

| Cell | Name | Formula | Meaning |
|------|------|---------|---------|
| B18 | قیمت فیلامنت مصرفی | `=B13*B3` | filament cost = weight × price/g |
| B19 | هزینه برق مصرفی | `=B4*B14` | electricity = price/kWh × hours *(as authored; see A.1 note on B2)* |
| B20 | هزینه اسطحلاک پرینت محصول | `=B5*B14` | depreciation = per-hour × hours |
| B21 | هزینه بسته بندی و ارسال | `=B10` | packaging + shipping (whole shipment) |
| B22 | هزینه بسته بندی و ارسال هر عدد | `=B21/B15` | per-unit shipping = shipment / qty |
| B24 | جمع هزینه های ارسال یک عدد | `=B23+B22` | per-unit delivery bundle = label + per-unit shipping |
| B25 | جمع هزینه های تولید | `=SUM(B18:B20)` | production cost = filament + electricity + depreciation |
| E25 | جمع هزینه های تولید — زنجیر دار (chain variant) | `=B25+(B15*B9)` | production cost + chain per unit × qty |

### A.4 Price & marketplace (Digikala) formulas

| Cell | Name | Formula | Meaning |
|------|------|---------|---------|
| B28 | قیمت فروش کل | `=B25*B6` | total sale price = production cost × profit multiplier |
| B28/E28 | قیمت فروش کل — زنجیر دار | `=E25*B6` | chain variant × multiplier |
| B29 | قیمت فروش هر عدد محصول | `=B28/B15` | unit sale price |
| E29 | … زنجیر دار | `=E28/B15` | unit sale price (chain) |
| B31 | کمیسیون دیجی‌کالا برای هر عدد | `=(B29*13.1/100)` | unit commission *(hardcodes 13.1 instead of B7; based on B29)* |
| B32 | قیمت کل با هزینه ارسال دیجی‌کالا | `=B28+B24` | *(as authored: total price + per-unit delivery — dimensional quirk)* |
| B33 | قیمت هر عدد با کمیسیون دیجی‌کالا | `=B29+B31` | unit price + commission |
| E33 | … زنجیر دار | `=E29+B31` | *(quirk: adds commission derived from non-chain B29)* |
| B34 | قیمت هر عدد با لیبل دیجی کالا | `=B33+B23` | + label cost |
| E34 | … زنجیر دار | `=E33+B23` | + label cost |
| B35 | **قیمت نهایی** (با هزینه لیبل و کمیسیون و ارسال) دیجی کالا | `=B34+B24+(B34*(10/100))` | final unit price = unit+commission+label + per-unit delivery + 10% buffer on B34 |
| E35 | … زنجیر دار | `=E34+B24+(B34*(10/100))` | final unit price (chain), reusing the plain B34 buffer |

### A.5 Authored quirks — preserve literally (repair phase 4 user decision)

1. **B6** labeled «درصد» (percent) but used as a ×2.5 multiplier (i.e., 250% of cost). Use it as a multiplier, exactly as the formula does.
2. **B31** hardcodes `13.1` instead of referencing **B7**; and chain-variant commission (E33) reuses B31 (computed from non-chain B29) instead of `E29*B7/100`. Preserve the literal 13.1% and shared B31. B7 is display-only.
3. **B32** mixes total (B28) with per-unit (B24) — dimensional inconsistency.
4. **B2** (printer power kW) and **B8** (packaging nylon) are defined but unused by formulas — do not wire them into the calculation.
5. **B35** adds B24 again plus a 10% contingency on B34; the 10% is a literal constant. **E35 also references plain B34**, not E34, for its buffer; preserve this shared value.
6. Currency is implicitly **Toman** everywhere; the page must follow §Phase-7 currency rules (Persian numerals, Toman default, LTR-isolated figures).
7. B25 is **not** multiplied by B15. E25 adds only `B15*B9`. Both B29 and E29 then divide by B15. Preserve this even when quantity exceeds one.
8. Reference sample (B13=240, B14=10, B15=1): **B35=2760748.5, E35=2780748.5 Toman**. The previously reported E35=2785630.5 was the app's normalized result, not the XLSX value.
9. Reproducible reference: `scripts/extract_pricing_reference.py --check` validates the fixture against the original workbook formulas, cached values and SHA-256. The frontend tests compare all formula cells for seven scenarios, independently of app pricing logic. Changes affect new calculations only; never rewrite saved order/production price snapshots.


---

*Compiled from `VIRA_SQLite_No_Docker.md` and `قیمت نهایی.xlsx` (Sheet1, A1:F35), plus user amendments. **Status:** Phase 8 complete 2026-10-14 — Installer, Versioned Releases & In-App Delta Updates: Inno Setup 6 installer with the mandatory «مسیر نصب» directory-selection step (InstallDir recorded in the registry), strict vX.Y.Z annotated tags + CHANGELOG.md, schema-versioned latest.json (unknown versions refused) with full_installer + K=3 deltas, ETag-cached GitHub update checks with APP_UPDATE_URL override and Ed25519 signatures, delta engine (per-file SHA-256 manifests, manifest diffing, update.json + files/ + BSDIFF40 patches/ + delete.json, delta → chain → full-installer selection — never a full re-download when a delta applies), transactional vira-updater.exe (mutex, snapshot, verified apply, rollback with «خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.»), mandated update dialog «به‌روزرسانی جدید موجود است» / «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟» + startup badge, zero data loss (pre-update backup + rollback until health checks), CI artifact + Release asset distribution with Windows install/upgrade/rollback smoke tests. 186 pytest + 70 Vitest green, ruff + mypy clean, tsc + eslint clean, build green, Bandit 0 medium+, pip-audit clean. **The 8-phase plan is fully delivered.***

## User-requested follow-up — repair subphase 4-B (2026-10-16; in progress)

Track the next-update scope in
[`docs/plans/pricing-dates-catalog-theme-follow-up-fa.md`](docs/plans/pricing-dates-catalog-theme-follow-up-fa.md):

- Remove spreadsheet cell-reference columns and formula annotations from the pricing UI, preserving literal formulas, amounts and the three row highlights.
- Implement the revised calendar policy above, including persistent calendar selection and Tehran-based today.
- Add Settings → Item master data for adding/removing item types, units and suppliers; the New item form must consume persisted options. Reuse existing suppliers; protect references/history by deactivating used options rather than deleting their records. Dynamic types/units require real schema/API support, not just new labels over fixed enums; preserve stock/production semantics and explicit unit compatibility.
- Give the light theme a very subtle cream or pale-green background through shared theme tokens, retaining accessible contrast, semantic highlights and the existing dark theme.

Execution was authorized after v1.0.10. Substep 4-B/1 implements pricing presentation
and light-theme changes. Substep 4-B/2 adds genuine civil-date inputs, Tehran
presentation and an installation-wide calendar preference stored as versioned,
append-only SQLite security events (no DDL/revision change; backups include it).
Only OWNER/BOOKKEEPER can change it, with CSRF and revision compare-and-swap;
authenticated AUDITOR can read it. No browser-only preference or data rewrite.
Item master-data implementation is now locally tested; its final Windows migration/rollback gate passed as recorded in the catalog report below.
The user deferred installed-data/manual acceptance until the phases finish, not
automated tests. This is not authorization to publish another version. Preserve
immutable releases, migration backups and delta-only routine updates. The detailed
plan defines acceptance tests and per-step reporting.


### 4-B/3-A safety checkpoint — preceding catalog implementation

Before dynamic type/unit DDL, the updater must restore the exact attempt's verified
SQLite snapshot after a failed schema migration, not just old app files. The new
standalone stdlib DB tool is shipped/hash-verified in the delta, snapshots after
writers stop, preserves failed DB/WAL state, avoids rewriting unchanged DBs and
validates restored schema/data plus old-app readiness. Active-update writes and
recurring jobs are blocked in current code until the helper commits.

See [`docs/reports/phase4b-3a-schema-rollback-fa.md`](docs/reports/phase4b-3a-schema-rollback-fa.md)
for the public-1.0.10 / compiled-helper / real probe-revision rollback gate and its
actual test status. The probe revision exists only in disposable CI payloads.
It does not close the final catalog-migration gate: rerun with the actual reference
models/DDL before shipping that migration. Types, units and supplier Settings UI
were not delivered by this earlier safety checkpoint. No new public release is authorized.


### 4-B/3-B — persisted item catalog (2026-10-17, unpublished)

Settings and New item now share persisted type/unit reference tables and the
existing supplier registry. The preserving `0006_item_catalog` migration rebuilds
only the physical inventory table inside an explicit SQLite IMMEDIATE transaction,
checks the copied rows in both directions and verifies foreign keys/integrity
before committing schema, data and revision together. The runtime DB still enforces
foreign keys. No historical ledger, stock movement, price or quantity is rewritten.
Used/default choices deactivate; unused custom choices can be physically deleted;
reactivation and revision conflicts are supported. New types are general stock,
not implicitly filament/produced goods; only canonical FILAMENT/G and PRODUCT/PCS
participate in existing production, with no automatic unit conversion.

See [`docs/reports/phase4b-3b-item-catalog-fa.md`](docs/reports/phase4b-3b-item-catalog-fa.md)
for actual local and Windows gate evidence/status. The public-1.0.10 gate now seeds
with the untouched public migrator/ORM and applies the actual final catalog DDL,
not a synthetic probe. Installed-business/Windows visual acceptance remains deferred;
no new tag, release, installer or authorization to publish is implied.


Final 4-B/3-B evidence: **357 backend / 196 frontend tests**, five real-browser
scenarios, and **all five CI jobs successful** on `fb82b2c` (run **38992081789**),
including actual catalog DDL from immutable public 1.0.10 and compiled-helper
schema/data rollback. Inventory indexes/triggers are preserved alongside rows.
This completes the automated implementation gate, not installed-business/native
visual acceptance, a release/version bump or authorization to publish.


### Native PDF proof follow-up (unpublished, 2026-10-17)

See [`docs/reports/native-pdf-font-proof-fa.md`](docs/reports/native-pdf-font-proof-fa.md).
Strict native Windows PDF/API/font verification **passed**, with all five CI jobs
successful on `e5e3364` (run **38996175479**): one/four A4 pages, actual embedded
Vazirmatn Regular/Bold, all 30 used Latin/Persian/Arabic digits in both weights.
Local regression: **368 backend / 196 frontend / six real-browser tests passed**.
Self-contained browser fallback fonts work under document-only restrictive CSP;
the PDF fetcher reads only the two bundled TTFs using the locked WeasyPrint 70 API.
The pinned upstream native fixture is CI-only, NOT included in installer/delta
payloads. Runtime closure, third-party license/source compliance,
installed-bundled-Python proof and human RTL/print/business acceptance remain open.
No release, new version, publication authorization or installed-PDF acceptance.


### Private staged-CPython PDF/runtime audit (unpublished, 2026-10-17)

[Report](docs/reports/pdf-runtime-payload-audit-fa.md) and
[deterministic native inventory](docs/dependencies/pdf-runtime-win64-inventory.json).
All five CI jobs passed on `d848a08` (run **39038459962**); **387 backend / 196 frontend /
six CI browser scenarios**. A private copy produced by the actual payload stager,
relocated to a spaced/Persian path, renders the same one/four-page PDFs with
bundled **CPython 3.11.17**, `-I`, production-only dependencies and **27 audited DLLs**.
The audit excludes 51 unrelated SDK DLLs; all 27 selected libraries actually load
from the private candidate. Original staged-file hashes remain intact except caches.

Do NOT infer production/runtime distribution readiness. The private proof exposed
and addressed libffi load-order collision and Fontconfig's lossy Unicode config
path using an explicit ASCII temporary config. General bootstrap/path handling,
per-library exact source/build provenance and notices/corresponding source remain
open; all 27 libraries are UNREVIEWED and the candidate says DO_NOT_DISTRIBUTE.
No automatic native runtime was added to normal staging/startup, no native binary
is committed/uploaded, no public version/tag/release or installed-user acceptance.
Next: establish a source-verifiable licensed runtime (build pinned sources if
upstream provenance cannot be established), then normal startup/delta/rollback proof.


### Source-verifiable native runtime proof (unpublished, 2026-10-17)

[Persian report](docs/reports/pdf-runtime-source-build-fa.md),
[full source inventory and copyright texts](docs/dependencies/pdf-runtime-win64-source-inventory.json),
and [verified source/PDF evidence](docs/dependencies/pdf-runtime-win64-source-proof.json).
The NEW source-built candidate has **21 DLLs / 14,417,408 bytes**, all actually
loaded from its private relocated staged-CPython payload. The old 27 SDK DLLs
remain UNREVIEWED; this is not a relabeling or approval of them.

Native run **39048889428 / 2ec79b8** passed: 35 target/host packages compiled with
native binary caches disabled at vcpkg **a5f736224e85b32e25a8ffc52562333180396642**.
Complete patched target source materials cover **20 packages / 25,505 entries /
21 safe internal symlinks**, with receipts, exact owners, SPDX, original copyright
bytes, full recipes/patches and actual build wrappers. Target DLLs use a static
CRT; build-only host tools use a separate dynamic-CRT/release triplet after a real
gettext host-tool crash exposed the invalid unified static-CRT configuration.

Independent artifact audit **39052300861 / b6c5475** verified the source ZIP hash,
all target source trees/notices/SPDX/owners and original PDFs without recompiling.
GitHub truncates notices at ten per step: all 47 inventory chunks were recovered
across six steps, not mistaken for complete evidence when only three were visible.
Source ZIP: **188,615,875 bytes**, SHA256
`259532d2cd8c5d3b176402acdcfb9daadb2cb897d5710010cc198eeabe5401de`.
Large sources remain temporary CI artifacts (14 days), not committed or a durable
corresponding-source delivery arrangement for a future public binary release.

Actual **CPython 3.11.17**, `-I`, production-only dependencies, int/double callbacks,
one/four-page A4 PDFs and embedded Vazirmatn 400/700 with all 30 digits pass. The
two PDF hashes match the previous private proof exactly; this does NOT claim
bit-for-bit reproducibility of native libraries or all future documents.
Regression: **413 backend / 196 frontend / six CI browser scenarios**, Ruff/Mypy/
Bandit. All five ordinary CI jobs on `b6c5475` (39052300805) passed.

Still **BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW** /
DO_NOT_DISTRIBUTE. Explicit license choices, notices, recipe/compiler/CRT rights,
durable source delivery, general Unicode Fontconfig/bootstrap, normal native
manifest/delta/rollback, minimum-OS validation and installed-user acceptance remain
open. libiconv's port has no declared license field; its source and full copyright
are preserved, NOT silently approved. The private proof still uses an ASCII
external temporary Fontconfig config. No native runtime was connected to normal
startup/staging; no native binary upload, release/tag/version bump or user-data/
pricing change. Continue with license choices and production bootstrap only after
this technical source-materials checkpoint; publication still needs approval.


### Native PDF license materials checkpoint (unpublished, 2026-10-18)

[Persian report](docs/reports/pdf-runtime-license-materials-fa.md),
[explicit proposed selections](docs/dependencies/pdf-runtime-license-policy.json),
[generated notices](docs/dependencies/pdf-runtime-THIRD-PARTY-NOTICES.txt), and
[source-delivery contract](docs/dependencies/pdf-runtime-source-delivery-plan-fa.md).
All **20 packages / 21 DLLs** are covered. The original source ZIP was reverified
without recompilation; **11 supplemental source files / all 19 metadata chunks**
were recovered. PCRE2's 97-byte COPYING was only a forwarding stub: actual
LICENCE.md (BSD-3-Clause WITH PCRE2-exception) and the separate BSD-2-Clause SLJIT
license are now preserved. The SLJIT source is the vcpkg-pinned commit, NOT merely
the PCRE2 tag's submodule. FTL is proposed for FreeType with attribution and nine
contributed-driver/hash/zlib/HarfBuzz notices. libiconv's absent port declaration
is not filled with an invented SPDX approval; the original LGPL-library/GPL-CLI
scope is explicitly distinguished. Every other original AND/OR scope is retained.

A real first Windows CI failure exposed legacy-locale corruption of UTF-8
copyright bytes. Explicit UTF-8 JSON reads and LF writes fix it without relaxing
hash verification; a regression enforces the contract. **438 backend tests / 33
focused tests**, Ruff, Mypy (84 app files) and the configured Bandit gates pass.
License-source audit **39102792100 / 40addf7** passes. All five ordinary CI jobs
**39102792071 / 40addf7** pass, including native Windows, the real PDF/private
worker and public 1.0.10 schema/compiled-helper rollback; **196 frontend / six
browser scenarios**. The linked report preserves the initial failure too.

The retained private source/review artifact now lasts **90 days**, expiring
**2027-01-16 UTC**; this is STILL NOT durable recipient source delivery. No release
or native-binary publication. The existing archive captures actual wrappers but
not every transitive dependency for independently running the whole workflow;
complete/permissioned recipe sidecar is an explicit prerequisite, not an SDK claim.

Still **BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW**. Prepared choices
are not legal sign-off. Six mandatory gates remain: component legal review;
compiler/static-CRT terms; VIRA build-script rights/completeness; real recipient
source delivery; compatible LGPL replacement/EULA proof; production bootstrap,
native delta/rollback and deferred installed-user acceptance. MIT or any other
license was NOT applied to VIRA-owned code without the owner's decision. No normal
runtime integration, version/tag/release, user-data/pricing change or human
acceptance is inferred from this checkpoint.


### Owner-confirmed limited MIT grant for PDF build tooling (2026-10-18)

The owner explicitly answered yes to MIT **only for native PDF build scripts and
settings**, not the accounting app. This permission is now applied via
[the full MIT license and scope guide](LICENSES/README.md),
[exact file/version scope](docs/dependencies/pdf-build-script-license-scope.json),
and [machine-checked status](docs/dependencies/pdf-build-script-license-check.json).
Nine explicit VIRA-authored build/configuration/instruction/checker files are
covered; no wildcard, root LICENSE or automatic license for unlisted application,
staging, backend/frontend/installer or third-party sources. Seven historical
archive members match the granted reference versions. The original source ZIP
hash is unchanged. Native build/profile files were not edited merely to add
headers, so there is no need for another native compilation to establish consent.

`check_pdf_build_license.py` validates the limited grant and can create a NEW
source/license sidecar with only the listed files. It also supplies the previously
missing `pdf_runtime_inventory.py` import helper. The private license-proof
workflow attaches the grant and these source files alongside the old source ZIP;
this remains a temporary review copy, NOT recipient-ready durable source delivery
or proof that the entire application-referencing workflow is standalone.
24 new tests / 57 focused checks / 462 backend tests pass locally, plus Ruff,
Mypy (84 app files) and the configured Bandit gates. All five ordinary CI jobs
**39104212641 / 0742355** and source/limited-sidecar audit **39104212604** pass;
196 frontend / six browser scenarios, native Windows PDF/private Python and real
public-version schema/compiled-helper rollback are green. See the
[confirmation report](docs/reports/pdf-build-script-license-grant-fa.md) and
[pinned proof](docs/dependencies/pdf-build-script-license-proof.json).
The permissions substep is confirmed; recipe completeness and every other native
runtime gate remain open. BLOCKED is project release-readiness, not an extra MIT
restriction. No application-wide MIT grant, native-runtime integration, binary
publication/version/tag/release, user-data/pricing change or human acceptance.

### Independent native-only PDF recipe and compiler/CRT evidence (2026-10-18)

The next authorized preparation step adds `rebuild_pdf_native.ps1` and its native
inspector as explicit MIT build-tool derivatives (11 files now, not an app-wide
license). The [native-only guide](docs/dependencies/pdf-native-rebuild-guide.md)
uses a NEW absolute work directory, pinned vcpkg and disabled binary caches; no
application checkout, Node/uv/app Python/staging/database is needed to compile.
Windows x64, PowerShell 7, Git, appropriately licensed MSVC/SDK and downloads are
prerequisites, not an offline SDK. Python/pefile is an optional separate inspector.
Modified overlays are permitted; baseline hash comparison is not a legal ban on
MIT/LGPL modifications. Historical archive/grant proofs remain historical.

[Independent run and regression evidence](docs/dependencies/pdf-native-rebuild-proof-run.json)
is authoritative for the long Windows build's final status; plan/contract-test
success MUST NOT be reported as completed native compilation. The audit requires
20 reference preferred-source trees, 21 DLL owners/PE closure and actual private
loaded origins. Even a successful native audit is not app rendering with these
new DLLs, bitwise reproduction or production installation/update acceptance.

Actual original compiler records identify MSVC 19.51.36260.0, VS18/v145, tools path
14.51.36231 and SDK rc 10.0.26100.0, NOT bundled Python's MSC1944. Installed terms
and official 2026 Enterprise/Professional, Build Tools and C++ Runtime agreements
are now recorded in the [official reference review](docs/dependencies/pdf-crt-official-reference-review.json).
Full-use/trial, OSS Build Tools compilation exceptions and runtime installation
rights are distinct from conditional redistribution. Runner installation and a
REDIST filename list do not establish entitlement or static-CRT component coverage.
No remote raw-DOCX checksum is claimed from parsed text. CRT gate remains open.

[Persian report](docs/reports/pdf-native-independent-rebuild-fa.md) preserves the
ordinary Windows readiness/rollback failure and cp1252 diagnostic fix; no failing
gate may be hidden by local passes or weakened readiness/hash checks. 476 backend
tests locally, Ruff and Mypy/84 pass. Six distribution gates remain tracked; native
integration remains BLOCKED. No runtime payload, release/version/tag, accounting
values, real user data or installed-user acceptance changed.

Independent baseline result: **39108011284 / d5b2516 succeeded**. The isolated
entry point compiled; all 20 preferred-source tree hashes matched and all 21
DLLs passed owner/PE-closure/private-origin loading checks. Two complete metadata
chunks are committed in `pdf-native-independent-rebuild-evidence.json` with hash
and log-only artifact provenance in the proof. This closes the baseline technical
experiment, NOT CRT clearance, recipient assembly/delivery or runtime integration.

Final ordinary code regression **39110216955 / 867dfd3: all five jobs passed**,
including both Windows real in-app apply/rollback and public 1.0.10 schema/
compiled-helper rollback; 476 backend / 196 frontend / six browser scenarios.
71 focused checks and local app/audit Bandit pass. Initial readiness failure and
subsequent diagnostic-test/lint corrections remain recorded; successful retry
alone does not establish the initial readiness root cause. No production health,
hash or rollback condition was relaxed. Final evidence updates are documentation
only, not a new native output or release.

### Native source-kit assembly and separate CRT probe (2026-10-18)

The next authorized preparation phase adds `pdf_source_kit.py`, an explicit MIT
native-build-tool derivative (**12 listed files**, not the accounting app). It
assembles the immutable original source ZIP, licensed sidecar, guide, notices,
policy/reference evidence and a per-file SHA256/size manifest in a NEW directory.
Its standard-library-only inspector must use its OWN trusted checker, never
execute a checker from an arbitrary inspected kit, reject envelope symlinks/
external resolved paths (including junctions) and require consistency across
source/notices/policy/scope. Internal hashes do not authenticate a publisher:
use an independently trusted external digest and trusted verifier.

Actual private CI kit assembly, `python -I -S` recipient-style checking, extraction
of **21 relative symlinks** and rehashing **all 20 source trees / 25,505 entries**
are recorded in [kit proof](docs/dependencies/pdf-source-kit-proof.json). Preserve
safe relative symlinks and script modes; reject path escapes, collisions, cycles,
missing targets, special entries, oversized archives and existing destinations.
Windows symlink-permission failure must be explicit, not silently flatten links.
This is a temporary 90-day review kit, NOT anonymous durable source delivery.
The build still downloads pinned inputs: direct extracted-local-source/offline
compilation is NOT proven, and modified sources need reviewed overlays.

The [separate CRT probe](docs/dependencies/pdf-crt-static-probe-proof.json) genuinely
compiled/ran `/MT`, recorded `MT_StaticRelease`, seven searched library paths/hashes,
317 Loaded trace events (not 317 unique native components) and KERNEL32-only imports
for THAT probe. Full `/VERBOSE` was required; initial `/VERBOSE:LIB` evidence failures
are retained, not hidden or waived. Actual original/rebuilt 21-DLL object mapping
and producer entitlement remain pending. Microsoft documentation distinguishes SDK
static UCRT, compiler support, static startup and C++ library; simply switching to
`/MD` does not eliminate static startup or establish redistribution permission.

[Persian report](docs/reports/pdf-source-kit-and-crt-probe-fa.md) and the updated
[source-delivery plan](docs/dependencies/pdf-runtime-source-delivery-plan-fa.md)
preserve boundaries and regression evidence. 506 backend tests locally, 79 focused
checks, Ruff/Mypy (84 files) and configured Bandit pass. Six distribution gates
remain tracked; no source availability, CRT permission, LGPL replacement/EULA,
production bootstrap/native updates or installed-user acceptance is inferred.
No runtime payload, broad license, version/tag/release, real data or pricing change.

Final code evidence: source kit **39113483257**, scoped-source/license audit
**39113483241** and all five ordinary CI jobs **39113483256**, on **1e27683**, passed.
506 backend / 196 frontend / six browser scenarios, both Windows current apply/
rollback and public 1.0.10 schema/compiled-helper rollback are green. The separate
CRT probe **39113097728 / 0bceb1e** passed with its original evidence failures
preserved. Kit manifest digest and artifact retention are pinned in the proof;
no binary/source publication or legal clearance is implied. Final evidence-only
updates do not alter the native recipe or business application.

### Local preferred-source replay phase — 2026-10-18

The next authorized step adds a standard-library local-source adapter and explicit
port pins to the limited MIT build-tool derivatives (**14 files**, no app-wide
license). The default native driver still downloads target sources; the new
route uses its existing `-OverlayPorts` option with verified, already-patched
kit inputs. Actual catalog: 19 single-root source packages plus empty `pthread`.
Unknown/multiple roots, recipe edits, unsafe links/paths and unacknowledged source
changes fail closed. Source extraction now creates Windows nested symlink targets
with native separators; digest targets remain canonical POSIX paths.

Native driver/profile remain unchanged. Only pinned TARGET source-acquisition
blocks are replaced; host/build-tool downloads still work, so this is not an
offline compiler SDK. Preserve PCRE2's already-merged SLJIT; reject uncaptured APNG.
Full MIT/upstream notices are retained. A controlled local Pango version-string
edit must be observed through its real rebuilt DLL function, with all 20 source
trees/21 DLL owners, closure and origins audited and external inputs unchanged.
Original ZIP stays immutable; the modified reference is separate and explicitly
NOT a new corresponding-source archive or the ordinary distribution candidate.

[Report](docs/reports/pdf-local-preferred-source-replay-fa.md) and
[exact local instructions](docs/dependencies/pdf-native-rebuild-guide.md).
Current automated evidence: 536 backend tests, 84 focused checks and Ruff/Mypy/
Bandit pass. Actual native build **39146630126 / 576c0ea** and final audit PASSED:
20 source trees, 21 DLL origins/owners/closure and the executed modified version
`1.58.0-vira-local-source`, with external source inputs unchanged. All seven raw
annotation chunks are recovered and hash-pinned in the
[proof](docs/dependencies/pdf-local-source-replay-proof.json). The Windows nested
symlink issue and real gettext make failure are retained; ZIP mtime preservation
fixes unwanted Autotools regeneration. Ordinary CI **39146693875 / ca4b61e**:
all five jobs pass, including 196 frontend tests, six browser scenarios and both
Windows rollback paths. No legal clearance or installed-user acceptance is inferred. Six
source/license/CRT/LGPL/production gates remain OPEN. No version/tag/release,
installer/native payload, business calculations or installed data change.

Final guide/policy source kit **39150398698 / f4c088b** and limited-license/source
audit **39150398692** pass: 26 manifested files, 14 licensed build files, actual
20-tree rehash/21 symlinks. The native Windows build remains separately pinned;
no exact-envelope/bitwise or durable-public-delivery claim.

### Private application consumption of locally source-built PDF engine — 2026-10-18

Authorized follow-up completed: fresh native build **39153212109 / 284e827** then
real app rendering from relocated production **CPython 3.11.17**, in `VIRA چاپ بومی`.
All 20 preferred-source trees/21 DLL hashes, owners and origins audited; all 21
candidate DLLs actually loaded from the relocated private closure. The SAME render
process executed `pango_version_string()` = `1.58.0-vira-local-source`. Real single/
four-page A4 PDFs embed/use Vazirmatn 400/700 with Latin/Persian/Arabic digits; hashes
match the previous synthetic fixtures. Production manifest unchanged; dev PDF/PE
inspectors absent from production; isolation and ctypes callbacks pass.

[Report](docs/reports/pdf-local-source-app-consumer-fa.md) and
[eight-part hash-pinned proof](docs/dependencies/pdf-local-source-app-consumer-proof.json).
26 new tests; 562 backend / 61 focused, Ruff/Mypy (84 app files)/Bandit pass.
Ordinary **39153212117 / 284e827: all five jobs SUCCESS**, 196 frontend/six browser
scenarios and both existing Windows rollback paths. App-QA handoff/controller are
NOT added to the 14-file MIT native recipe scope. Modified reference retains
`source_archive=null`; no new modified corresponding-source archive or distribution
candidate. Six gates remain OPEN: private consumption is NOT installed replacement/
EULA approval, CRT rights, durable source delivery, normal Inno/native delta/rollback,
production Unicode Fontconfig/bootstrap or installed-user acceptance. No normal
payload/install/data/math, broad license, version/tag/release change.

### Complete modified-source PRIVATE review packaging — 2026-10-18

The next authorized source-delivery prerequisite packages a DIFFERENT complete
modified source ZIP, retaining the byte-identical original kit/ZIP and scoped MIT
recipe. Actual successful assembly and DOWNLOADED Windows extraction/preparation:
**39158897935 / f00ca08**. All original archive members checked, all 20 compiled
preferred trees match, 25505 entries/21 links preserved. Modified ZIP SHA256
`1d56fe9a3305f3b9bb7a741dbb697b7d5b9a80a74a1c7bb172e91895ea311921`.
The licensed derivative remains 14 explicitly listed files, not QA/app/CRT.

[Report](docs/reports/pdf-modified-source-kit-fa.md),
[proof](docs/dependencies/pdf-modified-source-kit-proof.json),
[real transport failure](docs/dependencies/pdf-modified-source-transport-failure.json).
Artifact upload initially omitted the licensed hidden .github workflow; independent
manifest-versus-downloaded-members diagnostics proved the exact missing file.
Scoped source artifacts now opt in to hidden files, without weakening hash/scope
checks. Pre-upload success is NOT post-download completeness. 35 new tests / 119
focused; 597 backend tests pass locally. Native extraction/build regression
**39158539572 / d47e2c9 SUCCESS**: 20 matching trees/21 DLL origins/real modified
Pango, with full seven-part witness pinned. Ordinary **39160309610 / 693f887**
all five jobs pass (196 frontend/six browser scenarios/both Windows rollback paths).
Preserve real 7139 startup-badge timeout; QA-only bounded diagnostic retry changed
NO waits/assertions/product behavior and does not establish the initial root cause.
Final documented modified kit **39159627961 / 7139e41**, original kit
**39159627909**, source/license **39159627993** all pass; original subkit manifest
is cross-bound to actual downloaded Windows verification.

An external prominent modification/date notice is included; the exact compiled
Pango file has NO new inline change/date notice. Legal completeness is explicitly
NOT approved; adding one changes hashes and needs a fresh build/reference. Old
adapter references stay source_archive=null (it does not bind this separate review
archive), and historical proofs retain their original preparation flags. No new
compilation FROM this envelope is claimed. Six gates OPEN; no anonymous durable
public source delivery, CRT/EULA/production clearance, release/tag/version, normal
payload/install/data/math or installed acceptance change.

### Inline modification/date notice, actual archive build and PDF — 2026-10-19

Authorized private step **SUCCESS: 39165372821 / 84c20ac**. Add prominent dated
notice INSIDE the modified Pango file; retain all upstream headers and original
ZIP. New complete archive: 188617046 bytes, SHA256
`b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2`.
Windows actually DOWNLOADS and authenticates it against producer-job output pins
separate from the artifact bytes. Compile those extracted sources, WITHOUT any
post-extraction edit or binary cache, BEFORE installing application dependencies.
All 20 real buildtrees and noticed Pango bytes match the archive inputs; 21 DLL
origins/closure/hashes match the candidate and real PDF process. Production CPython
3.11.17, isolated Persian/spaced payload, Pango 1.58.0-vira-local-source, one/four
A4 pages, embedded/used Vazirmatn 400/700/all 30 digit glyphs pass. Reverify the exact
source envelope AFTER compilation/rendering. No bitwise/offline claim.

[Persian report](docs/reports/pdf-noticed-archive-build-fa.md),
[archive/build/PDF proof](docs/dependencies/pdf-noticed-archive-build-proof.json),
with independently hashed complete new witness. Preserve historical evidence and
the packaging-time false fresh-build flag; the NEW witness binds success to that
exact source archive, not the old build. Old adapter's source_archive=null remains
scoped/truthful. Ten new tests; 607 backend, Ruff/Mypy84/Bandit/license14 pass.

Technical inline-notice and compile-FROM-this-archive gaps are now proven, NOT
legal approval, recipient-ready/toolchain review, durable anonymous source delivery,
CRT rights, EULA/installed DLL replacement, production Unicode bootstrap/Inno/native
delta/rollback or installed-user acceptance. All six policy gates stay OPEN. No
normal payload/install/data/math, broad app/QA license, version/tag/release change.

### Private three-layer Unicode PDF bootstrap — 2026-10-19, no release

**39175100427 / fa68e2a SUCCESS**: separately pinned 27-DLL stock-SDK preflight,
then independent cold source build on another runner BEFORE app dependencies,
from the authenticated noticed archive: exact 20 source trees, 21 fresh DLLs,
marked Pango; two isolated production-dependency CPython 3.11 workers with same
Unicode profile/state/cache/TEMP and unrelated CWD, Unicode app/interpreter/DLLs.
Explicit UTF-8 memory Fontconfig, zero active system fonts, actual Unicode TEMP
TTF hashes and cleanup per document; real 1/4 A4 pages, Vazirmatn 400/700/all 30
digits. Native audit/candidate/witness byte bindings and final envelope recheck.
Stock SDK is NOT source provenance and never substitutes for the fresh 21 DLLs.

Actual failures are preserved and distinguished: CP1252 source-test decoding,
WeasyPrint temporary-font-path encoding, and native filename ACP 1252 despite
Python UTF-8. Direct identical-TTF Unicode-vs-ASCII controls proved the last one.
Private launch uses -I -B -X utf8 PLUS a modified CPython PE resource manifest
activeCodePage UTF-8; independently require GetACP()==65001. Both EXE hashes,
original/re-extracted manifests and SDK tool are recorded. Original manifest
semantics preserved, PRIVATE baseline restamped then unchanged across workers.
The EXE is NOT an unmodified upstream binary. Normal staging/installer unchanged;
1903+ capability, minimum product OS, CPython notices/signing/redistribution and
all-Windows-version coverage remain production review, not silently approved.

[Persian report](docs/reports/pdf-unicode-bootstrap-fa.md),
[source proof](docs/dependencies/pdf-unicode-bootstrap-proof.json),
[separate preflight proof](docs/dependencies/pdf-unicode-bootstrap-preflight-proof.json).
626 backend tests, Ruff/Mypy85/Bandit existing medium+high gate/license14 pass.
One CI dependency-audit failure has unknown original cause because signed logs
were inaccessible; exact audit/exit semantics retained, bounded diagnostics added,
and the actual next successful audit is recorded separately, not called a fix.
No advisory ignores/test skips/global UTF-8 CI masking/WeasyPrint monkeypatch.

Adapter/app QA NOT covered by limited native-build MIT grant. Normal renderer
and HTTP default unchanged, no ordinary launcher integration. Read-only TTFs are
NOT installed ACL proof, state reuse NOT disk-cache-hit proof. Six gates stay
OPEN: component/CRT rights, recipient recipe/toolchain review, durable anonymous
source delivery, installed replacement/EULA, ordinary pre-import bootstrap,
Inno/native delta/rollback and deferred installed acceptance. No user data/math,
install, version, tag or release changes; no publication authority inferred.

### Private pre-import no-site launcher — 2026-10-19, no release

39182480848 / 8118098 SUCCESS: stdlib-only entry validates independent baseline
and inventory digests/all baseline members before third-party imports. Require
-I -S -B -X utf8, reject early sensitive modules, pin full libffi path BEFORE
ctypes/application PDF code, verify ACP 65001 and actual loaded origin. Two fresh
PIDs (1528/3112), same state and baseline, real 1/4 A4 PDFs, Vazirmatn 400/700/all
30 digits, Unicode app/profile/bootstrap TEMP/worker TEMP/CWD, zero active system
fonts and strict cleanup. Three actual Windows rejection cases: omitted -S,
early ctypes, wrong inventory digest. 42 behavioral/workflow controls plus two
witness controls; 670 backend pass; Ruff/Mypy85/Bandit existing gate/license14.

[Report](docs/reports/pdf-private-launcher-fa.md),
[proof](docs/dependencies/pdf-private-launcher-proof.json).
This is separately pinned stock SDK/27 DLLs, NOT new source provenance or proof
of the NEW launcher with the prior 21 source DLLs. Prior source witness unchanged.
Setup/GITHUB_ENV defect regression, actual download/artifact timeouts, and direct
rerun API 403 are preserved; first setup stderr still unknown. No assertion/pin
weakening, silent failure relabel, advisory ignore, test skip or actual rerun was
used. Git push of the real regression checkpoint triggered a separate valid run.

Normal start_vira.cmd/staging/HTTP startup/Inno/updater/data/math/version/tags/
releases unchanged. CI/private TEMP only; not a signing/security boundary against
someone controlling both harness and entry. Normal HTTP startup, source21 pairing,
minimum OS/signing/notices, native delta/rollback and deferred installed acceptance
remain unproven; all six legal/source/production gates OPEN. MIT is still only
the explicit 14 native-build files, not this launcher/QA or application.

### Private real HTTP startup — 2026-10-19, not ordinary startup or release

39215968473 / 7634e93 SUCCESS: same no-site pre-import bootstrap, then real
migrator/create_app/Uvicorn on real TCP loopback with lifespan and shutdown.
Check live/ready/revision/compiled SPA/OpenAPI, reject unauthorized PDF/wrong
login/missing CSRF, use actual owner cookie and API-created synthetic orders.
Two fresh PIDs reuse actual SQLite and fixture IDs; four HTTP PDFs per process,
eight total 1/4 A4 PDFs, Vazirmatn 400/700, 30 Regular digits and ten Persian Bold
digits in actual route totals. All27 SDK DLLs loaded privately, callbacks valid,
TTF SHA/system-font exclusion/per-document temp cleanup independently checked.

Two client requests overlap; observed native render peak=1 because the existing
SQLite BEGIN IMMEDIATE transaction policy is preserved. Never claim two native
renders/concurrent throughput. Initial barrier inside renderer was incorrect;
moved to client before sending. Never change DB locking/math to force overlap.
Initial Windows attempt returned HTML and correctly FAILED; retain receipt.
Required private cache was missing, add creation/regression and traceback without
locals, then actual next run passes. Local optional native diagnostic lacks Pango;
it is NOT Windows evidence. 14 guards/workflow + two witness tests; 686 backend
pass. Local TCP tests use explicitly fake invalid PDF/static bytes; only actual
Windows external inspection proves native PDFs and compiled SPA serving.

[Report](docs/reports/pdf-private-http-fa.md),
[proof](docs/dependencies/pdf-private-http-proof.json).
Private stock SDK/27 DLLs with PROCESS-LOCAL font-adapter injection, not source21
pairing, normal production startup or installed-user acceptance. Existing proofs
immutable. No installer/normal launcher/staging/updater/version/tag/release/data/
math change, no request for user testing. All six gates remain OPEN. MIT still
only explicit14 native-build files; no new launcher/QA/application license grant.

### Private source-built real HTTP pairing — 2026-10-19, NOT distribution or normal startup

**39226693623 / b04440e SUCCESS**: separately authenticated noticed archive → cold build
from20 preferred source trees (binary caches disabled) → independent21-DLL audit
→ private no-site launcher → real factory/lifespan/Uvicorn TCP/auth/CSRF/SQLite
→ eight inspected1/4-A4 HTTP route PDFs and fresh-process restart with same DB/IDs.
Executed modified Pango `1.58.0-vira-local-source`; all21 actual loaded origins
and hashes bound to this run's native audit. Prior SDK27/1.58.2 and old source
proofs unchanged; SDK preflight is separate, never compilation provenance.
Vazirmatn400/700,30 Regular/ten Persian Bold digits, ACP65001, SHA-matched TTFs,
zero system fonts and per-document cleanup. Parallel clients, observed native
peak=1; no DB locking/math or throughput claim.
Source closure pins `ffi-8.dll`; bundled CPython `_ctypes` may use its distinct
`libffi-8.dll`. No alias/rename or source-FFI callback claim.

Keep failed39220310210/f479f70: all physical/binding/reverification steps passed,
annotation transport failed; original stderr unavailable (log-host EOF). Actual
upstream-volume regression exposes oversized repeated inventory metadata. Explicit
validated projection preserves every binding field/full raw inventory in artifact,
unchanged32-part limit; fixed pipeline repeats entire cold build/HTTP successfully.
26 guards +9 synthetic binder/volume tests +2 actual-witness controls;723 backend
pass. Fake/historical-schema tests are never fresh compilation evidence.
[Report](docs/reports/pdf-source-http-fa.md), [proof](docs/dependencies/pdf-source-http-proof.json).

PRIVATE/process-local QA font adapter only. Not normal production startup,
installed acceptance, signing/minimum OS, native Inno/delta/rollback, EULA or CRT
rights. All six gates OPEN; scoped MIT14 unchanged and not HTTP/QA/app code.
No installed/ordinary launcher/staging/version/tag/release/data/math change.

### App-owned PDF dispatch PREPARATION — 2026-10-19, not native wiring proof

Add stdlib-only `PdfRenderer` and immutable path-only `PrivatePdfPolicy`. Factory
keyword-only policy selects a per-app renderer; actual proforma route dispatches
through Request.app.state. Default None remains exact legacy render_pdf call,
no new setting/env/HTTP/UI opt-in and no installed launcher selects private mode.
Private mode owns per-document cache/config lifecycle in application code, no QA
renderer monkeypatch or caller-supplied configuration factory. Reject ambiguous
paths/symlinks and non-PDF output; fail cleanup before returning, never retry default.
Preserve existing self-contained HTML/CSP fallback, template/context/math/DB locks.
Factory/route DO change; pdf.py/pdf_fontconfig.py and native bootstrap do NOT.

22 synthetic/lifecycle/ASGI route/import controls;745 backend PASS (90.13s), no skips,
Ruff/Mypy86/Bandit existing gate/MIT14 PASS. OpenAPI modes identical. These tests use
explicit FAKE bytes, not native/real-TCP/embedded-font proof. Prior source21 witness
frozen, not relabelled as proof of new wiring. App-owned Windows HTTP/source21 pair
still FALSE/PENDING: next private native proof must use this policy WITHOUT replacing
renderer with QA FontAudit. Both policy/review snapshots synchronized, six gates OPEN.
No installed launcher/staging/Inno/updater/version/tag/release/business-data change;
normal font selection remains legacy, no expanded application/QA license grant.
[Report](docs/reports/pdf-app-owned-preparation-fa.md),
[limited local evidence](docs/dependencies/pdf-app-owned-preparation-evidence.json).

### Private application-owned Windows HTTP — 2026-10-19, not ordinary/default startup

SDK 39243690293 SUCCESS:27 DLL/Pango1.58.2. Separate fresh-source 39243690330
SUCCESS: authenticated noticed archive/cold20-tree21-DLL build, executed modified
Pango1.58.0-vira-local-source, legacy QA regression THEN distinct app-owned HTTP.
Each owned lane has2 fresh PIDs/same SQLite+IDs,8 actual1/4-A4 route PDFs, normal
factory/lifespan/TCP/login/CSRF/compiled SPA/OpenAPI and graceful shutdown.16 actual
owned PDFs total, never include regression PDFs or relabel historical witnesses.
Vazirmatn400/700,30 Regular/ten Persian Bold digits, TTF SHA, zero active system
fonts, independent font AND cache cleanup; private ACP65001/no-site and3 actual
negative guards. Parallel clients, observed document/native peak1, locking unchanged.

Factory selects its typed PrivatePdfPolicy/PdfRenderer: NO render_pdf replacement,
NO QA configuration factory. Callable identity/source fingerprints unchanged,
contextmanager source via inspect.unwrap. Passive plain-value lifecycle logging
has no native pointers/config objects/customer context; capture config restored.
Keep actual SDK worker failure39242791845 (missing active property), exact traceback
and new active-count regression; no success from incomplete first process. Full
rerun passes.17 guards+2 synthetic source+2 recorded-witness controls;766 backend,
Ruff/Mypy86/Bandit existing gate/MIT14 pass. Frozen old evidence unchanged.

[Report](docs/reports/pdf-app-owned-http-fa.md),
[SDK proof](docs/dependencies/pdf-app-owned-sdk-http-proof.json),
[source proof](docs/dependencies/pdf-app-owned-source-http-proof.json).
All six gates OPEN, policy/review progress synchronized, MIT only explicit14 build
files not app/QA. Still private caller/modified PE interpreter, not ordinary
production bootstrap, installed/visual acceptance, signing/minimum OS, Inno/native
delta/rollback, EULA/CRT or durable anonymous delivery. Default remains legacy;
no ordinary launcher/staging/version/tag/release/userdata/math change.

### Application-owned private bootstrap preflight PREPARATION — 2026-10-19

New stdlib-only app/private_pdf_bootstrap.py owns a READ-ONLY SDK27 plan verifier,
not an activator/installed entry. Frozen path/hash plan + immutable plain-data
snapshot; independent baseline/inventory hashes, exact full-file coverage (reject
unmanifested Python/native), canonical Windows/POSIX members/case aliases,
symlink/reparse rejection, required app/font members, private version/modified-PE
receipt and exact separately pinned 27-DLL SDK/preload. Source21 explicitly NOT
supported by this plan; historical SDK/source HTTP witnesses remain frozen.

Private prepare guard checks Windows CI, bundled3.11/-I-S-B-Xutf8, sensitive-module
absence, app package/code/interpreter origins and disjoint runner-owned Unicode
profile/state/CWD. Verification does NOT load DLL/CFFI/ctypes, set env/sys.path,
create directories, migrate DB, select factory or start server. Snapshot is not an
activation capability/signature or ACL/hardlink/TOCTOU/actual NTFS junction proof.
Future activator must revalidate and separately prove ACP/native/module origin.

94 synthetic/read-only/import/guard controls,860 backend PASS88.67s/no skips,
Ruff/Mypy87/Bandit existing gate/MIT14 PASS. Fresh isolated stdlib import AND
synthetic verification tested; Windows process flags/paths are SIMULATED only.
No real Windows preflight/native activation/new PDF/cold-source claim this phase.
Policy/review preparation flags synchronized; ALL SIX GATES OPEN. No ordinary
launcher, stage script, factory/route, settings/env opt-in, release/tag/version,
installed data/pricing/Inno/updater change. Unchanged stager copies new module as
ordinary app source but no launcher selects it; whole-app/QA license NOT changed.
[Report](docs/reports/pdf-bootstrap-preparation-fa.md),
[limited evidence](docs/dependencies/pdf-bootstrap-preparation-evidence.json).

### Private app-owned SDK bootstrap activation/HTTP — 2026-10-19

Explicit activate_private_sdk(plan) in app now owns full revalidation/preload/
ACP65001/native origin/handle lifetime/env-path-TEMP restore. Read-only verifier
APIs unchanged, no cached-snapshot bypass, no QA/config callback. First third-party
CFFI absolute SDK libffi before ctypes/app; native pointers never yielded. Runtime
scope does NOT unload modules/OS DLLs; fresh process required. Per-process fresh
bootstrap workspace separate from persistent private HTTP DB; freshness not weakened.

Distinct entry authenticates app module BEFORE execution, delegates native setup
to app then runs fixed prior app-owned HTTP worker. QA still orchestrates migration/
factory/server/fixtures; NOT ordinary startup. Existing launchers/cold-source lane
unchanged. Windows39286484245/d5e5f57 SUCCESS/job118174226710/artifact12204790607;
45583B witness SHAac0aa31d6854c541bbaba6be52e3865da9d1a4d77f25b84cab2a77a97857813d,
2 authenticated annotation parts, no independent ZIP download/hash claim. PIDs2352/
9096, same DB/IDs,8 NEW actual1/4A4 PDFs,Vazirmatn400/700,30/10 digits,two TTF hashes,
zero system fonts,27 mapped DLL/Pango1.58.2,font+cache+bootstrap temp cleanup and
settings restore.4 actual negatives incl unmanifested Python. Peak1,locks unchanged.

20 synthetic activation/binder/exception controls+1 recorded-witness control;
881 backend PASS92.58s/no skips,Ruff/Mypy87/Bandit current gate/MIT14 PASS. Exact
implementation CI39286501715 all5 SUCCESS. Final witness/docs commit checked separately.
[Report](docs/reports/pdf-bootstrap-sdk-http-fa.md),
[proof](docs/dependencies/pdf-bootstrap-sdk-http-proof.json),
[checkpoint](docs/dependencies/pdf-bootstrap-sdk-checkpoint-ci.json).

Source21 still explicitly unsupported by this plan/context; prior source evidence
NOT this activation proof. No new cold build, ordinary launcher/stager selection/
factory/route/settings/version/tag/release/installed userdata/math change. New files
copied as normal sources by unchanged stager, never auto-selected. All6 gates OPEN;
MIT14 only, signing/minOS/CRT/EULA/durable delivery/native Inno-delta-rollback and
installed acceptance remain unproven. Cooperative hashes NOT signatures/ACL/TOCTOU.

### Remaining readiness PHASE 1 OF 6 — 2026-10-20, PRIVATE source bootstrap COMPLETE

Per owner agreement, one complete phase per remaining workstream, not one phase
per small check. Phase1 includes source implementation, guards, tests, one actual
cold Windows compilation, all regressions, real owned bootstrap/HTTP and evidence.
Explicit source-audit SHA in immutable plan + activate_private_source; SDK API
rejects source and source API rejects missing audit. App owns exact noticed archive/
file/manifest,20-tree21-DLL hash/owner/version/cache binding, double preflight and
source ffi-8.dll preload/ACP/origin/lifetime/restore. No app import of QA or renderer/
configuration factory callback. CPython libffi-8.dll is distinct, no rename/alias or
source-FFI callback provenance claim. Read-only verifier APIs/default remain intact.

39388243191/88180ea SUCCESS: separate actual SDK preflight then cold source20-tree
build/cache disabled,21-DLL audit, executed Pango1.58.0-vira-local-source; legacy and
owned-font regressions followed by distinct app-owned SOURCE BOOTSTRAP mode and
post-activation noticed-envelope reverify. PIDs6792/8708,same SQLite/IDs,8 NEW actual
1/4A4 PDFs,Vazirmatn400/700,30/10 digits,two TTF hashes,zero system fonts,all font/cache/
bootstrap-temp cleanup and env/path/TEMP restore.5 actual negatives including wrong
source-audit digest. Peak1,parallel clients not parallel native throughput;locks/math
unchanged. Regression PDFs not counted/relabelled as new bootstrap proofs.

119672B witness SHA3c134b431fe977f2937e84b6139ec3daa19517c407cf5a6de904bdbeb2043a5d,
10 authenticated same-job annotation parts;artifact12250199759 metadata authenticated,
ZIP not independently downloaded/hashed. Repository hashes are canonical Git bytes,
not claimed staged Windows CRLF bytes.23 new synthetic source controls+1 recorded
witness test;905 backend PASS95.02s/no skips,Ruff/Mypy87/Bandit gate/MIT14 PASS.
SDK39388243073 and ordinary CI39388243225 all5 SUCCESS at same executable head.
[Report](docs/reports/readiness-phase1-source-bootstrap-fa.md),
[proof](docs/dependencies/pdf-bootstrap-source-http-proof.json),
[checkpoint](docs/dependencies/pdf-bootstrap-source-checkpoint-ci.json).

Five workstreams remain:2 ordinary launcher integration;3 native clean install/
delta/rollback preserving data;4 final legal/distribution package review (parallel);
5 deferred actual installed-user tests;6 separately owner-authorized release after
Persian notes. These workstreams are NOT one-to-one legal gates: ALL SIX GATES OPEN.
No main/factory/route/settings/installed launcher/stage script/version/tag/release/
user data/schema/math change. Current stager copies sources but never auto-selects
this mode. No ordinary-startup, signing/minOS, CRT/EULA/durable-public-source/native
Inno-delta-rollback/installed acceptance approval; MIT14 only, not whole app/QA.

Phase1 final-docs CI39394669426/aee483d FAILED only in recorded-audit replay on
Windows: test write_text translated canonical LF to CRLF, expected hash unchanged.
Exact write_bytes correction;905 local PASS95.02s/no skips; full final CI repeated.
[Immutable failure receipt](docs/dependencies/pdf-bootstrap-source-final-ci-failure.json).
Real cold source/bootstrap39388243191 remains successful, not relabelled/rebuilt.


### Remaining readiness PHASE 2 OF 6 — 2026-10-20, real CMD private SOURCE integration COMPLETE

The real scripts/start_vira.cmd now has an explicit PRIVATE source candidate mode;
its ordinary default body is unchanged (Phase1 normalized SHA256
 a385c16ae8eaf49a61b06f8016fc1b22deaa000bcb3bc01554b9ad8eb0229cf4).
App-owned desktop_entry owns audit/guards/activation, real migration+idempotent seed,
persistent secret, real factory+renderer, health-gated optional browser, foreground
Uvicorn and graceful shutdown. QA is ONLY external process/HTTP client, no injected
factory/renderer/configuration callback. Bootstrap workspace is fresh per process,
disjoint from persistent private business state. Lifetime/update locks and reparse/
marker guards precede native/app import. log_config=None preserves app logging;
actual TCP synthetic logging regression protects the independently reproduced bug.

Cold Windows39437161409/f64649eee502d6a29547798e386f5572d3dd5e3c SUCCESS, SDK fast
preflight118677276979 and source118679715648,20 preferred trees/cache disabled,
21 DLL origins/executed modified Pango/legacy regressions/real CMD/post-CMD source
envelope ALL SUCCESS. Actual PIDs2360/2380, same private DB/IDs/session/secret,
first seed6 currencies+22 accounts+1 user and restart all0,8 NEW real HTTP PDFs,
1/4A4 pages/Vazirmatn400/700/required digits/two TTF hashes/zero system fonts,
all document/bootstrap cleanup, graceful shutdown/lock release. Parallel clients
observed native peak1, not parallel native throughput.4 real pre-native/pre-app
negatives: wrong manifest/source audit, duplicate instance/update lock. Persian,
space, ! and & paths, readonly source TTFs and actual ACP65001 covered. User-data
sentinel and update-blocked DB preserved. No installed-user acceptance inferred.

544380B full witness SHA3eb97ba7c340e6d6fdb0326e8412a8d73d22591b28d9ab1727cc961a4b2e89cf.
Complete native audit1b73804a34668b08f4c79af677d17842e4cc02cf10fca53a1f34029a12983630;
16 Git-blob implementation hashes frozen at executable f64649e, not staged CRLF hashes.
Conservative full-inventory budget needed56 parts, capacity now64/eight steps, tested
losslessly BEFORE native build. GitHub's separate50 annotations/JOB cap still hid
44 parts after earlier phases consumed quota. Full successful artifact recovered
without app/native reexecution by39447134103/695ceee,8 independent SUCCESS jobs.
Each actually downloaded original artifact12277476098 ZIP, verified bytes SHA256
854f9cfe9f60073a381fb855a65a2c21c5c5d5cf4c0f90ae98c408f90d765888, original same-check
witness digest/bytes and original frozen binder.56 unique parts from authenticated
recovery checks reconstructed byte-identically. ZIP hashed on recovery runners,
NOT downloaded locally. All inventory/license/copyright retained. Extra steps do
not bypass50/job; use complete artifact or independent jobs.90-day artifact is
NOT durable public corresponding-source distribution.

Preserved failures:39416463306/c09 missing request parent BEFORE CMD/0 new PDFs;
39423104695/e3 closed LifecycleFile by default Uvicorn logging -> HTML fallback,
not PDF. Parents+fast CMD gate and log_config=None fixed without renderer/hash/
font-policy weakening.39431706305/ba superseded/cancelled during compilation,
not native success or a third runtime failure.945 backend PASS66.864s/zero skips,
errors or failures, including26 authenticated witness/binder/default-CMD controls;
Ruff/Mypy88/Bandit existing gate/MIT14 PASS. Executable-head CI39437161229 all5
SUCCESS; final docs/evidence checkpoint tracked separately.
[Report](docs/reports/readiness-phase2-desktop-startup-fa.md),
[authenticated proof](docs/dependencies/pdf-desktop-source-http-proof.json),
[full witness](docs/dependencies/pdf-desktop-source-http-evidence.json).

Phase2 complete ONLY within agreed private SOURCE option of REAL CMD, NOT public
ordinary-default activation. Four workstreams remain:3 selected-path Inno native
clean install/incremental delta+rollback preserving all data;4 final legal/CRT/EULA/
notices+durable exact source delivery;5 deferred installed-user data/Excel/visual/
browser/Ctrl+C/window-close acceptance;6 separately owner-authorized release with
Persian notes/immutable tag/in-app permission. ALL SIX legal/distribution gates OPEN.
No Phase3, user-install activation, data/math/UI/schema/version/tag/release change.
MIT14 only, not whole app/QA/third-party CRT rights. Cooperative controls, not ACL,
signature or hostile-owner TOCTOU guarantee; stale locks not automatically deleted.

Phase2 docs/evidence checkpoint eb7e761: CI39448011124 all5 SUCCESS; license39448011002,
source kit39448011222 and modified kit39448011383 (including Windows recipient) ALL
SUCCESS. [Final checkpoint](docs/dependencies/pdf-desktop-source-checkpoint-ci.json).
Next checkpoint-only tip CI is observed separately; no new native/source claim.


### Remaining readiness PHASE 3 OF 6 — 2026-10-21, ACTIVE / NOT COMPLETE

Owner continuation authorizes private native Inno/incremental-update/rollback work,
NOT public activation or release. Existing vira.iss now has an explicitly defined
PrivateSourceCI preset with distinct AppId/registry, selected empty directory,
isolated runner profile, external three-digest anchor and data-preserving uninstall.
App-owned private_installed_source bridge delegates fresh requests to unchanged
REAL start_vira.cmd and unchanged app-owned bootstrap/lifecycle. Existing real
vira_updater.ps1 has an explicit private context branch: anchored OLD runtime byte
verification, shared mutex and external runtime/controller clone before replacement.
Public default branches/allowlist remain unchanged. New stdlib private controller
assembles/verifies exact changed-file delta, bounded BSDIFF, backups/journal/DB,
apply/restart/health/rollback; it is NOT yet real-native acceptance. No QA factory.

52 new SYNTHETIC byte/anchor/path/tamper tests; opaque .dll/.exe test bytes are NOT
native execution.997 local backend PASS81.843s/zero skips/errors/failures, Ruff,
Mypy89/Bandit existing gate/MIT14 PASS. Windows preflight compiles both actual Inno
presets and installs/uninstalls ONLY opaque data; cannot prove native PDF/update.
Remaining within SAME Phase3: actual Source21 Inno/startup/PDF, complete private
in-app permission+delta selection, real apply/rollback/data/session proof, failure/
recovery controls, authenticated full evidence and final CI. No phase completion,
no Phase4 approval, no user-install/data/schema/math/UI/version/tag/release change.
16 executable files frozen by Phase2 proof remain unchanged. ALL SIX GATES OPEN;
new tooling NOT added to the limited14-file MIT grant.
[Phase3 work-in-progress](docs/reports/readiness-phase3-native-install-update-fa.md).


Phase3 initial Windows preflight39583808465 and CI39583808447/4e2ecef failed.
Opaque-byte pytest parameter IDs exceeded Windows PYTEST_CURRENT_TEST env32767
limit: exact byte data retained, short explicit IDs added; no skipped controls.
Security gate found9 newly reported vulnerabilities in certifi2026.7.22/Pillow12.3.0;
lock upgraded to2026.10.19/13.0.0, no audit ignore. Local audit now clean (old seeded
setuptools tool upgraded separately, not added as app dependency).
[Preserved failure](docs/dependencies/phase3-initial-preflight-failure.json).
App bridge uses proven raw CMD quoting/profile-owned CWD; generated Inno uninstaller
is outside fully manifested payload. Added real Windows CMD-only fixture check;
no native-runtime execution claim.53 focused tests PASS locally; next Windows
preflight/CI still required. Phase3 remains ACTIVE/INCOMPLETE.

Phase3 second Windows run4516a48: auxiliary log retrieval failed BEFORE preflight;
removed only that retrieval, not a test. Ordinary CI39584663404 backend/security,
frontend/OpenAPI/Playwright SUCCESS; Windows failed in new AST test's implicit
cp1252 source read. Explicit UTF8 correction, no expected hash/data relaxation.
[Second failure](docs/dependencies/phase3-second-preflight-failure.json).
Added6 explicitly simulated transaction tests: real filesystem/ZIP/BSDIFF/SQLite
backup+restore/quarantine with mocked process boundaries; plus raw real-CMD-only
check.59 focused tests,1004 full local tests PASS78.304s/zero skips/failures/errors.
Actual Source21 installed app/in-app delta/rollback proof STILL NOT DONE.

Phase3 fffbb1f/preflight39585368010 failed in2 simulated SQLite writer tests:
connection transaction context did NOT close its Windows file handle. Exact
contextlib.closing+transaction correction; production DB tool already closes.
[Third failure](docs/dependencies/phase3-third-preflight-failure.json).
No cases skipped, no native/Inno success inferred.

Phase3 preflight39585596841/9d8d778:59 Windows synthetic tests PASS, public
Inno compile PASS, private compile FAILED (ISPP has no Pascal Chr function).
Use literal doubled-quote Parameters in conditional Inno entries.
[Fourth failure](docs/dependencies/phase3-fourth-preflight-failure.json).
Inno6.7.1 compiler banner says non-commercial use only: no commercial distribution
entitlement inferred; legal review still OPEN. No installed Source21 proof.

Phase3 LIMITED Inno checkpoint39585771427/e5103ad SUCCESS:59 Windows focused
controls, BOTH Inno presets compiled, real private opaque-fixture install/uninstall
in selected Persian/space/!/& path, external anchor and data preserved, duplicate
anchor rejected. Interpreter/DLL fixture bytes NEVER executed.
[Limited authenticated proof](docs/dependencies/phase3-inno-limited-preflight-proof.json).
Follow-up requires rejection of orphan private state and exact payload file-set
(no generated Inno uninstaller inside manifested app root). This is NOT Source21
installed/runtime/delta acceptance or phase completion. Phase3 remains ACTIVE.

Phase3 9c7b764 checkpoint: CI39586234984 ALL5 SUCCESS; license39586235299, source
kit39586235160, modified kit39586235248/Windows recipient ALL SUCCESS. Limited
Inno39586235223 SUCCESS with orphan-state rejection and exact opaque payload set;
[proof](docs/dependencies/phase3-inno-orphan-preflight-proof.json),
[incomplete checkpoint](docs/dependencies/phase3-incomplete-checkpoint-ci.json).
1004 local tests PASS77.446s/no skips/errors/failures, security audit clean.
Follow-up confines private installer directory to runner TEMP and checks OLD
anchor/manifest reparse paths before cloning runtime; verify its tip separately.
Still NO actual Source21 installed app/in-app native delta or rollback proof, NO
new Phase3 cold build started. Phase3 ACTIVE/INCOMPLETE, not permission for Phase4.


### Phase3 private in-app channel checkpoint — still INCOMPLETE (2026-10-21)
The genuine private installed CMD bridge passes an opt-in marker and pinned port;
marker alone cannot enable this channel. Runner/profile/state ownership, exact
runtime Settings and old external manifest anchor must match. Existing streaming
size/SHA verification precedes private target-anchor staging and a receipt; apply
rechecks package/staged metadata and chooses ONLY the anchored installed OLD
helper. Native/pdf operations remain forbidden in public staging. Target port and
browser policy cannot redirect the client. Controller/runtime cloning is outside
the private data profile. A separate channel lock ties restarted-client polling
to the current attempt; nested finally releases the mutex even when receipt
publication fails. Crash/stale-lock recovery is NOT yet proven.

23 new SYNTHETIC channel/CLI controls; complete local backend suite1027 PASS in
77.29s, zero failures/errors/skips. Ruff PASS; Mypy90 PASS; Bandit CI-level -ll
PASS. Initial unfiltered Bandit reports27 low findings (not a zero-findings claim).
Fresh local venv inherited setuptools66.1.1; initial audit failed6 reports for
3 advisory IDs; upgraded ONLY the local tooling seed to84.2.1, audit then PASS.
No lockfile or shipped dependency/version change in this checkpoint. Byte-exact
UTF8 manifest generation now matches delta metadata across Windows/Linux.
Windows PS parsing, new regressions and real limited Inno checks must verify the
new commit separately; previous f688 CI is NOT evidence for these changes.
No Phase3 Source21 cold build/installed native transaction has run. Clean install,
real permissioned changed-native delta and verified rollback/data preservation,
plus crash/stale recovery remain acceptance work. Phase3 ACTIVE/INCOMPLETE;
all6 distribution gates OPEN, public1.0.10/user installation untouched; no Phase4,
tag, release or expanded MIT permission.


Phase3 follow-up:27 synthetic private-channel controls; complete local suite1031
PASS68.32s with ZERO failures/errors/skips. Added rejection of data/DB/updates and
version-staging links BEFORE writes, plus normalized malformed archive failures.
Phase2 frozen16 Git blob digests rechecked: all identical. 263fe1f is independently
verified by CI39596502047 ALL5 SUCCESS and limited Windows39596501961 SUCCESS
(PS parsing, synthetic channel controls and opaque Inno, NOT native acceptance).
[Explicit incomplete channel receipt](docs/dependencies/phase3-private-channel-checkpoint-ci.json).
Those CI runs precede the four extra link regressions; follow-up needs its own CI.
Important integration blocker found rather than bypassed: frozen Phase1/2 private
bootstrap accepts ONLY version0.0.0-private-unicode-proof. Synthetic99.30.x channel
fixtures do not prove a versioned native installation. Need explicit independently
anchored installed-version contract and regression proof WITHOUT weakening public
or existing Phase1/2 rejection. No new Source21 cold build started; Phase3 remains
ACTIVE/INCOMPLETE, six distribution gates OPEN, no publication/Phase4 permission.


### Phase3 installed-version implementation (2026-10-21; INCOMPLETE)
Owner authorized continuing without user action. Explicit schema2 anchor adds a
canonical version; the app binds it to the independently checked manifest and
source pins. An explicit installed request passes the anchor through the SAME
real CMD; legacy fixed-version and public paths remain closed. No env-only opt-in,
QA callbacks, SDK fallback or silent version-file rewrite. Target version binding
and contract-downgrade rejection also cover generator/stager/controller.
[Contract and acceptance limits](docs/dependencies/phase3-installed-version-contract.md).

IMPORTANT evidence change: Phase3 now extends TWO Phase2 runtime modules AND their
workflow (THREE of the16 historical frozen files). Exact old bytes retained in
`docs/dependencies/phase2-frozen-implementation/` match original proof hashes;
other13 files unchanged. Old proof hashes/witnesses are NOT rewritten; historical
Windows evidence does NOT attest new runtime. Legacy regressions and new28
synthetic contract/ZIP/BSDIFF/assembly tests run; final local1059 PASS87.59s with
zero failures/errors/skips; Ruff/Mypy90/Bandit CI-level/audit PASS. The initial
full run's single evidence assertion was FIXED by archiving the omitted original
workflow, not ignored or skipped. Fresh Windows/cold-source execution still must
verify the new contract; Inno version99.30.0 is DISPOSABLE PRIVATE QA only, public
version remains1.0.10. No user install/data/math/UI/schema changes, no Phase4 or
release/tag approval; all6 distribution gates remain OPEN. Phase3 ACTIVE/INCOMPLETE.


Phase3 execution blocker after17989b39e0089421ed4c57fe4f98dcb7a8131575 push:
remote ref confirmed, but Actions lists ZERO new runs/check suites/check runs for
that revision. Automatic suppression cause NOT established. Explicit source
workflow dispatch and Actions-permissions API each returnHTTP403, "Resource not
accessible by integration". Do NOT claim a cold build was started or new Windows
proof exists. [Blocked receipt](docs/dependencies/phase3-version-contract-blocked-checkpoint.json).
Add explicit workflow_dispatch to CI/private preflight/source workflows so an
Actions-authorized connection can run this SAME branch. This does not grant
external API permissions; GitHub/Arena connection's Actions authorization needs
attention. Never request passwords/tokens/codes. Local1059 PASS remains valid for
runtime code; manual-trigger-only follow-up does not change runtime. Phase3 still
ACTIVE/INCOMPLETE; owner install/data/public1.0.10 untouched, no release/tag.


Phase3 automatic-run update: push workflows subsequently appeared; the earlier
zero-run/403 checkpoint is HISTORICAL, not a current total execution block.
Manual dispatch STILL403, but automatic CI39609353418 and source39608813235 are
running. No user reconnect/action is needed to continue this automatic path.
Windows preflight39608813001/job119251942209 FAILED at17989b3: build_manifest CLI
printed Persian path to cp1252 stdout (UnicodeEncodeError). [Failure receipt](docs/dependencies/phase3-version-contract-windows-unicode-failure.json).
Fix the real CLI stdout to UTF8; retain Persian path and force ASCII inherited
output in the existing assembly test to prevent regression. Native ACP/loader
and manifest bytes unchanged.81 focused local controls PASS, Ruff/Mypy90 PASS.
Re-run Windows preflight AND source workflow on the fix; do not skip failed test
or infer native success from local/synthetic controls. Phase3 still INCOMPLETE.


Phase3 stdout fix4669c5e PUSH CONFIRMED; full local suite1059 PASS87.72s, zero
failures/errors/skips; Ruff/Mypy90/Bandit CI-level/dependency audit PASS. While
collecting fix-run results, GitHub API authentication failedHTTP401 "Bad credentials"
for run/job reads. This is NEW and distinct from the earlier manual-dispatch403.
Do not infer latest Windows/source result; it is UNKNOWN until connection repair.
[Exact checkpoint](docs/dependencies/phase3-stdout-fix-auth-expiry-checkpoint.json).
Reconnect GitHub in Arena; no passwords/tokens/codes in chat. Automatic workflows
may continue remotely; their current status cannot be read. User installation and
public1.0.10 untouched, Phase3 INCOMPLETE, no release/tag. This documentation-only
checkpoint is saved locally; no further remote push attempted with known-bad auth.


### Phase3 resumed: real Windows stdout fix PASS; cold source build ACTIVE
GitHub repository/Actions reads work again. No owner reconnect is currently
required to continue automatic runs; manual dispatch403 is not a total blocker.
4669c5e CI39610014300 ALL5 SUCCESS; limited Windows39610014273/job119256125181
SUCCESS (including the previously failing Unicode CLI/assembly test). Source
workflow39610014494/job119259657791 observed ACTUALLY compiling target libraries
from local preferred trees with binary caches disabled. This is build progress,
NOT completed Source21 install/delta acceptance.

New safety fix: keep `state/data/updates/.update.lock` through target/rollback
readiness AND durable terminal journal. Only the explicit installed SOURCE
request with matching64-hex controller nonce/native lock may start under it;
legacy, env-only, foreign-profile/token/owner/link requests remain rejected.
The existing production HTTP/scheduler gate continues blocking mutations503;
health reads work. Commit journal failure restores old files/DB/anchor while
writes stay closed; rollback readiness/journal failure retains quarantine.
New12 controls; full local1071 PASS86.71s with zero failures/errors/skips; Ruff,
Mypy90, Bandit CI-level and dependency audit PASS. Initial static call-order test
needed its extended-call prefix/explicit installed-role assertion updated, not
removal; initial post-unlock403 test expectation corrected to existing CSRF gate.
[Checkpoint](docs/dependencies/phase3-write-quarantine-checkpoint.json).
Fresh Windows/Source21 acceptance for THIS safety follow-up still required.
Source workflow queues new verification WITHOUT cancelling an active cold build.
Do NOT claim real native delta/rollback or crash/stale recovery yet. Phase3 stays
ACTIVE/INCOMPLETE; all6 gates OPEN, public1.0.10/user data untouched, no Phase4/tag/release.
