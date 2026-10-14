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
| 3 | **Design system** | Tailwind + shadcn/ui (Radix): dialogs, popovers, command palettes, date-range pickers, comboboxes; dark/light themes. **Vazirmatn** primary font + **JetBrains Mono** for numbers; `tabular-nums` on all financial figures. Reusable `<Money />` component: ISO 4217 formatting, inflow/outflow coloring, accounting parentheses `($1,234.56)` for negatives. |
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
   - **Vazirmatn** + **JetBrains Mono**; `tabular-nums`; **Persian numerals `۰۱۲۳۴۵۶۷۸۹` by default** everywhere (no toggle). Money, arithmetic, account codes, decimal values, IDs, negatives rendered with isolated LTR (`dir="ltr"`, `unicode-bidi: isolate`) in RTL contexts. Internal values stay machine-readable; Persian formatting at presentation layer only.
   - **Jalali (Solar Hijri) calendar exclusively** (`date-fns-jalali` + fa-IR locale) for pickers, filters, forms, fiscal selectors, reports, dashboards; no Gregorian picker or calendar toggle in UI. Store dates canonically Gregorian ISO 8601 (or UTC timestamps); convert at the edges. Backend/PDF use `jdatetime` + Babel for consistent Jalali formatting. Iranian fiscal years begin **1 Farvardin**; correct Jalali leap-year handling.
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
| Frontend | React 19, TypeScript 5+ strict, Vite, TanStack Router/Query v5/Table v8/Virtual, Zustand, React Hook Form + Zod, decimal.js, Tailwind CSS + shadcn/ui (Radix), Vazirmatn + JetBrains Mono, react-i18next (fa only), date-fns-jalali, cmdk, react-hotkeys-hook, ECharts/Recharts, Plotly, react-pdf, react-zoom-pan-pinch, PapaParse, react-dropzone, openapi-typescript + openapi-fetch, Umami (optional) |
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

Source: `قیمت نهایی.xlsx`, single `Sheet1`, cells A1:F35. This is the basis for the **Sales Price Calculations page** (Phase 1 → Production). Phase 1 must formalize these relations into the product spec and normalize the dimensional quirks noted below. All amounts in **Toman**.

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

*(B8 نایلون بسته بندی is defined but not referenced by any formula — confirm intended use, e.g., inside packaging cost.) Also note B2 (printer power) is defined but not referenced by B19, which uses `B4*B14` only — the authored sheet omits `power × hours`; Phase 1 must decide whether to include `B2` (`1.3 × B14 × B4`).*

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
| E35 | … زنجیر دار | `=E34+B24+(E34*(10/100))` | final unit price (chain) |

### A.5 Quirks to normalize in Phase 1 ("compile every relation and make it as perfect as you can")

1. **B6** labeled «درصد» (percent) but used as a ×2.5 multiplier (i.e., 250% of cost). Formalize as `sale_price = cost × profit_factor` with configurable factor.
2. **B31** hardcodes `13.1` instead of referencing **B7**; and chain-variant commission (E33) reuses B31 (computed from non-chain B29) instead of `E29*B7/100`.
3. **B32** mixes total (B28) with per-unit (B24) — dimensional inconsistency.
4. **B2** (printer power kW) and **B8** (packaging nylon) are defined but unused by formulas — decide whether to wire them in (e.g., electricity `=B2*B14*B4`, packaging inside B21).
5. **B35** adds B24 again plus a 10% contingency on B34; the 10% is an unnamed constant — expose it as a configurable "marketplace risk/return buffer".
6. Currency is implicitly **Toman** everywhere; the page must follow §Phase-7 currency rules (Persian numerals, Toman default, LTR-isolated figures).

---

*Compiled from `VIRA_SQLite_No_Docker.md` and `قیمت نهایی.xlsx` (Sheet1, A1:F35), plus user amendments. **Status:** Phase 7 complete 2026-10-14 — Enhancements & Localization: unified search (FTS5 + LIKE under one parameterized path, Decimal numeric tokens → scaled-INTEGER amount matches, RapidFuzz re-rank, entry-number/memo coverage), pluggable storage (StorageBackend protocol, local + S3-compatible with lazy boto3/SSE/sha256 content-addressed layout/presigned GET + 302 delivery, faceted <ReceiptViewer/>), Persian-only react-i18next (/locales/fa/{common,ledger,reports,validation}.json namespaces, no language switcher), logical CSS (ms-/me-/ps-/pe-/border-s/text-start) + Jalali fiscal year 1 Farvardin + Jalali print-to-PDF headers + centralized <Money/> decimal.js audit, privacy-first Umami (VITE_UMAMI_* opt-in, typed useAnalytics(), zero-PII redaction) on the four workflow events, Ctrl+K palette + journal/accounts filter bars on /api/v1/search. 144 pytest + 63 Vitest green, ruff + mypy clean, tsc + eslint clean, build green, Bandit 0 medium+, pip-audit clean. Phases 1–7 delivered. Awaiting the user's **\"proceed\"** to start Phase 8 (Windows Packaging & Update Distribution).*