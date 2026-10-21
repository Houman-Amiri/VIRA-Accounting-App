Persian Accounting App (V.I.R.A)

Role : You are a world class Iranian full-stack Windows App developer with the best programing, security, database design, UI/UX design skills. Working for the V.I.R.A company who is demanding an Accounting App.



Here's my App idea in a phased execution plan (contains 8 phases):&#x20;

**Mandatory architecture constraints — follow these in every phase:**
- Use **SQLite only** as the application's database. Do not add PostgreSQL, another database server, or a database abstraction that assumes server-specific SQL features.
- **Do not use Docker, Docker Compose, Dev Containers, container images, or any container runtime.** Install and run the application directly on Windows using Python, Node.js, a Python virtual environment, and native Windows scripts/services.
- The SQLite database must be a local file stored outside the Git repository, defaulting to `%LOCALAPPDATA%\VIRA\data\vira.sqlite3` for a single Windows user. Make the path configurable through `SQLITE_DATABASE_PATH`.
- Treat SQLite's typing, locking, and trigger limitations as design constraints. Use integer-scaled storage for exact monetary values, application-level `Decimal` validation, short write transactions, WAL mode, and SQLite-compatible SQL only.
- The canonical frontend is the React + TypeScript + Vite SPA in Phase 3, backed by FastAPI. Do not build a separate HTMX/Alpine frontend; Jinja2 may be used for server-rendered PDF documents only.
- Create and maintain a `project brief.md` containing the actual selected stack and these non-negotiable constraints. If any later section conflicts with these constraints, these constraints take precedence.
- Ship and update the application as a native Windows product: an **Inno Setup** installer with a user-selectable install directory, published from GitHub (Actions artifacts + versioned Release assets), strict `vX.Y.Z` release tags for every version, and an in-app **Check for updates** system that downloads only the parts that changed (delta updates) and never loses user data (see Phase 8). No container-based packaging or update channels.
- build the the app separatly in phases, start with compiling requests in this file and right its master prompt and place it in the repo so you can read it any time needed.when ready wait for me to say "proceed", then you can start phase one.

**Pricing clarification — repair phase 4 (user-selected literal Excel parity):**
- `قیمت نهایی.xlsx` is the source of truth. Preserve its actual formulas, including quantity behavior: B25 is not multiplied by B15; E25 is B25+B15*B9; B29/E29 divide by B15.
- Both variants reuse the plain commission B31 (literal 13.1%, not B7), and both final prices use the plain B34*10% buffer. E35 is `=E34+B24+(B34*(10/100))`.
- B2, B7 and B8 are defined but unused in the formulas; do not silently wire them in. Show shared cell references and literal constants honestly in the UI.
- Original sample (240 g, 10 h, quantity 1): B35=2760748.5 and **E35=2780748.5 Toman**, not the previously reported normalized E35=2785630.5.
- Use decimal arithmetic, independently extracted workbook fixtures and quantity>1 regression tests. Existing saved financial data and price snapshots must remain untouched.

Phase 1(initiation & planning):

1.      Main Idea: [An Accounting App to Manage my warehouse goods (3D printing Filaments and produced Models), Orders and production. In the warehouse section it must have these attributes: name of the filament, weight, entity, color, price, date and supplier name and address. In the Orders section : date, full name of the costumer, phone number, Address, Order details and status. In the production section: production based on the order details and my Warehouse Inventory. Main features for the Warehouse section: Stockout / Inventory Shortage alarm, supplier suggestion to buy from based on the score I give them based on their price, quality and the time they send the order. Main features for the Orders section: Sales Proforma Invoice with Word and PDF export and Sales Report Daily-Weekly-Monthly and annual with the search and filter ability. Main features for the production section: a Sales Price Calculations page based on the Excel file provided in the Repo named "قیمت نهایی.xlsx" (read all cells in the file, extract texts and formulas, compile every relation and make it as perfect as you can.)]

2.      [this app must have a live-looking landing page that simultaneously Shows the Warehouse Inventory by showing beautiful Chart and recent products with some details.

3.      The core data entities, fields, and relationships are “products to sell" and Warehouse Inventory items, a fully dynamic Dashboard that controls and Supervises everything].

4.      Write project brief for consistent AI context and place it inside a MD file named “project brief”.



## Phase 2: Core Stack (Back-end)

Use the following Python development stack and architectural specifications to build the accounting application. Adhere strictly to the library choices and financial integrity rules defined under each feature module below:

1\. Core Ledger & Double-Entry Accounting Engine

* **Exact Decimal Arithmetic (`decimal.Decimal`):**

  * Strictly forbid the use of `float` for any monetary values or calculations.

  * Use Python's built-in `decimal.Decimal` configured with `ROUND_HALF_EVEN` (banker's rounding) at the application layer. Because SQLite does not enforce fixed-precision decimal types, store money as `INTEGER` scaled by 10,000 and exchange rates as `INTEGER` scaled by 100,000,000. Convert through tested utilities and reject overflow; never use `float` for financial calculations.

* **Currency & Money Representation (`py-moneyed` + `Babel`):**

  * Pair every monetary `Decimal` amount with an ISO 4217 currency code (e.g., `USD`, `EUR`) using `py-moneyed` to prevent invalid cross-currency arithmetic without an explicit exchange rate.

  * Use `Babel` for locale-aware currency formatting and display.

* **Accounting Invariant Validation (`Pydantic v2`):**

  * Enforce strict double-entry validation rules in Pydantic schemas before database persistence:

    * Every `JournalEntry` must contain at least two `TransactionSplit` lines.

    * The sum of all debits must strictly equal the sum of all credits ($\sum \text{Debits} - \sum \text{Credits} = 0$) per currency before a transaction can be posted.

* **Optional Ledger Core (`beancount`):**

  * Support compatibility with `beancount` data structures and plain-text double-entry accounting principles where applicable.



2. Database, Storage & Immutable Audit Trail

* **Primary Database (SQLite only):**
  * Use SQLite 3.45+ as the sole database engine. Store the database in a local file, never inside the source repository, a synced cloud folder, or a network share.
  * Configure every database connection with `PRAGMA foreign_keys=ON;`, `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and a reasonable `PRAGMA busy_timeout` (for example, 5000 ms). Verify that required settings are active at startup.
  * Use SQLite `STRICT` tables where compatible. Use SQLite-supported declared types (`INTEGER`, `TEXT`, `REAL`, `BLOB`, `ANY`) only in `STRICT` tables; avoid PostgreSQL-specific types or SQL semantics.
  * Store money as scaled `INTEGER` values (`amount × 10,000`) and FX rates as scaled `INTEGER` values (`rate × 100,000,000`). The application must convert values to/from Python `Decimal`; enforce documented amount bounds so integer arithmetic cannot overflow.

* **ORM & Schema Migrations (`SQLAlchemy 2.0` + `Alembic`):**
  * Use modern SQLAlchemy 2.0 typed declarative syntax (`Mapped`, `mapped_column`) with the SQLite driver `aiosqlite` if an async API is retained.
  * Keep ORM models compatible with SQLite, use `TEXT` for UUIDs, ISO-8601 dates/timestamps, and JSON-serialized text, plus `INTEGER` for booleans (`0`/`1`) and scaled monetary values.
  * Manage schema changes with versioned Alembic migrations. Test both upgrade and downgrade paths against temporary SQLite database files. Do not rely on server-specific types or SQL features, third-party extensions, advisory locks, or deferred constraint triggers.

* **Immutability & Audit Logging (`SQLAlchemy Events` + SQLite triggers):**
  * Implement append-only ledger principles: reconciled or locked transactions must never be hard-deleted or silently overwritten; corrections require contra/reversing entries.
  * Use SQLAlchemy session events and SQLite-compatible triggers for audit capture and enforceable row-level protections. Use application transaction services for invariants that SQLite cannot enforce as deferred cross-row constraints.
  * Store old/new audit snapshots as valid JSON serialized in `TEXT`, with UTC ISO-8601 timestamps. Protect audit records from ordinary application updates/deletes and include the actor, action, affected table, record ID, and timestamp.

3\. Backend Web Framework & API Layer

* **Primary Framework (`FastAPI`):**

  * Build modular routers with dependency injection for database sessions, authentication, and ledger services.

  * Leverage native `Pydantic v2` serialization for both JSON REST endpoints (OpenAPI/Swagger documented) and HTML form validation.




4. User Interface, Forms & Interactive Tables

* **Canonical UI:** Use the React + TypeScript + Vite SPA defined in Phase 3 as the only application frontend. Do not create a parallel HTMX/Alpine.js application.
* **PDF templates only (`Jinja2`):** Use Jinja2 HTML templates only where useful for generating invoices and printable accounting documents on the backend.
* **Design system:** Use Tailwind CSS with `shadcn/ui` / Radix primitives, full Persian RTL support, accessible keyboard interaction, financial data tables, status badges, modal dialogs, responsive layouts, and dark/light themes.

5\. Bank Statement Import & Reconciliation

* **CSV & Spreadsheet Ingestion (`Polars` or `Pandas` + `openpyxl`):**

  * Build a configurable ingestion pipeline that reads bank CSV and `.xlsx` files, normalizes dates, strips whitespace/noise from payee descriptions, and maps columns to internal ledger schemas.

* **Standard Financial File Parsers (`ofxtools`, `mt940`, `camt`):**

  * Parse `.OFX` / `.QFX` files with `ofxtools` and European `.MT940` / `CAMT.053` XML statements, extracting unique bank transaction IDs (`FITID`) to guarantee idempotent imports and prevent duplicate entries.

* **Automated Bank Feeds (`httpx` + `GoCardless Bank Account Data API` / `Plaid` / `SimpleFIN`):**

  * Use async `httpx` clients to connect to PSD2/Open Banking APIs (GoCardless for EU/UK, Plaid or SimpleFIN for North America) for automated transaction syncing.

* **Smart Categorization & Auto-Matching (`RapidFuzz` + `Scikit-learn`):**

  * Use `RapidFuzz` string similarity and a lightweight local classifier to match imported bank lines against historical payees and automatically suggest target Expense/Income accounts and reconciliation matches.



6\. Financial Reporting, Budgeting & Dashboards

* **Core Accounting Statements (`SQL Recursive CTEs` + `Polars`):**

  * Generate standard financial reports using SQL `WITH RECURSIVE` Common Table Expressions to roll up hierarchical account trees:

    * **Balance Sheet:** Assets, Liabilities, and Equity snapshot as of a specific date.

    * **Income Statement (Profit & Loss):** Revenue vs. Expenses over a selected period.

    * **Cash Flow Statement & Trial Balance:** Period movement and debit/credit equilibrium checks.

* **Interactive Financial Visualizations (`Plotly` or `Apache ECharts`):**

  * Render interactive charts embedded directly into Jinja2 templates, including Net Worth trendlines, Income-to-Expense Sankey flows, Cash Flow waterfalls, and Monthly Budget burn-down progress bars.

7\. Receipts, OCR & PDF Invoicing

* **PDF Generation (`WeasyPrint`):**

  * Generate print-ready, pixel-perfect PDF invoices and year-end financial statements directly from styled HTML/CSS templates.

* **Receipt OCR & Structured Extraction (`PaddleOCR` / `Tesseract` + `LiteLLM` / `Instructor`):**

  * Extract raw text from uploaded receipt images/PDFs locally using `PaddleOCR` or `pytesseract`.

  * Optionally parse messy receipt text or images into strict Pydantic models (`merchant`, `date`, `subtotal`, `tax`, `total`, `currency`, `line_items`) using `Instructor` + `LiteLLM` (supporting local Ollama models or cloud vision APIs).

* **Content-Addressable File Storage (`Local Filesystem` or `S3` / `MinIO` via `boto3`):**

  * Store receipt attachments renamed by their `SHA-256` file digest to prevent duplicates and link their metadata to the corresponding `JournalEntry`.



8\. Multi-Currency & Scheduled Automation

* **Background Job Scheduler (`APScheduler` or `Huey`):**

  * Run an in-process or lightweight task scheduler to automatically generate recurring journal entries (e.g., rent, subscriptions, depreciation, payroll) on scheduled cron intervals.

* **Automated Foreign Exchange (FX) Rates (`httpx` + `Frankfurter API`):**

  * Fetch daily reference exchange rates from `Frankfurter.app` (ECB data) and store historical rates in an `ExchangeRate` table to compute realized and unrealized FX gains/losses across multi-currency accounts.



9\. Testing & Financial Integrity Verification

* **Unit & Integration Testing (`pytest` + `httpx.AsyncClient`):**

  * Maintain comprehensive test coverage for all ledger services, API routes, statement parsers, and database constraints using isolated test transactions.

* **Property-Based Financial Testing (`Hypothesis`):**

  * Use `Hypothesis` to generate randomized multi-split transactions, edge-case decimal values, and currency conversions to mathematically verify that the ledger never violates double-entry balance invariants or loses precision.



10. Security, Backups & Self-Hosting

* **Authentication & Access Control (`FastAPI-Users` / `Authlib` + `pwdlib` + `pyotp`):**
  * Secure the application with `Argon2id` password hashing (`pwdlib`), secure HTTP-only session cookies, CSRF protection, and optional TOTP two-factor authentication (`pyotp`).

* **Native Windows Deployment (no container runtime):**
  * Run FastAPI and the built React static assets directly on Windows. Provide `start_vira.bat` and `stop_vira.bat` or equivalent PowerShell scripts, plus an optional Windows Task Scheduler setup for launch-at-login/startup.
  * Bind to `127.0.0.1` by default. Enable LAN access only through an explicit setting and Windows Firewall rule. For remote private access, document native Tailscale installation; do not deploy the app through Docker or Docker Compose.
  * Keep configuration in environment variables or Windows Credential Manager. Never store secrets in the repository or in the SQLite database in plaintext.

* **Application Updates (see Phase 8):** Distribute the app through the Inno Setup installer and keep it current with the in-app delta updater defined in Phase 8. Updates are fetched from GitHub releases only — never Docker or container registries — and must never touch user data.
* **SQLite Backups & Recovery:**
  * Use Python's `sqlite3.Connection.backup()` API or SQLite's supported online backup mechanism to create consistent snapshots while the application is running. Do not back up an active database by copying only the `.db` file while ignoring its `-wal` state.
  * Back up the SQLite database and the receipt-storage directory together on a schedule using Windows Task Scheduler. Optionally encrypt backup artifacts with `age` or `Restic` before copying them to an external disk or S3-compatible destination.
  * Provide restore-verification scripts that restore to a temporary path, run `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`, and verify accounting invariants before a backup is considered valid.

## Phase 3: Core Stack (Frontend)

1.       

2.      Use the following TypeScript Single-Page Application (SPA) stack and UI specifications to build the accounting application's frontend. Adhere strictly to the library choices and financial UX rules defined under each feature module below:

3.       

4.      ### 1. Core Framework, Build Tooling & Type Safety

5.      * **Framework & Bundler (`React 19` + `TypeScript 5+` + `Vite`):**

6.        * Enforce strict TypeScript configuration (`"strict": true`, `"noImplicitAny": true`) across all components, hooks, and utilities.

7.      * **End-to-End API Type Generation (`openapi-typescript` + `openapi-fetch`):**

8.        * Automatically generate TypeScript interfaces directly from the Python FastAPI `openapi.json` schema so backend Pydantic models and frontend types never drift out of sync.

9.      * **Exact Client-Side Decimal Math (`decimal.js`):**

10.    * Strictly forbid native JavaScript `number` arithmetic for monetary calculations.

11.    * Represent monetary values in API payloads as serialized strings (e.g., `"1250.5000"`) and parse them into `Decimal` instances on the client for all live form math and aggregations.

12.   

13.  ### 2. Routing, Server State & Client Store

14.  * **Type-Safe Routing (`TanStack Router`):**

15.    * Use URL search params as the single source of truth for ledger filters, date ranges, pagination cursors, and active report parameters using validated Zod/Valibot search schemas.

16.  * **Async Server State & Caching (`TanStack Query v5`):**

17.    * Manage all API fetching, optimistic updates (e.g., toggling transaction `Cleared` status), and automatic cache invalidation across Account Balances, Registers, and Reports when a new `JournalEntry` is posted.

18.  * **Local UI State (`Zustand`):**

19.    * Manage ephemeral workspace state such as open split-screen panes, active reconciliation sessions, sidebar collapse state, and keyboard shortcut modes.

20.   

21.  ### 3. Design System, Component Primitives & Financial Typography

22.  * **Styling & Accessible Primitives (`Tailwind CSS` + `shadcn/ui` / `Radix UI`):**

23.    * Build a high-density, keyboard-accessible component library (Dialogs, Popovers, Command Palettes, Date Range Pickers, Comboboxes) with full Dark/Light theme support.

24.  * **Tabular Financial Typography (`Vazirmatn` + `Intl.NumberFormat`):**

25.    * Apply `tabular-nums` to all numeric cells, badges, and financial statements for strict vertical decimal alignment.

26.    * Create a reusable `\<Money />` component that formats amounts with ISO 4217 currency symbols, color-codes inflows/outflows, and supports accounting parentheses `($1,234.56)` for negative balances.

27.   

28.  ### 4. High-Density Ledger & Virtualized Data Grids

29.  * **Headless Data Grid (`TanStack Table v8` + `TanStack Virtual`):**

30.    * Render high-performance account registers capable of smoothly scrolling through $50,000+$ transaction splits at $60\text{ FPS}$ using row virtualization.

31.    * Support column resizing, multi-column sorting, pinned summary footers (`Cleared Balance`, `Unreconciled Delta`, `Working Balance`), row selection, and inline cell editing.

32.   

33.  ### 5. Double-Entry Journal Entry & Multi-Split Form Engine

34.  * **Form State & Schema Validation (`React Hook Form` + `Zod` + `decimal.js`):**

35.    * Use `useFieldArray` for dynamic multi-split transaction rows (`Account`, `Memo`, `Debit`, `Credit`, `Currency`).

36.    * Enforce a custom `Zod` `.superRefine()` rule using `decimal.js` that blocks submission unless $\sum \text{Debits} - \sum \text{Credits} === 0$ and at least two split lines are populated.

37.  * **Smart Auto-Balance & Hierarchical Account Picker:**

38.    * Automatically populate the remaining unbalanced amount into the next empty Debit/Credit input when focused, and provide a fuzzy-searchable hierarchical Account combobox.

39.   

40.  ### 6. Keyboard-First Navigation & Command Palette

41.  * **Global Command Menu (`cmdk` + `react-hotkeys-hook`):**

42.    * Provide a `Cmd+K` / `Ctrl+K` command center to navigate to any account, trigger bank imports, switch report periods, or create transactions without touching the mouse.

43.    * Implement spreadsheet-style arrow-key and `Tab`/`Enter` cell traversal inside `TanStack Table` and multi-split forms.

44.   

45.  ### 7. Bank Import Wizard & Split-Screen Reconciliation UI

46.  * **Client-Side File Preview & Mapping (`PapaParse` + `react-dropzone`):**

47.    * Parse `.CSV` headers client-side for instant column mapping previews before uploading to the backend ingestion pipeline.

48.  * **Side-by-Side Reconciliation Workspace:**

49.    * Build a dual-pane reconciliation interface pairing imported bank statement rows with suggested ledger matches, complete with confidence badges, one-click match/create actions, and a live `Difference to Reconcile` progress header.

50.   

51.  ### 8. Interactive Financial Statements & Visualizations

52.  * **Hierarchical Tree Tables (`TanStack Table` Expanding Rows):**

53.    * Render Balance Sheet, Income Statement (P&L), Cash Flow, and Trial Balance reports as expandable account trees with click-to-drill-down drawers showing underlying journal entries.

54.  * **Financial Charts (`Apache ECharts` or `Recharts`):**

55.    * Render interactive Net Worth area charts, Income-to-Expense Sankey flows, Cash Flow waterfalls, and Monthly Budget burn-down gauges.

56.   

57.  ### 9. Receipt Split-Viewer & PDF Preview

58.  * **Document & Receipt Inspector (`react-pdf` + `react-zoom-pan-pinch`):**

59.    * Display uploaded receipt images/PDFs side-by-side with OCR-extracted form fields for rapid human-in-the-loop verification.

60.   

61.  ### 10. Frontend Testing & Quality Assurance

62.  * **Unit, Component & E2E Testing (`Vitest` + `React Testing Library` + `Playwright`):**

63.    * Test all client-side `decimal.js` balance calculations and Zod accounting validators with `Vitest`, and verify full end-to-end bookkeeping workflows with `Playwright`.&#x20;

64.  Audit for accessibility and responsive issues, then fix them.



## Phase 4: Core Stack (Database & Persistence Layer)

Use SQLite as the only relational database. Design the schema for the FastAPI + SQLAlchemy 2.0 backend and React + TypeScript SPA. Every query, constraint, migration, trigger, backup, and test must be compatible with SQLite; do not use server-database-specific features.

### 1. Database Engine, Storage Types & Identifier Strategy

* **SQLite configuration:** Use SQLite 3.45+ with `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA foreign_keys=ON;`, and `PRAGMA busy_timeout=5000;`. Apply connection settings consistently and verify them at startup. Prefer `STRICT` tables.
* **Database file:** Default to `%LOCALAPPDATA%\VIRA\data\vira.sqlite3` on Windows, configurable with `SQLITE_DATABASE_PATH`. Create the parent directory securely and never commit the database, WAL/SHM files, backups, or customer attachments to Git.
* **SQLite type rules:** In `STRICT` tables use SQLite-supported storage types. Store identifiers as `TEXT` UUID strings, dates as ISO `YYYY-MM-DD` `TEXT`, timestamps as UTC ISO-8601 `TEXT`, JSON documents as validated JSON-serialized `TEXT`, and booleans as `INTEGER` values constrained to `0` or `1`. Use explicit `CHECK`, `UNIQUE`, and foreign-key constraints where supported.
* **Exact money storage:** SQLite does not enforce fixed-precision `NUMERIC(19,4)` semantics. Store all money amounts as scaled integers: `stored_amount = Decimal_amount × 10,000`, with four decimal places of precision. Store exchange rates as scaled integers using a factor of `100,000,000`. Provide central SQLAlchemy `TypeDecorator`/conversion helpers that expose Python `Decimal` values to services while persisting integers. Never use `REAL`, `float`, or JavaScript `number` for financial calculations. Validate quantization and overflow before writes and check that aggregate totals stay within SQLite's signed 64-bit integer range.
* **IDs and time:** Generate UUIDv7 IDs in the application and store them as canonical `TEXT`. Store timestamps as UTC ISO-8601 strings and keep a separate accounting `transaction_date` as ISO `YYYY-MM-DD`; calendar localization is a presentation concern.

### 2. SQLAlchemy, SQLite Driver & Migrations

* **ORM/driver:** Use SQLAlchemy 2.0 typed models (`Mapped`, `mapped_column`) with `aiosqlite` for the async FastAPI backend, or use synchronous `sqlite3`/SQLAlchemy consistently if that simplifies reliability. Do not mix sync and async session patterns within the same service.
* **SQLite concurrency:** SQLite permits one writer at a time. Keep write transactions short, use `BEGIN IMMEDIATE` where appropriate for ledger mutations, configure a busy timeout, and handle transient `database is locked` failures with bounded retries. Do not assume PostgreSQL-style row-level locking or advisory locks; design around SQLite's single-writer model.
* **Migrations:** Use Alembic migrations for all schema changes. Test migrations on temporary SQLite database files. Account for SQLite table-rebuild requirements when changing constraints or column definitions; migration scripts must preserve indexes, triggers, data, and foreign keys. Use SQLite-supported DDL and Alembic batch migrations where table rebuilds are required.
* **Deterministic naming:** Define stable naming conventions for indexes (`ix_`), unique constraints (`uq_`), check constraints (`ck_`), and foreign keys (`fk_`).

### 3. Core Double-Entry Ledger Schema & Hierarchical Accounts

* **`accounts`:** Include `id` (`TEXT`, UUIDv7), `code` (`TEXT`, unique), `name` (`TEXT`), `account_type` (`TEXT` with a `CHECK` restricting values to `ASSET`, `LIABILITY`, `EQUITY`, `INCOME`, `EXPENSE`), `normal_balance` (`TEXT` with a `CHECK` for `DEBIT`/`CREDIT`), `currency` (`TEXT`, ISO 4217), `parent_id` (self-referencing foreign key), `path` (materialized path string such as `1000.1010`), `is_placeholder` and `is_active` (`INTEGER` constrained to `0`/`1`), and `version_id` (`INTEGER`). Prevent posting splits to placeholder accounts.
* **`journal_entries`:** Include `id` (`TEXT`), unique sequential `entry_number`, `transaction_date` (`TEXT`, `YYYY-MM-DD`), `posted_at` (UTC ISO-8601 `TEXT`), `payee` (`TEXT`), `description` (`TEXT`), `status` (`TEXT` constrained to `DRAFT`, `POSTED`, `VOIDED`), `reversed_entry_id` (self-referencing foreign key), `metadata_json` (validated JSON in `TEXT`), and `version_id` (`INTEGER`).
* **`transaction_splits`:** Include `id` (`TEXT`), `journal_entry_id` and `account_id` (foreign keys using `ON DELETE RESTRICT`), `memo` (`TEXT`), `debit` and `credit` (`INTEGER` scaled by 10,000, default `0`), `currency` (`TEXT`), `exchange_rate` (`INTEGER` scaled by 100,000,000, default `100000000`), `functional_debit` and `functional_credit` (`INTEGER` scaled by 10,000), and `reconciliation_status` (`TEXT` constrained to `UNRECONCILED`, `CLEARED`, `RECONCILED`). Use the same scale consistently in every backend calculation, SQL aggregate, test, and API conversion.

### 4. Row Integrity & Double-Entry Posting Validation

* **Row-level constraints:** Add a SQLite `CHECK` constraint ensuring stored debit and credit integers are non-negative, at most one side is positive, and exactly one side is positive for an active split: `CHECK (debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0) AND (debit > 0 OR credit > 0))`. If drafts need empty split rows, keep those rows only in frontend state and persist only valid split lines.
* **Posting validation:** SQLite does not support PostgreSQL-style `DEFERRABLE INITIALLY DEFERRED` constraint triggers. Before changing an entry from `DRAFT` to `POSTED`, a single ledger service must validate inside one database write transaction that at least two valid split rows exist and that exact integer-scaled functional debits equal credits. Use a SQLite `BEFORE UPDATE OF status` trigger as a secondary guard if practical, but keep the service-level validation authoritative and atomic.
* **Atomic operations:** Insert/update split lines, verify all invariants, update status, and commit within one transaction. On any failure, roll back every change. Do not allow a partially written or unbalanced posted entry. Test concurrent posting attempts and integer overflow.

### 5. Immutable Entries, Fiscal Period Locks & Audit Trail

* **`fiscal_periods`:** Store `start_date`, `end_date`, `is_closed`, and `closed_at`. Add SQLite-compatible triggers or centralized service checks to reject writes to journal entries/splits that belong to closed periods. For split triggers, join to the parent `journal_entries` row to find the accounting date.
* **Reconciled/posted data:** Reject deletion or amount/account changes to reconciled splits and posted entries through service checks and SQLite triggers where row-level checks suffice. Corrections must create a reversing `JournalEntry` linked through `reversed_entry_id`; never silently overwrite ledger history.
* **`audit_logs`:** Include `id`, `table_name`, `record_id`, `action`, `old_data` and `new_data` (JSON serialized as `TEXT`), `changed_at` (UTC ISO-8601 `TEXT`), and `actor_id`. Populate logs through SQLAlchemy session events and/or SQLite triggers. Redact secrets, tokens, and sensitive authentication values. Prevent ordinary users and code paths from updating/deleting audit history.

### 6. Multi-Currency, FX History & Cost Basis

* **`exchange_rates`:** Store `base_currency`, `quote_currency`, `rate_date` (`YYYY-MM-DD` text), `rate` (integer scaled by 100,000,000), and `source`, with `UNIQUE (base_currency, quote_currency, rate_date)`.
* **Dual amounts:** Store original-currency debit/credit and functional-currency equivalents as scaled integers. Convert rates and amounts using `Decimal` in the application layer and a documented rounding policy; persist the resulting exact scaled integer amounts so historical reports are deterministic.
* **Currency validation:** Every entry and split must carry explicit currency codes. Prevent cross-currency arithmetic unless an explicit rate and conversion path are provided.

### 7. Bank Import Idempotency & Reconciliation Tables

* **`bank_import_batches` and `bank_statement_lines`:** Store raw imported bank rows separately until matched or categorized. Enforce de-duplication with unique keys such as `UNIQUE (account_id, external_fitid)` and a fallback SHA-256 `dedup_hash` for CSV imports.
* **`reconciliation_sessions`:** Store account, statement date, beginning/ending balances (scaled integers), status, and completion timestamp. Link reconciled splits to the session and preserve history for auditability.
* **Import safety:** Validate file format, normalize dates and payee descriptions, and commit each import batch atomically. Repeated uploads must not create duplicate journal entries.

### 8. SQLite Indexing, Search & Rollups

* **Indexes and pagination:** Create B-tree indexes on `transaction_splits (account_id, journal_entry_id)` and `journal_entries (transaction_date DESC, id DESC)`. Use keyset/cursor pagination with stable tie-breakers and avoid unbounded `OFFSET` queries for large registers.
* **Search:** Use parameterized SQLite `LIKE` queries for simple field matching and SQLite FTS5 for indexed full-text search when the installed SQLite build supports it. Keep a tested `LIKE` fallback. Use `RapidFuzz` in the application layer for fuzzy matching of candidate results; do not require `pg_trgm`, GIN indexes, `ILIKE`, or an external search server.
* **Balance rollups:** Create SQLite views where useful and a monthly `account_balance_snapshots` table for expensive reports. Sum scaled integers only within known safe bounds, convert to `Decimal` at the service boundary, and test that reports reconcile with the underlying splits. Performance goals must be benchmarked on representative local data rather than assumed.

### 9. Concurrency Control & API Mutation Idempotency

* **Optimistic concurrency:** Use SQLAlchemy `version_id_col` for `journal_entries` and `accounts`. Require the client to send the current `version_id` on updates and return HTTP `409 Conflict` when the stored version differs.
* **`idempotency_keys`:** Store `key` (unique `TEXT` UUID), `request_hash`, `response_status`, `response_body` (JSON serialized `TEXT`), `created_at`, and `expires_at`. Use an atomic transaction to check/claim the key and persist the resulting response so retries cannot create duplicate entries.
* **SQLite write serialization:** Design API writes with SQLite's single-writer model in mind. Keep transactions short and never use unsupported advisory-lock patterns.

### 10. Seeding, Testing & Backup Strategy

* **Seed data:** Provide idempotent Python seed scripts for personal-finance and small-business charts of accounts, supported currencies, and opening-balance equity accounts. Seed scripts must be safe to run more than once.
* **Tests:** Use `pytest`, `pytest-asyncio` if needed, and `Hypothesis` against temporary on-disk SQLite databases. Test actual `CHECK` constraints, foreign keys, trigger protections, migration upgrades, integer-scaled decimal conversions, import idempotency, locking behavior, and double-entry invariants.
* **Backups:** Use SQLite's online backup API to generate a consistent snapshot, then encrypt and copy the snapshot plus receipt storage. Automate with Windows Task Scheduler. Restore into a temporary location and verify `PRAGMA integrity_check;`, `PRAGMA foreign_key_check;`, migration version, and ledger debit/credit equality before declaring recovery successful.

## Phase 5: Core Stack (Integration, Auth & Security)



Use the following full-stack integration patterns, authentication workflows, and defense-in-depth security specifications to connect the React + TypeScript (`TanStack`) SPA, the Python (`FastAPI`) backend, the database layer, and external financial APIs. Adhere strictly to the rules defined under each module below:



### 1. Authentication & Session Management (SPA $\leftrightarrow$ FastAPI)

* **Password Hashing (`pwdlib` with `Argon2id`):**

  * Hash all user passwords using `Argon2id` with OWASP-recommended memory, iteration, and parallelism parameters. Never store plaintext or reversible passwords.

* **Stateful HttpOnly Session Cookies or Rotating Token Auth (`FastAPI` + `Authlib`):**

  * Issue short-lived access sessions stored in `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict`) cookies so authentication tokens are completely inaccessible to browser JavaScript (`XSS`-immune).

  * Support automatic silent session refresh in the `openapi-fetch` client interceptor; if a refresh fails with `401 Unauthorized`, cleanly snapshot unsaved form drafts in memory and redirect via `TanStack Router` to `/login`.

* **Multi-Factor Authentication (`pyotp` + `qrcode` + Recovery Codes):**

  * Implement RFC 6238 TOTP Two-Factor Authentication with QR code provisioning during setup.

  * Generate 10 single-use backup recovery codes at MFA enrollment, display them once to the user, and store only their `Argon2id` hashes in the database.



### 2. Authorization, Scopes & Step-Up (`Sudo`) Re-Authentication

* **Role & Scope Enforcement (FastAPI Dependency Injection):**

  * Enforce role-based access scopes on every route via FastAPI `Depends()` guards:

    * `owner`: Full administrative, ledger, and configuration access.

    * `bookkeeper`: Create/edit journal entries, import bank statements, and reconcile accounts; cannot unlock closed fiscal periods or delete accounts.

    * `auditor` (`read-only`): View ledgers, financial statements, audit logs, and receipts; blocked from all `POST`/`PUT`/`PATCH`/`DELETE` mutations.

    * `ingest_api`: Scoped API key restricted strictly to posting draft transactions or uploading receipts from mobile shortcuts/CLI scripts.

* **Step-Up Authentication (`Sudo Mode`) for High-Risk Actions:**

  * Require explicit password or TOTP re-verification (granting a 5-minute elevated `sudo` token) before executing sensitive actions:

    1. Re-opening a closed `FiscalPeriod`.

    2. Voiding or un-reconciling a previously completed `ReconciliationSession`.

    3. Exporting full unencrypted database dumps or ledger archives.

    4. Adding, viewing, or revoking Open Banking API credentials or API keys.



### 3. Type-Safe Frontend–Backend Contract & Error Protocol

* **Automated OpenAPI Contract Generation (`openapi-typescript` + `openapi-fetch`):**

  * Expose a strict OpenAPI 3.1 schema from FastAPI and auto-generate TypeScript types (`schema.d.ts`) so every request payload, query parameter, and response body in `TanStack Query` is compile-time checked.

* **Strict Financial Serialization Contract:**

  * Serialize all monetary `Decimal` values across JSON APIs as exact fixed-scale strings (e.g., `"1250.5000"`), currency codes as ISO 4217 strings (`"USD"`), dates as ISO 8601 (`"YYYY-MM-DD"`), timestamps as UTC (`"YYYY-MM-DDTHH:MM:SSZ"`), and IDs as `UUIDv7` strings.

* **Standardized Error Responses (`RFC 9457 Problem Details`):**

  * Return all API and database errors in a consistent `application/problem+json` structure (`type`, `title`, `status`, `detail`, `instance`, `errors[]`).

  * Map backend accounting errors (e.g., `UnbalancedJournalEntryError`, `ClosedFiscalPeriodError`, `DuplicateBankImportError`) to deterministic error codes so `React Hook Form` and `TanStack Query` can highlight specific split rows or display actionable toast messages.



### 4. End-to-End Idempotency & Optimistic Concurrency Control

* **Mutation Idempotency (`Idempotency-Key` Header):**

  * Generate a unique UUID `Idempotency-Key` header in the React API client for every `POST` and `PATCH` mutation (journal creation, bank import commit, reconciliation finish).

  * Implement a FastAPI idempotency middleware backed by the `idempotency_keys` table that caches responses for 24 hours, ensuring network retries or double-clicks never create duplicate ledger entries.

* **Optimistic Locking (`ETag` / `version_id`):**

  * Include the record's current `version_id` in all `JournalEntry` and `Account` update payloads.

  * If a concurrent modification occurred, reject the request with HTTP `409 Conflict` and prompt the user in the React UI to diff and refresh the row rather than silently overwriting ledger history.



### 5. Encryption at Rest & Secret Management

* **Field-Level Envelope Encryption (`cryptography` AES-256-GCM / `Fernet`):**

  * Encrypt sensitive third-party credentials and PII at the application layer before writing to the database:

    * Open Banking access/refresh tokens (`GoCardless`, `Plaid`, `SimpleFIN`).

    * External webhook signing secrets and LLM/OCR API keys.

    * Full IBANs, bank routing/account numbers, and tax identification numbers.

  * Support key rotation via `MultiFernet` using a primary master key (`APP_ENCRYPTION_KEY`) loaded exclusively from environment variables or Windows Credential Manager.

* **Validated Runtime Configuration (`pydantic-settings`):**

  * Validate all environment variables, database URLs, encryption keys, and CORS origins at FastAPI startup; refuse to boot if production secrets are missing, default, or weak.



### 6. External Banking, FX & Webhook Integration Security

* **Resilient Outbound API Clients (`httpx.AsyncClient` + `tenacity`):**

  * Wrap all external calls (`GoCardless`, `Plaid`, `SimpleFIN`, `Frankfurter FX API`, and optional Vision LLM endpoints) in dedicated async service adapters with strict connection/read timeouts, exponential backoff with jitter (`tenacity`), and rate-limit respect (`Retry-After`).

* **Webhook Signature Verification & Replay Protection:**

  * Verify cryptographic signatures (`HMAC-SHA256` or `JWS`) on all incoming bank sync webhooks using constant-time comparison (`hmac.compare_digest`).

  * Reject webhook payloads with timestamps older than 5 minutes to prevent replay attacks, and deduplicate webhook `event_id` values before queuing background ingestion jobs.

* **Privacy-Preserving Receipt OCR Integration:**

  * Default to local OCR execution (`PaddleOCR` / `Tesseract`). If an external Vision LLM is enabled by the user, provide an explicit opt-in toggle and strip unrelated metadata before transmission.



### 7. Secure File Upload & Receipt Storage Pipeline

* **Strict File Inspection & Sanitization (`python-magic` + `Pillow`):**

  * Validate uploaded bank statements (`.csv`, `.ofx`, `.qfx`, `.mt940`, `.xlsx`) and receipts (`.pdf`, `.png`, `.jpg`, `.webp`) by inspecting file magic bytes—never trust the browser `Content-Type` or file extension alone.

  * Enforce strict maximum upload sizes (e.g., `10 MB` per receipt, `25 MB` per statement), strip EXIF GPS/camera metadata from uploaded receipt images using `Pillow`, and scan/sanitize CSV cell values starting with `=`, `+`, `-`, or `@` to prevent CSV Formula Injection during exports.

* **Isolated Content-Addressable Storage & Authenticated Delivery:**

  * Store uploaded files outside the public static web root, renamed by their `SHA-256` content digest.

  * Serve receipt previews to the React `\<ReceiptViewer />` exclusively through an authenticated FastAPI streaming endpoint (or short-lived signed URLs) with `X-Content-Type-Options: nosniff` and a restrictive `Content-Security-Policy: sandbox` header.



### 8. Transport Security, CSRF, CORS & Rate Limiting

* **Cross-Origin & CSRF Protection (`CORSMiddleware` + Double-Submit / Custom Header):**

  * Restrict `CORSMiddleware` strictly to the configured frontend origin (`FRONTEND_ORIGIN`) with `allow_credentials=True` and explicit allowed methods/headers (never wildcard `*` in production).

  * Enforce CSRF validation on all state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`) using an `X-CSRF-Token` header synchronized with a signed cookie.

* **Hardened HTTP Security Headers:**

  * Inject security headers via middleware or reverse proxy: `Strict-Transport-Security` (HSTS), `Content-Security-Policy` (CSP), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: same-origin`.

* **Endpoint Rate Limiting (`slowapi` / Token Bucket):**

  * Apply strict IP and account-based rate limits on `/api/v1/auth/login` (e.g., 5 attempts/minute with exponential lockout), `/api/v1/auth/totp`, `/api/v1/imports/upload`, and `/api/v1/ocr/extract`.



### 9. Security Audit Logging & Sensitive Data Redaction

* **Immutable Security & Access Log (`security_audit_logs`):**

  * Record all security-critical events (`LOGIN_SUCCESS`, `LOGIN_FAILED`, `MFA_CHALLENGE_FAILED`, `SUDO_ELEVATION`, `PERIOD_UNLOCKED`, `BACKUP_EXPORTED`, `API_KEY_CREATED`) with UTC timestamp, actor ID, IP address, and User-Agent.

* **Structured Log Redaction (`structlog`):**

  * Configure a mandatory `structlog` processor pipeline that automatically scrubs `password`, `token`, `authorization`, `cookie`, `secret`, `iban`, and `account_number` fields from all application logs and exception tracebacks.



### 10. Native Windows Runtime, Network Security & Verification (No Docker)

* **Least-privilege native processes:** Run FastAPI and the built React SPA as ordinary Windows processes or optional Windows services, under a dedicated low-privilege account where practical. Do not package or launch them in containers.
* **SQLite isolation:** Keep the database file and receipt storage under the configured application-data directory with Windows filesystem ACLs that allow access only to the intended user/service. Never expose the SQLite file directly over a network share; remote clients must access data only through the authenticated API.
* **Private access:** Bind to `127.0.0.1` by default. LAN binding must be explicit and paired with a narrow Windows Firewall rule. For access from other devices, document native Tailscale use; optional reverse proxies must be installed and run directly on the host.
* **Automated security verification (`pytest` + `Playwright` + `Bandit`):** Test that unauthenticated or `auditor`-scoped requests cannot mutate ledger entries (`401`/`403`), idempotent retries do not create duplicates, stale `version_id` updates return `409`, locked periods reject mutations, and backups can be restored. Run `Bandit`, `pip-audit`, and `npm audit`; investigate and resolve high-severity findings.

## Phase 6: Core Stack (Deployment & DevOps — GitHub Web Workflow, Windows-Native)

Use GitHub's Web interface for repository editing and code review, and GitHub Actions for automated tests/builds. The application must run directly on Windows. Do not use Docker, Docker Compose, Dev Containers, container images, or container-based deployment workflows.

### 1. Monorepo Structure & GitHub Web Hygiene

* Keep a clear, shallow repository structure:
  * `/backend` — FastAPI, SQLAlchemy, Alembic, and Python modules.
  * `/frontend` — React, TypeScript, Vite, and TanStack modules.
  * `/scripts` — native PowerShell (`.ps1`) and Windows batch (`.bat`) setup, launch, migration, backup, restore, and health-check scripts.
  * `/.github/workflows` — test, build, dependency, and release workflows.
  * Do not create `/deploy` Dockerfiles, `docker-compose.yml`, or `/.devcontainer` configuration.
* Configure `.gitattributes` with consistent line endings and a `.gitignore` that excludes `.env`, `*.sqlite`, `*.sqlite3`, `*.db`, `*-wal`, `*-shm`, backups, encryption keys, receipt uploads, Python virtual environments, `node_modules`, and build output.
* Keep `uv.lock` and `pnpm-lock.yaml` synchronized with `pyproject.toml` and `package.json`. GitHub Actions should detect stale lockfiles and fail clearly or create a dependency-sync pull request; do not rely on an unreviewed bot commit to rewrite application source.

### 2. OpenAPI Type Generation & Web-First Workflow

* Generate TypeScript API types from FastAPI's OpenAPI schema using `openapi-typescript` and `openapi-fetch`.
* Add a `pnpm openapi-ts` script. CI should start FastAPI with a temporary SQLite database, obtain `openapi.json`, generate `schema.d.ts`, and run `tsc --noEmit` before building the frontend.
* Keep schema and generated-type changes reviewable in GitHub Web. Provide documented GitHub Actions steps for generating an Alembic migration, but require review and tests before applying schema changes to user data.

### 3. Native Windows Development Environment

* Document supported versions of Python 3.12, `uv`, Node.js 22, and `pnpm`; install them directly on Windows using standard installers or package managers.
* Provide a `setup_windows.ps1` script that creates the Python virtual environment, installs backend dependencies, installs frontend dependencies, prepares the application-data directories, validates SQLite availability, and runs Alembic migrations.
* Provide `start_vira.bat` / `start_vira.ps1` and `stop_vira.bat` / `stop_vira.ps1`. The launch script should start the backend and either serve the built frontend through FastAPI or start Vite for development. Show clear logs and surface startup failures.
* Use `%LOCALAPPDATA%\VIRA\data\vira.sqlite3` as the default database location. Keep the file, backups, encryption keys, and uploaded receipts outside the repository.
* Document an optional Windows Task Scheduler configuration for startup/login launch and scheduled backups. If installing as a Windows service, use a maintained service wrapper and least-privilege account; do not add container-based services.

### 4. Reproducible Native Builds

* **Backend:** Install dependencies through `uv sync` into a local Python virtual environment. Document any native Windows prerequisites for `WeasyPrint`, OCR libraries, or file-type inspection. If a dependency is unsupported on Windows, choose and document a compatible alternative instead of requiring a Linux container.
* **Frontend:** Use Node.js 22 and `pnpm install --frozen-lockfile`, generate API types from the FastAPI schema, run `pnpm lint`, `pnpm typecheck`, and `pnpm build`.
* **Distribution artifacts:** Build the `vira-updater.exe` helper and compile the Inno Setup installer (Phase 8) in CI; the installed app must run self-contained on Windows without requiring separate Python or Node.js installations.
* **Local serving:** Serve the compiled React assets through FastAPI or a separately installed native static-file server. Keep API and frontend on the same origin where practical; document CORS/CSRF settings when origins differ.
* Never build or publish Docker images, and do not require a container registry.

### 5. GitHub Actions CI for SQLite

* Run workflows on GitHub-hosted Windows or Ubuntu runners using installed Python and Node.js toolchains—without service containers.
* Trigger CI on pushes and pull requests. Steps must include:
  1. Python formatting/lint/type/security checks (`ruff`, `mypy`, `bandit`, `pip-audit`).
  2. Frontend formatting/lint/type checks (`prettier`, `eslint`, `tsc --noEmit`) and `npm audit`/equivalent.
  3. Create a fresh temporary SQLite database, apply `alembic upgrade head`, and run `pytest` plus `Hypothesis` financial invariant tests.
  4. Build the React production assets and run Playwright end-to-end tests against the native processes launched by CI.
  5. Upload test reports and build artifacts to the GitHub Actions run; do not publish container images.
* Configure Dependabot for `pip`/`uv`, `npm`/`pnpm`, and `github-actions` only. Do not configure container-image dependency updates.

### 6. Secrets & Native Deployment Workflow

* Store production secrets in Windows Credential Manager or in restricted environment configuration outside the repository. GitHub Actions secrets may be used only for CI or a deliberately configured deployment workflow; never commit secret values.
* Provide a release workflow that runs tests, builds the frontend, packages source/build artifacts, compiles the Inno Setup installer (Phase 8), generates delta update packages against the previous release tags, uploads the full setup as a GitHub Actions workflow artifact, and publishes a versioned GitHub Release — created from an annotated `vX.Y.Z` git tag — carrying the installer, delta packages, `latest.json`, `SHA256SUMS`, and Persian release notes. Deployment to the target Windows machine should be a reviewed, explicit step using the release artifact or a secured self-hosted GitHub Actions runner.
* Do not use automatic unreviewed production schema migrations. Before applying Alembic migrations, create and verify a SQLite online backup. Apply the migration, run a health check and accounting-invariant check, then mark deployment successful. If migration fails, stop the service and follow a documented tested restore procedure.
* If a self-hosted runner is used, restrict repository and environment permissions, protect production environments, and never expose the runner to untrusted pull-request code.

### 7. Safe SQLite Migration Lifecycle

* Before each production migration, use `sqlite3.Connection.backup()` to create a consistent backup outside the database directory and verify that the snapshot passes `PRAGMA integrity_check;`.
* Run `alembic upgrade head` against the configured SQLite file with a single migration process. SQLite has no PostgreSQL advisory lock; use a local lock file or Windows named mutex to prevent two app instances from applying migrations simultaneously.
* Run `PRAGMA foreign_key_check;`, verify the expected Alembic revision, and check the ledger's debit/credit invariants before enabling normal traffic. Account for SQLite table rebuilds in migrations and keep a tested downgrade/restore path.

### 8. Scheduled Encrypted Backups & In-App Management

* Use Windows Task Scheduler to run daily SQLite online backups and copy the receipt-storage directory. Encrypt completed snapshots with `age` or `Restic`; upload to an external or S3-compatible destination only if configured.
* Provide a `Sudo`-protected System & Operations area in the React UI showing the app version/Git commit, schema migration revision, last backup status/time/size, a one-click encrypted-snapshot download, and a «بررسی به‌روزرسانی» (Check for updates) action with current/latest version status, driven by the Phase 8 update system.
* Offer a restore-verification operation that restores to a temporary location, runs SQLite integrity and foreign-key checks, and verifies `sum(debits) = sum(credits)` before reporting the backup healthy.

### 9. Health Checks, Logging & Private Access

* Provide `/api/v1/health/live` and `/api/v1/health/ready`. Check database connectivity, Alembic revision, writable receipt storage, and scheduler status. Surface errors in logs and the native process supervisor rather than Docker healthchecks.
* Log rotation and crash recovery must be configured for the native Windows process or service. Do not log secrets or financial PII.
* Default to loopback access. Document explicit Windows Firewall rules and native Tailscale setup for private remote access; do not expose SQLite files or unnecessary ports publicly.

## Phase 7: Enhancements & Localization Stack



Implement the following enhancement modules on top of the Core Stack (FastAPI + SQLAlchemy 2.0 + SQLite + React/TypeScript + TanStack). SQLite is the only database engine; use SQLite-compatible SQL and keep monetary storage exact.



### 1. SQLite-Native Ledger Search (FTS5 + Parameterized Queries)

* **No external search engine:** Do not introduce Elasticsearch, Meilisearch, Typesense, third-party database extensions, or a separate search server. SQLite FTS5 may be used when it is compiled into the installed SQLite build.
* Power the `TanStack Table` filter bar and `Ctrl+K` command palette through parameterized SQLAlchemy queries using SQLite `LIKE` and SQLite FTS5 for indexed full-text search when available. Maintain a tested `LIKE` fallback for environments where FTS5 is unavailable.
* Support unified search across `journal_entries.payee`, `journal_entries.description`, `journal_entries.entry_number`, `transaction_splits.memo`, and `accounts.code` / `accounts.name`.
* Parse numeric search tokens with Python `Decimal` and compare them to integer-scaled debit/credit values using the shared monetary conversion utility. Never compare monetary values using floating-point conversions. Use `RapidFuzz` for optional fuzzy matching over a bounded set of SQLite search candidates.

### 2. Receipt & Statement Upload Pipeline (`FastAPI UploadFile` $\rightarrow$ Local / S3 Storage)

* **Multipart Upload Handling (`FastAPI UploadFile` + `python-multipart`):**

  * Replace Node-style middleware with a dedicated FastAPI multipart upload service supporting both drag-and-drop receipt attachments (`.pdf`, `.png`, `.jpg`, `.webp`) from `react-dropzone` and bank statement files (`.csv`, `.xlsx`, `.ofx`, `.qfx`, `.mt940`).

* **Validation, Sanitization & Content-Addressable Hashing (`python-magic` + `Pillow`):**

  * Verify true MIME types via file magic bytes (`python-magic`), enforce size caps (`10 MB` receipts / `25 MB` statements), strip EXIF GPS/camera metadata from images using `Pillow`, and compute a `SHA-256` content digest to deduplicate identical uploads automatically.

* **Pluggable Storage Backend (local Windows filesystem or S3-compatible storage via `boto3`):**

  * Implement a clean `StorageBackend` protocol switched via `STORAGE_PROVIDER=local|s3` in `pydantic-settings`:

    * `local`: Store files under `%LOCALAPPDATA%\VIRA\receipt_storage` (or the configured application-data directory), partitioned by hash prefix (`ab/cd/<sha256>.pdf`). Keep the directory outside the repository and apply restrictive Windows file permissions.

    * `s3`: Stores files in any S3-compatible bucket (`MinIO`, `Cloudflare R2`, `Backblaze B2`, `AWS S3`) using `boto3` with server-side encryption and authenticated streaming/presigned delivery to the React `\<ReceiptViewer />`.



### 3. Persian-Only Accounting UI, RTL Support & Jalali Calendar



* **Persian-Only Interface & Native RTL Layout (`react-i18next` + Tailwind Logical Properties):**

  * Build a strictly Persian-only (`fa-IR`) accounting application. Configure `react-i18next` with namespace-split Persian translation JSON files (`/locales/fa/{common,ledger,reports,validation}.json`). Do not create English translations, language-switching controls, or multilingual infrastructure.

  * Set `\<html lang="fa" dir="rtl">` permanently across the entire application. Use Tailwind CSS logical utilities (`ms-*`, `me-*`, `ps-*`, `pe-*`, `border-s`, `text-start`, `text-end`) consistently across all `shadcn/ui` components, sidebars, `TanStack Table` grids, forms, dialogs, dashboards, and split-screen reconciliation panes. Ensure every component follows natural Persian reading order without requiring CSS overrides or manual per-component RTL patches.

  * All application UI text, navigation labels, buttons, tooltips, validation errors, notifications, empty states, reports, and user-facing messages must be written in Persian. Use natural, professional Persian terminology appropriate for accounting and financial management.



* **Persian Typography & Strict Accounting Directionality (`Vazirmatn` for text and all numbers):**

  * User amendment (2026-10-17): use `Vazirmatn` for **all displayed numbers** as well as text, including inputs, tables, dates, charts/tooltips, technical values and print/PDF. Keep values/calculations/numeral semantics unchanged; retain tabular numbers and isolated LTR.

  * Use `Vazirmatn` as the primary application font, with proper Persian glyph rendering, readable typography, and support for Persian characters and numerals. Use `tabular-nums` where appropriate for aligned financial figures.

  * Default to Persian numerals (`۰۱۲۳۴۵۶۷۸۹`) throughout the user interface, forms, date pickers, tables, dashboards, and Persian financial reports. Do not provide a language or numeral-system toggle.

  * Render monetary amounts, arithmetic expressions, account codes (e.g., `1010`), decimal values, transaction identifiers, and negative accounting figures using isolated left-to-right formatting (`dir="ltr"` and `unicode-bidi: isolate`) wherever necessary to prevent incorrect digit ordering, misplaced minus signs, or inverted decimal separators in RTL contexts.

  * Preserve correct numeric values and machine-readable formats internally. Apply Persian numeral formatting only at the presentation layer when appropriate, ensuring reliable sorting, arithmetic, validation, copy/paste, and data export.



* **Persian Solar Hijri Fiscal Calendar (`date-fns-jalali`):**

  * Calendar policy revised by the user on 2026-10-16: use Solar Hijri / Jalali as the default calendar with Persian locale (`fa-IR`), and provide a persistent Settings → Date & calendar → Jalali / Gregorian selector. This replaces the earlier Jalali-only restriction; it does not introduce a language or numeral-system switch. Order and new-journal-entry forms must accept the selected calendar, with consistent related lists, date filters and shared formatters.

  * Use `date-fns-jalali` for Jalali input/conversion/formatting in React. Derive today and display timestamp instants using the IANA zone `Asia/Tehran`, not the browser/server timezone or the UTC day from `toISOString().slice(0, 10)`. Switching calendars must preserve the actual selected day and existing records; test Tehran-midnight boundaries and Persian/Latin input digits.

  * Store all database `transaction_date` values using a canonical, unambiguous date representation: Gregorian ISO 8601 (`YYYY-MM-DD`) for date-only values, without converting their midnight through UTC, or UTC timestamps for actual instants. Convert at the input/display boundaries according to the selected calendar; do not rewrite historical dates or shift a date-only day because of timezone conversion.

  * Use `jdatetime` and `Babel` where needed in FastAPI and `WeasyPrint` PDF generation to ensure consistent calendar-aware date formatting across the frontend, backend, printed documents, and exported financial statements (Jalali by default).

  * Support Iranian fiscal years beginning on `1 Farvardin` regardless of the display-calendar preference, and ensure accurate Jalali leap-year handling, date-range calculations, period comparisons, and year-end accounting operations.



* **Iranian Currency Handling (`IRR` Rial & IRT Toman):**

  * Implement a centralized `\<Money />` component using `decimal.js` for precise monetary calculations and consistent formatting throughout the application.

  * Support Iranian Rial (`IRR`) and Toman (`IRT`) as configurable display and transaction-entry units, with an explicitly defined conversion rule of `1 Toman = 10 Rials`. Never apply currency conversion implicitly or more than once.

  * Define the canonical currency and amount representation in the database and document whether amounts are stored in Rial or Toman. Keep calculations, journal entries, ledger balances, reconciliation, taxes, and financial reports consistent with that representation.

  * Default the user interface to Toman (`تومان`) unless a specific accounting or integration requirement mandates Rial. Display all monetary values with Persian numerals, appropriate Persian separators, correct negative-number formatting, and clear currency labels.

  * Preserve exact monetary precision during calculations and conversions. Avoid floating-point arithmetic for financial operations, and ensure reliable rounding, validation, database persistence, and report generation.

### 5. Privacy-First Product Analytics (`Umami` Integration)

* **Lightweight SPA Integration (`Umami` + `TanStack Router`):**

  * Inject the `Umami` tracker script dynamically only when `VITE_UMAMI_WEBSITE_ID` and `VITE_UMAMI_SCRIPT_URL` are present in the environment (with an optional separately installed Umami instance outside the application runtime).

  * Bind a typed `useAnalytics()` hook to `TanStack Router` navigation events and key bookkeeping workflows (`journal_entry_created`, `bank_statement_imported`, `reconciliation_completed`, `report_viewed`).

* **Strict Financial Zero-PII Redaction Guard:**

  * Enforce a client-side sanitization wrapper around `window\.umami.track()` that strips URL query parameters (`?search=...`, `?amount=...`), masks UUIDs in route paths (`/accounts/:id` instead of the raw UUID), and strictly forbids transmitting monetary figures, account names, payee descriptions, or receipt filenames in analytics payloads.


## Phase 8: Installer, Versioned Releases & In-App Delta Updates (Windows-Native)

Deliver V.I.R.A as a distributable Windows product: an **Inno Setup** installer published from GitHub, strict **version tagging** for every release, and a safe **in-app update system** that downloads only the parts that changed and never loses user data. All mandatory architecture constraints still apply (SQLite-only, no Docker, user data outside the install directory). This phase completes the 8-phase plan promised above.

### 1. Windows Installer (`Inno Setup 6`)

* **Installer build:** Compile a native Windows installer with **Inno Setup 6** (`iscc`) inside GitHub Actions. *(Implemented in Phase 8: `installer/vira.iss`, compiled in `release.yml` via `choco install innosetup` + `iscc`.)* The full setup (`VIRA-Setup-vX.Y.Z.exe`) must be published **both** as a GitHub Actions workflow artifact on the release run **and** as an immutable GitHub Release asset (the durable download used by end users and the updater's full-install fallback).
* **"Select where to install" step:** The wizard must always show an explicit **«مسیر نصب» (Select where to install)** destination-directory page (`DisableDirPage=no`), defaulting to `{autopf}\VIRA` (or `{localappdata}\Programs\VIRA` for per-user installs). The chosen `InstallDir` is recorded under a stable registry key (`HKLM\SOFTWARE\VIRA\InstallDir`, or `HKCU` equivalent for per-user installs) so the updater and uninstaller can reliably locate the installation.
* **Package contents:** the bundled FastAPI backend (PyInstaller one-folder bundle or embedded CPython with `uv sync` locked site-packages), the compiled React SPA static assets served by FastAPI, the native PowerShell/batch scripts, `vira-updater.exe` (see §6), `version.json`, and `install_manifest.json` (per-file `path`, `SHA-256`, `size` for every installed file — the baseline for delta updates).
* **Wizard steps:** welcome → license (optional) → **directory selection (select where to install)** → additional tasks (desktop shortcut, Start menu, launch-at-login, register the Task Scheduler backup job) → install progress → finish. A Start menu/launcher shortcut runs `start_vira`, which starts FastAPI and opens the app in the default browser at `http://127.0.0.1:<port>`.
* **Uninstaller:** ship the standard Inno uninstaller. It must never delete user data (`%LOCALAPPDATA%\VIRA\data` SQLite files, receipt storage, encryption keys, logs, backups) — offer a "delete application data" checkbox only as an explicit opt-in, unchecked by default.

### 2. Versioning & Release Tags (SemVer + GitHub Releases)

* **Single version source of truth** (e.g., `backend/pyproject.toml`), stamped at build time into `version.json`, the installer metadata, the `openapi.json` / `/api/v1/health/ready` payload, and the UI (System & Operations page). Use strict SemVer `MAJOR.MINOR.PATCH`.
* **Tag every version:** when a version is finalized, create an annotated git tag `vX.Y.Z` and push it (`git tag -a vX.Y.Z -m "Release vX.Y.Z"` / `git push origin vX.Y.Z`). The release workflow triggers on `v*` tags. Tags are immutable — never move or re-use a tag; fixes ship as a new patch version. Maintain a `CHANGELOG.md`.
* **Release contents:** `VIRA-Setup-vX.Y.Z.exe`, delta update packages (§5), `latest.json` (§3), `SHA256SUMS`, and release notes in Persian (`notes_fa`) plus English.
* **Release workflow (extends Phase 6 §6):** run the full test suite (pytest + Hypothesis + Vitest + Playwright), build the SPA and backend bundle, compile the Inno Setup installer, generate delta packages against the last K = 3 released tags, upload the setup as a GitHub Actions workflow artifact, then publish the GitHub Release with all assets.

### 3. Update Channel & Manifest (`latest.json`)

* Every release publishes a machine-readable `latest.json` asset: `{schema_version, version, pub_date, min_app_version, notes_fa, notes_en, full_installer: {url, sha256, size}, deltas: [{from_version, url, sha256, size}], files_manifest_sha256}`. URLs must point to immutable GitHub Release assets.
* The app checks for updates via `GET https://api.github.com/repos/<owner>/<repo>/releases/latest`, then reads `latest.json` from the release assets. Use conditional requests (ETag caching), handle `403`/`429` rate limits gracefully with a retry-later Persian message, and support an optional `APP_UPDATE_URL` override for a self-hosted mirror.
* Never embed GitHub tokens in the app; anonymous public-repository access only. All update configuration is validated by `pydantic-settings`. *(Implemented in Phase 8: `backend/app/services/update.py` + `update_engine.py` (`parse_latest` refuses unknown `schema_version`); `APP_UPDATE_URL` + `UPDATE_PUBLIC_KEY` in `config.py`.)*

### 4. In-App Update UX ("Check for updates" — «بررسی به‌روزرسانی»)

* Add a Persian-only **«بررسی به‌روزرسانی»** button in the Sudo-protected **System & Operations** area (Phase 6 §8), available to the `owner` role after step-up re-authentication. Also run a non-blocking background check at application startup that shows a subtle "update available" badge; never auto-download or auto-install without explicit user confirmation.
* When a newer version exists, show an RTL Persian dialog that conveys exactly the required message **"A new update available, do you want to download and install?"**:
  * Title: **«به‌روزرسانی جدید موجود است»**
  * Message: **«به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟»**
  * A short release-notes summary, and buttons: **«دانلود و نصب»**, **«بعداً»**, **«مشاهدهٔ جزئیات»**.
* Show download progress (including the delta/download size), verification status, and a "restart to finish" step. On failure or rollback, show a clear Persian error («خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.») with the log path. All user-facing update strings live in `/locales/fa/…`.
* Update checks and installs use the existing typed `openapi-fetch`/httpx patterns, TanStack Query cache for status, and Zod-validated `latest.json` parsing.

### 5. Delta Update Engine (download only the changed parts)

* **Never re-download the full installer when a delta applies.** Maintain per-file SHA-256 manifests (from `install_manifest.json`). Each release publishes delta packages covering the last **K = 3** released versions: `VIRA-vX.Y.Z-delta-from-vA.B.C.zip`.
* **Delta package contents:** `update.json` (base version, target version, ordered file operations), `files/` (new/changed small files — templates, JS/CSS, scripts — stored as-is), `patches/` (**bsdiff** binary patches for large files such as `.exe`/`.dll`/`.pyd` above a threshold, e.g., 256 KB), `delete.json` (files removed in the target version), and a hash for every member.
* **Client-side selection:** if the current version has a matching delta → download the delta (typically a small fraction of the setup size). If the installation is older than the covered bases → fall back to the **full installer** (Inno Setup supports silent upgrade, `/SILENT`, into the recorded `InstallDir`). If reaching the target requires a chain of deltas, apply each hop with full verification, or fall back to the full installer.
* **Generation:** CI computes the file-manifest diff between the new build and each base tag's manifest and produces the per-base delta zips plus `SHA256SUMS`. *(Implemented in Phase 8: `scripts/build_manifest.py`, `scripts/gen_delta.py`, `scripts/build_deltas.ps1`, engine in `backend/app/services/update_engine.py`.)*
* Alternative mechanisms (zsync-style range diffs, MSIX/appinstaller) may replace this design only if they remain Windows-native, non-container, and satisfy "no full re-download" and "no data loss"; the manifest + bsdiff design above is the reference implementation.

### 6. Updater Helper & Transactional Apply (`vira-updater.exe`)

* The running application cannot overwrite its own files. Ship a tiny dedicated **updater helper** (native single executable) that the main app launches after the user confirms: *(Implemented in Phase 8: `scripts/vira_updater.ps1` → `vira-updater.exe` via ps2exe, launched by `POST /api/v1/system/update/apply`.)* it stages the verified package in `%LOCALAPPDATA%\VIRA\updates\<version>\`, gracefully stops FastAPI and the scheduler (reuse `stop_vira` semantics), then applies the file operations.
* **Single instance:** a named Windows mutex plus a local lock file prevent concurrent updates and prevent the app from starting mid-update.
* **Elevation:** request UAC elevation (`requireAdministrator`) only when `InstallDir` requires it; per-user installs update without elevation.
* **Transactional apply:** (1) snapshot every file scheduled to change into `{app}\rollback\prev\` and copy the current `install_manifest.json`/`version.json`; (2) apply copies and `bspatch` patches and delete removed files; (3) rewrite `install_manifest.json` + `version.json`; (4) relaunch the app. On **any** failure at any step: restore the snapshot and manifests, relaunch the previous version, and surface the Persian error with the log path. Keep the rollback snapshot until the new version reports healthy (first successful `/api/v1/health/ready` + accounting-invariant check).
* **After restart:** run the standard safe migration lifecycle (Phase 6 §7: SQLite online backup → `alembic upgrade head` → `PRAGMA integrity_check` / `PRAGMA foreign_key_check` → debit/credit equality) and record the outcome on the System & Operations page.

### 7. No Data Loss — Non-Negotiable

* User data (SQLite `vira.sqlite3` + WAL/SHM, receipt storage, encryption keys, configuration, logs, backups) lives exclusively outside `{app}` under `%LOCALAPPDATA%\VIRA\`. Updates, repair installs, and uninstallers must never overwrite or delete it.
* Before the first boot of a new version, the updater creates a pre-update SQLite online backup (`%LOCALAPPDATA%\VIRA\backups\pre-update-<version>.sqlite3`) and keeps the file-level rollback snapshot until health checks pass.
* A verified restore path is mandatory and tested; a failed update must always return the user to a working previous version with **all data intact**.

### 8. Update Security

* TLS to GitHub only; verify `SHA-256` of every downloaded package against `latest.json` before staging anything; *(Implemented in Phase 8 — SHA-256 verified before staging; Ed25519 via `scripts/sign_update.py` + `verify_latest_signature`; unknown schema refused.)* recommended: an Ed25519/minisign signature over `latest.json` with the public key baked into the app (protects against tampered release assets or mirrors).
* No file from a package is executed or written into `InstallDir` before verification succeeds. Unknown `latest.json` `schema_version` → refuse and prompt for a manual install.
* Rate-limit-aware GitHub API usage with ETag caching; never log update URLs containing credentials; no secrets in the repository or the update channel.

### 9. CI Verification (extends Phase 6 §5)

* On `v*` tags the release workflow builds everything in §2 and additionally uploads `VIRA-Setup-vX.Y.Z.exe` as a workflow artifact (GitHub artifact), satisfying "downloadable from GitHub artifacts" alongside the Release asset.
* A Windows CI job runs a silent-install smoke test (`VIRA-Setup-vX.Y.Z.exe /VERYSILENT /DIR=<temp>`), an upgrade test from the previous version using a real delta package (asserting downloaded bytes ≈ delta size, not the full setup), a data-preservation check (SQLite checksum identical across the update), and a forced-failure rollback test.

### 10. Testing & Acceptance Criteria

* **Unit:** manifest diffing, delta generation and selection, SemVer comparison, SHA-256 verification, rollback state machine, `latest.json` parsing (including malformed/old schema versions).
* **Frontend (Vitest/Playwright):** the «بررسی به‌روزرسانی» button and dialog copy (mocked GitHub API), progress UI, decline path, startup badge behavior, RTL/Persian rendering.
* **Integration (Windows):** fresh install shows the "select where to install" step and honors the chosen directory; in-app delta update downloads only the delta; user data byte-identical after update; rollback restores the previous version; uninstall keeps data by default.
* **Acceptance:** the full setup is downloadable from GitHub (Release asset + Actions artifact) with a visible "select where to install" step; every released version has a `vX.Y.Z` tag; in-app updates fetch from GitHub, announce with the required message, and **never re-download the whole setup when a delta exists**; zero data loss in every scenario.


## User-requested next-update scope — repair subphase 4-B (2026-10-16)

**Status: in progress, unreleased.** Execution was authorized after v1.0.10;
substep 4-B/1 covers pricing presentation and the light theme; 4-B/2 adds real
civil-date input and installation-wide calendar selection backed by versioned,
append-only SQLite security events. OWNER/BOOKKEEPER writes require CSRF and
compare-and-swap; authenticated AUDITOR reads are allowed. No new schema revision,
localStorage preference or historical-date rewrite. Item master-data implementation is now locally tested; the final Windows migration/rollback gate passed as recorded in the catalog report below. Installed-data/manual acceptance was deferred
by the user until the phases finish; automated tests remain mandatory.
The full scope, safe-deletion rules,
timezone/date-only semantics and acceptance criteria are recorded in
[`docs/plans/pricing-dates-catalog-theme-follow-up-fa.md`](docs/plans/pricing-dates-catalog-theme-follow-up-fa.md).

1. Remove cell-reference columns/formula annotations from the pricing report; preserve formulas, numeric results and green/blue/red highlights.
2. Apply the revised calendar policy above: default Jalali, persistent Gregorian/Jalali selection, real calendar input in orders and new accounting entries, and `Asia/Tehran` for today/timestamp presentation.
3. Add item master-data settings for adding/removing types, units and suppliers, consumed by New item. Reuse the supplier registry. Preserve referenced options/history through deactivation, and implement dynamic types/units across schema, API and UI with explicit inventory/production compatibility and no implicit stock conversion.
4. Slightly tint light-mode backgrounds cream or very pale green using shared tokens; preserve readable controls, accessible contrast, dark mode and pricing highlights.

Do not treat this queue as completion of repair phase 4, commencement of phase 5,
or approval for another release. Existing backup, immutable-tag, reviewed Persian notes,
select-path fresh installer and delta-only routine-update requirements remain mandatory.


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

### گام دستور مستقل native PDF و شواهد CRT — ۲۰۲۶-۱۰-۱۸

ورودی `rebuild_pdf_native.ps1` و بازرس native به‌عنوان مشتقات ابزار ساخت MIT،
صریحاً در دامنهٔ ۱۱فایلی ثبت شده‌اند؛ مجوز برنامه عوض نشده است.
[راهنمای ساخت مستقل](docs/dependencies/pdf-native-rebuild-guide.md) از سایدکار و
مسیر مطلقِ جدید، vcpkg پین‌شده و cache خاموش استفاده می‌کند؛ کامپایل به checkout
برنامه، Node/uv/Python برنامه، staging یا دیتابیس نیاز ندارد. Windows x64، PowerShell
7، Git، کامپایلر/SDK با شرایط مجاز و اینترنت پیش‌نیازند؛ SDK آفلاین نیست. بازرس
جداگانه Python/pefile می‌خواهد. overlay و تغییر مجاز سورس ممنوع نشده‌اند؛ هش مرجع
فقط معیار baseline است.

[proof ساخت طولانی مستقل و تست‌های عادی](docs/dependencies/pdf-native-rebuild-proof-run.json)
مرجع وضعیت نهایی است: اجرای plan یا تست قرارداد، موفقیت کامپایل واقعی نیست.
ممیزی باید ۲۰ درخت سورس مرجع و ۲۱ DLL/مالک/closure و مسیر واقعی بارگذاری را بررسی
کند؛ این هم اثبات PDF برنامه با DLL جدید، بازتولید بیت‌به‌بیت یا پذیرش نصب نیست.

کامپایلر اصلی از log واقعی مشخص شد: MSVC 19.51.36260.0، VS18/v145، مسیر ابزار
14.51.36231 و SDK/rc 10.0.26100.0؛ نه MSC1944 متعلق به Python همراه. متن‌های
نصب‌شده و توافق‌های رسمی ۲۰۲۶ VS/Build Tools/C++ Runtime بررسی و
[نشانی‌ها/بندها](docs/dependencies/pdf-crt-official-reference-review.json) ثبت شدند.
حقوق trial/full-use، استثنای ساخت وابستگی متن‌باز و نصب runtime با مجوز توزیع یکی
نیستند؛ entitlement و تطبیق CRT استاتیک بازند. نصب runner یا فهرست REDIST جای
اجازهٔ حقوقی نیست؛ برای DOCX صرفاً parse‌شده هش خام اختراع نشده است.

[گزارش فارسی](docs/reports/pdf-native-independent-rebuild-fa.md) شکست واقعی readiness/
rollback ویندوز و اصلاح diagnostic مربوط به cp1252 را هم حفظ می‌کند؛ سلامت و hash
ضعیف نشده‌اند. ۴۷۶ تست بک‌اند محلی، Ruff و Mypy/۸۴ موفق‌اند. شش گیت توزیع همچنان
ردیابی می‌شوند؛ موتور وارد payload عادی نشده، نسخه/تگ/انتشار نداریم و داده/محاسبه
یا پذیرش نصب‌شده تغییر نکرده است.

نتیجهٔ baseline مستقل: **39108011284 / d5b2516 موفق شد**؛ کامپایل از سایدکار و
تطبیق ۲۰ درخت سورس و مالکیت/closure/بارگذاری خصوصی ۲۱ DLL تأیید شدند. دو قطعهٔ
کامل در `pdf-native-independent-rebuild-evidence.json`، با هش و provenance artifact
فقط log/metadata در proof ثبت شد. این اثبات فنی baseline است، نه رفع گیت CRT یا
تحویل واقعی source/recipe و اتصال runtime به نصب عادی.

رگرسیون نهایی کد **39110216955 / 867dfd3: هر پنج job موفق**؛ شامل هر دو apply/
rollback واقعی جاری و schema/compiled-helper rollback نسخهٔ عمومی ۱٫۰٫۱۰،
۴۷۶ تست بک‌اند / ۱۹۶ فرانت‌اند / شش سناریوی مرورگر. ۷۱ بررسی متمرکز و Bandit
محلی موفق‌اند. شکست اولیهٔ readiness و اصلاح‌های diagnostic/test/lint حفظ شدند؛
موفقیت retry به معنی یافتن علت اولیه نیست. هیچ شرط production سلامت/hash/rollback
ضعیف نشد. ثبت نهاییِ شواهد فقط مستندات است، نه runtime یا انتشار جدید.

### بستهٔ بررسی سورس و آزمون مستقل CRT — ۲۰۲۶-۱۰-۱۸

ابزار `pdf_source_kit.py` به‌عنوان مشتق صریح ابزار ساخت MIT اضافه شد: دامنهٔ فعلی
۱۲ فایل است، نه مجوز برنامه. بستهٔ بررسی شامل ZIP اصلیِ ثابت، سایدکار دارای حقوق،
راهنما، notices/مکمل‌ها، inventory/policy/review و مرجع رسمی CRT با manifest اندازه/
SHA256 است. ساخت/بررسی فقط Python استاندارد می‌خواهد؛ بازرس هرگز checker پوشهٔ
هدف دلخواه را اجرا نمی‌کند و symlink/junction بیرون envelope را رد می‌کند. هش‌های
خود بسته authentication ناشر نیستند؛ digest مستقل و verifier مورد اعتماد لازم‌اند.

[proof بسته](docs/dependencies/pdf-source-kit-proof.json) اجرای واقعی `-I -S`،
استخراج ۲۱ symlink نسبی و محاسبهٔ مجددِ برابر ۲۰ درخت / ۲۵٬۵۰۵ ورودی را ثبت می‌کند.
استخراج امن، executable bit را حفظ و escape/collision/cycle/special-file و مسیر
موجود را رد می‌کند. در ویندوز نبود مجوز symlink خطای صریح است، نه flatten کردن.
artifact بررسی ۹۰روزه، تحویل پایدار ناشناس نیست؛ کامپایل مستقیم از درخت local یا
آفلاین ثابت نشده و فرمان build هنوز ورودی‌های پین‌شده را دانلود می‌کند.

[probe مستقل CRT](docs/dependencies/pdf-crt-static-probe-proof.json) با `/MT` واقعاً
کامپایل/اجرا شد: directive استاتیک، هفت مسیر library با هش، ۳۱۷ رویداد Loaded و
import فقط KERNEL32 برای همین probe ثبت شدند؛ نه ۳۱۷ جزء یکتا یا map همان ۲۱ DLL.
شکست‌های `/VERBOSE:LIB` حفظ و با `/VERBOSE` کامل، بدون حذف شرط object trace، اصلاح
شدند. SDK-UCRT، پشتیبانی کامپایلر، startup و C++ static library جدا هستند؛ تغییر
ساده به `/MD` هم startup استاتیک را حذف یا مجوز توزیع را اثبات نمی‌کند.

[گزارش فارسی](docs/reports/pdf-source-kit-and-crt-probe-fa.md) و قرارداد تحویل سورس
همگام‌اند. ۵۰۶ تست بک‌اند محلی / ۷۹ متمرکز، Ruff/Mypy/۸۴ و Bandit موفق‌اند؛ نتایج
CI عادی جدا ثبت می‌شوند. شش گیت، از جمله حقوق CRT، تحویل واقعی، LGPL/EULA و
production bootstrap/native updates/پذیرش نصب‌شده بازند. داده، محاسبه، payload
عادی، نسخه/تگ/انتشار یا مجوز کل برنامه تغییر نکرده است.

نتیجهٔ نهایی کد: بستهٔ سورس **39113483257**، ممیزی source/مجوز **39113483241**
و هر پنج job عادی **39113483256** روی **1e27683** موفق شدند؛ ۵۰۶ بک‌اند / ۱۹۶
فرانت‌اند / شش سناریوی مرورگر و هر دو rollback واقعی ویندوز، شامل schema/helper
نسخهٔ عمومی ۱٫۰٫۱۰. probe CRT جدا **39113097728 / 0bceb1e** هم موفق است و
شکست‌های اولیه حفظ شده‌اند. digest بسته و انقضای artifact در proof پین شدند؛ این
تحویل عمومی، مجوز CRT یا تغییر recipe بومی/داده/برنامه نیست.

### ساخت مستقیم از preferred source محلی — ۲۰۲۶-۱۰-۱۸

ادامهٔ مجازشده ابزار استاندارد-library و پین صریح recipeها را به مشتقات محدود
MIT افزود: **۱۴ فایل صریح**، نه مجوز کل برنامه. فرمان پیش‌فرض native هنوز سورس
دانلود می‌کند؛ مسیر جدید با گزینهٔ موجود `-OverlayPorts`، درخت محلیِ استخراج‌شده و
ازقبل‌پچ‌شده را مصرف می‌کند. catalog واقعی ۱۹ ریشهٔ یگانه + واسط خالی `pthread`
را ثابت کرد؛ چندریشه‌ای/نام غیرمنتظره، recipe تغییرکرده، لینک/مسیر ناامن و تغییر
سورسِ بدون `--allow-modified` رد می‌شوند. لینک زیرپوشه‌ای ویندوز هنگام ایجاد از
جداکنندهٔ native استفاده می‌کند؛ digest همچنان POSIX و برابر آرشیو است.

driver و پروفایل native عوض نشدند؛ فقط دریافت سورسِ target جایگزین می‌شود، نه
توابع دانلود سراسری یا recipe ابزار host. SLJITِ ادغام‌شدهٔ PCRE2 دوباره حذف/پچ
نمی‌شود؛ APNGِ ثبت‌نشده رد می‌شود. مجوز کامل MIT/upstream همراه می‌ماند. برای اثبات
واقعی، تغییر صریح Pango باید از تابع DLL بازسازی‌شده دیده شود، همراه هش ۲۰ درخت،
مالک/closure/مبدأ ۲۱ DLL و ثابت‌ماندن ورودی بیرونی. ZIP اصلی دست‌نخورده است؛ مرجع
تغییرکرده جداست، نه سورس متناظر جدیدِ منتشرشده یا نامزد runtime عادی.

[گزارش](docs/reports/pdf-local-preferred-source-replay-fa.md) و
[دستور دقیق محلی](docs/dependencies/pdf-native-rebuild-guide.md) مرجع‌اند.
۵۳۶ تست بک‌اند، ۸۴ بررسی متمرکز و Ruff/Mypy/Bandit موفق‌اند؛ ساخت واقعی
**39146630126 / 576c0ea** و ممیزی نهایی **موفق شدند**: ۲۰ درخت، مالک/closure/مبدأ
۲۱ DLL و اجرای واقعی `1.58.0-vira-local-source`، با ورودی بیرونیِ بدون تغییر.
[proof هفت قطعهٔ کامل و هش‌ها](docs/dependencies/pdf-local-source-replay-proof.json)
ثبت شد. شکست لینک ویندوز و خطای make در gettext حفظ شدند؛ بازگرداندن mtime ZIP
از regeneration ناخواستهٔ Autotools جلوگیری می‌کند. هر پنج job عادی
**39146693875 / ca4b61e** موفق‌اند؛ شامل ۱۹۶ فرانت‌اند، شش سناریوی مرورگر و هر دو
rollback واقعی ویندوز.
شش گیت حقوقی/تحویل/CRT/LGPL/production بازند؛ SDK آفلاین، مجوز توزیع، پذیرش نصب،
تغییر داده/محاسبات، installer/payload معمول یا نسخه/تگ/انتشار نتیجه گرفته نمی‌شود.

بستهٔ نهاییِ همراه راهنما/policy به‌روز **39150398698 / f4c088b** و ممیزی
source/مجوز **39150398692** نیز موفق‌اند: ۲۶ فایلِ manifest، ۱۴ فایلِ مجاز،
rehash واقعی ۲۰ درخت و ۲۱ symlink؛ build ویندوز جدا پین شده و ادعای یکسانی
دقیق envelope، bitwise یا تحویل عمومی پایدار مطرح نیست.

### مصرف خصوصی موتور ساخته‌شده از سورس محلی در برنامه — ۲۰۲۶-۱۰-۱۸

ادامهٔ مجازشده **موفق** شد: ساخت تازهٔ `39153212109 / 284e827` و سپس رندر واقعی
از CPython تولید **3.11.17** در مسیر `VIRA چاپ بومی`. ۲۰ درخت و مالک/closure/هش
۲۱ DLL ممیزی شدند و هر ۲۱ مورد در فرایند رندر از نامزد خصوصی بارگذاری شدند؛
تابع Pango در **همان فرایند** مقدار `1.58.0-vira-local-source` داد. PDF واقعیِ
یک/چهارصفحه‌ای A4، وزیرمتن Regular/Bold و هر سه مجموعهٔ ارقام، manifest ثابت،
نبود بازرسان dev در تولید، `-I` و callbackهای ctypes تأیید شدند.

[گزارش](docs/reports/pdf-local-source-app-consumer-fa.md) و
[proof کامل هشت‌قطعه‌ای با هش](docs/dependencies/pdf-local-source-app-consumer-proof.json).
۲۶ تست تازه؛ ۵۶۲ بک‌اند / ۶۱ متمرکز و Ruff/Mypy/Bandit موفق‌اند. هر پنج job عادی
`39153212117 / 284e827` نیز موفق‌اند: ۱۹۶ فرانت‌اند / شش مرورگر / هر دو rollback
قبلی ویندوز. ابزار اتصال/کنترل QA برنامه **خارج از دامنهٔ MIT چهارده‌فایلی** است.
مرجع اصلاح‌شده `source_archive=null` می‌ماند؛ آرشیو متناظر جدیدی تهیه/منتشر نشده.
هر شش گیت بازند؛ این مصرف خصوصی جای جایگزینی در نصب واقعی/EULA، حق CRT، تحویل
عمومی سورس، bootstrap Unicode یا Inno/native delta/rollback/پذیرش نصب‌شده نیست.
نسخه/تگ/انتشار، مجوز کلی، payload عادی، نصب/داده و محاسبات تغییر نکردند.

### بستهٔ خصوصی سورس کامل نسخهٔ اصلاح‌شده — ۲۰۲۶-۱۰-۱۸

گام مجازشده آرشیو کاملِ **مجزای اصلاح‌شده** را کنار original-kit/ZIP اصلیِ بدون
تغییر و recipe مجاز آماده می‌کند؛ نه انتشار عمومی. اجرای
**39158897935 / f00ca08**: assemble، دانلود واقعی artifact در ویندوز، استخراج
۲۰ درخت / ۲۵٬۵۰۵ ورودی / ۲۱ لینک و آماده‌سازی recipe برابر شاهد ساخت موفق‌اند.
SHA256 آرشیو جدید `1d56fe9a3305f3b9bb7a741dbb697b7d5b9a80a74a1c7bb172e91895ea311921`.
همان مشتق مجازِ ابزار بسته‌سازی در دامنهٔ MIT **۱۴فایلی** است، نه app/QA/CRT.

[گزارش](docs/reports/pdf-modified-source-kit-fa.md)،
[proof](docs/dependencies/pdf-modified-source-kit-proof.json) و
[نقص واقعی انتقال](docs/dependencies/pdf-modified-source-transport-failure.json)
ثبت شدند: upload فایل مجازِ مخفی .github را حذف کرده بود؛ تشخیص مستقل دقیقاً
همان فایل را ثابت کرد. opt-in فقط برای artifact محدود سورس/recipe اضافه شد،
نه تضعیف manifest/hash یا upload کل مخزن. pre-upload قبولیِ انتقال نیست.
۳۵ تست تازه / ۱۱۹ متمرکز و ۵۹۷ بک‌اند موفق‌اند. رگرسیون واقعی بومی
**39158539572 / d47e2c9**، با ۲۰ درخت/۲۱ DLL و تابع اصلاح‌شده موفق شد؛ شاهد کامل
هفت‌قطعه‌ای پین شد. هر پنج job عادی **39160309610 / 693f887** موفق‌اند، با ۱۹۶
فرانت‌اند/شش مرورگر/هر دو rollback ویندوز. شکست واقعی badge در 7139 حفظ شد؛
diagnostic فقط QA بود و هیچ wait/assertion یا رفتار اپ را تغییر نداد. علت اولیه
از موفقیت retry نتیجه گرفته نمی‌شود. بستهٔ نهایی همراه راهنما/policy
**39159627961 / 7139e41**، kit اصلی **39159627909** و ممیزی source/مجوز
**39159627993** هم موفق‌اند؛ digest subkit با دریافت واقعی ویندوز تطبیق داده شد.

اعلان خارجیِ تغییر/تاریخ موجود است، اما داخل فایل Pangoِ واقعاً کامپایل‌شده اعلان
تازه وجود ندارد؛ قبولی کامل شروط LGPL ادعا نمی‌شود. افزودن آن hash و build تازه
می‌خواهد. مرجع helper قدیمی عمداً source_archive=null می‌ماند، چون خودش این بستهٔ
بررسی را ایجاد/احراز نمی‌کند؛ proof تاریخی بازنویسی نمی‌شود. کامپایل تازه از **همین
envelope**، تحویل عمومی پایدار، CRT/EULA و production نتیجه گرفته نمی‌شوند؛ شش
گیت بازند. داده/محاسبات، نصب/payload معمول، نسخه/تگ/انتشار و پذیرش نصب عوض نشدند.

### اعلان داخل سورس و ساخت/PDF مستقیم از بستهٔ تازه — ۲۰۲۶-۱۰-۱۹

گام مجازشده **موفق** شد: `39165372821 / 84c20ac`. اعلان برجستهٔ تغییر/تاریخ در
خود `pango-utils.c` اضافه شد، headerهای upstream و ZIP اصلی بدون تغییر ماندند.
ZIP تازه **۱۸۸٬۶۱۷٬۰۴۶ بایت** با SHA256
`b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2` است.
این بار artifact واقعاً در ویندوز دانلود و با digest مستقلِ خروجی job تولیدکننده
احراز شد؛ همان سورسِ دارای اعلان، بدون ویرایش پس از استخراج و بدون cache باینری
کامپایل شد. ۲۰ درخت واقعی، فایل جدید Pango و closure/هش/مبدأ ۲۱ DLL تأیید شدند؛
هر ۲۱ DLL در CPython تولید 3.11.17 با مسیر فارسی/فاصله‌دار برای PDF واقعی مصرف شدند.
Pango در همان فرایند `1.58.0-vira-local-source` داد؛ PDF یک/چهارصفحه‌ای A4،
وزیرمتن ۴۰۰/۷۰۰ و هر ۳۰ رقم کنترل شد. envelope بعد از ساخت/رندر دوباره احراز شد.

[گزارش](docs/reports/pdf-noticed-archive-build-fa.md)، [proof](docs/dependencies/pdf-noticed-archive-build-proof.json) و شاهد کاملِ هش‌شدهٔ پیوست آن
زنجیرهٔ archive→درخت‌های کامپایل‌شده→DLLهای مصرف‌شده→PDF را به هم متصل می‌کنند.
شاهد تاریخی بازنویسی نشد: بسته در زمان تهیه هنوز build جدید را اثبات‌نشده اعلام
می‌کند؛ proof جدا، موفقیت **تازه** را به همان hash وصل می‌کند. helper قدیمی
`source_archive=null` می‌ماند، چون خودش envelope را تولید/احراز نمی‌کند.

۱۰ تست تازه؛ ۶۰۷ بک‌اند، Ruff/Mypy۸۴/Bandit و scopeِ MIT چهارده‌فایلی موفق‌اند.
مجوز کلی/app-QA/CRT تغییر نکرده است. این شاهد شکاف فنیِ اعلان داخل فایل و ساخت
از همین بسته را می‌بندد، نه گیت‌های حقوقی/تحویل/نصب را: شش گیت همچنان بازند؛
CRT و مجوز اجزا، recipient/toolchain review، تحویل ناشناس پایدار، EULA/تعویض DLL
در نصب واقعی، bootstrap Unicode/Inno/native delta/rollback و پذیرش نصب‌شده بازند.
نسخه/تگ/انتشار، نصب/payload معمول، داده و محاسبات تغییر نکردند.

### bootstrap خصوصی Unicode: Fontconfig حافظه‌ای، UTF-8 پایتون و ACP ویندوز — ۲۰۲۶-۱۰-۱۹

**39175100427 / fa68e2a موفق**: پیش‌آزمون SDK پین‌شده با ۲۷ DLL، سپس روی runner
جدا ساخت تازهٔ بدون binary cache از آرشیو دارای اعلان، پیش از وابستگی‌های app؛
۲۰ درخت/۲۱ DLL، Pango نشانه‌گذاری‌شده و دو فرایند private CPython 3.11 با همان
state. app/interpreter/DLL، profile/LOCALAPPDATA/cache/TEMP و CWD نامرتبط، فارسی/
فاصله‌دارند. configuration فعال از حافظهٔ UTF-8، صفر قلم سیستم؛ TTFهای موقت با هش
وزیرمتن ۴۰۰/۷۰۰ تطبیق و بعد هر سند حذف شدند. PDF واقعی یک/چهارصفحه‌ای A4 و هر ۳۰
رقم در هر دو فرایند کنترل شد؛ ممیزی native/candidate به شاهد متصل و envelope سورس
در پایان دوباره احراز شد. SDK پیش‌آزمون **هرگز** شاهد منشأ ۲۱ DLL محسوب نشده است.

خطاهای واقعی جدا ثبت شدند: CP1252 خواندن سورس تست؛ CP1252 کدگذاری مسیر موقت در
WeasyPrint؛ سپس native filename که با وجود Python UTF-8 هنوز ACP 1252 داشت.
کنترل مستقیم همان TTFها در مسیر فارسی/ASCII تفاوت را اثبات کرد. نسخهٔ خصوصی با
`-I -B -X utf8` و **PE manifest تغییرکردهٔ CPython** اجرا می‌شود تا `GetACP()==65001`
شود؛ هر دو هش EXE و manifest اصلی/جاسازی‌شده و ابزار ثبت‌اند، semantics قبلی حفظ
شده‌اند. این EXE **دست‌نخوردهٔ upstream نیست**؛ baseline خصوصی پس از تغییر restamp
و در هر دو worker ثابت کنترل شده است. این کار نه تغییر stage/installer عادی است،
نه تأیید امضای تولید یا مجوز redistribution آن. نیاز 1903+، notices/امضای CPython و
پوشش نسخه‌های ویندوز بازبینی تولیدِ باز دارند.

[گزارش](docs/reports/pdf-unicode-bootstrap-fa.md)، [شاهد از سورس](docs/dependencies/pdf-unicode-bootstrap-proof.json)، [پیش‌آزمون مستقل](docs/dependencies/pdf-unicode-bootstrap-preflight-proof.json)
و رکوردهای شکست در گزارش‌اند. **۶۲۶ بک‌اند** شامل ۱۷ کنترل helper و دو کنترل تازهٔ
شاهد، Ruff/Mypy۸۵/Bandit گیت متوسط/شدید و MIT چهارده‌فایلی موفق‌اند. ممیزی وابستگی
یک failure بی‌trace قابل‌دریافت داشت؛ علت آن حدس زده نشده، فرمان/exit status حفظ و
diagnostics افزوده شد؛ قبولی واقعی اجرای بعدی جدا ثبت شده است.

helper و QA خارج از grant محدود MIT هستند؛ پیش‌فرض renderer/HTTP عوض نشده و
bootstrap خصوصی به مسیر عادی وصل نیست. read-only TTF ≠ ACL نصب؛ reuse state ≠ cache
hit. هر شش گیت باز: حقوق اجزا/CRT، بازبینی ابزار/کیت، سورس عمومی پایدار، EULA/تعویض
DLL و bootstrap عمومی/Inno/native delta/rollback/پذیرش نصب‌شده. داده، محاسبات، نصب
کاربر، version/tag/release تغییر نکرده‌اند؛ انتشار مجاز نشده است.

### راه‌انداز خصوصیِ پیش از import، بدون site — ۲۰۲۶-۱۰-۱۹

**39182480848 / 8118098 موفق**: entry خصوصی stdlib-only با `-I -S -B -X utf8`،
دو digest مستقل و بررسی تمام baseline، pin مسیر کامل libffi پیش از ctypes/app/
WeasyPrint، ACP 65001 و دو PID تازه با state مشترک. SDK پین‌شده **۲۷ DLL** دارد؛
این مرحله **ساخت سورس یا ترکیب launcher جدید با ۲۱ DLL قبلی نیست**. PDF واقعی
یک/چهارصفحه‌ای A4، وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم، TEMP فارسی/پاک‌سازی و صفر قلم سیستم
کنترل شدند. سه negative واقعیِ no-site، import زودهنگام و digest نادرست رد شدند.
۴۲ کنترل رفتاری/workflow و دو کنترل شاهد اضافه شد؛ مجموع **۶۷۰ بک‌اند** موفق‌اند.

[گزارش](docs/reports/pdf-private-launcher-fa.md) و [proof](docs/dependencies/pdf-private-launcher-proof.json). شکست‌های واقعی setup/دانلود/ArtifactService
و 403 بازاجرای مستقیم ثبت شدند؛ نه failure حذف شد، نه SHA/assertion تضعیف شد.
پیش‌آزمون SDK جای منشأ سورس نیست و هیچ شاهد تاریخی بازنویسی نشده است.

`start_vira.cmd`، staging عادی، HTTP startup، Inno/updater، داده/محاسبات و نسخه/
tag/release تغییر نکرده‌اند. این entry فقط CI/private TEMP است؛ امضای تولید یا
دفاع ضد‌دست‌کاری مستقل ادعا نمی‌شود. همهٔ شش گیت بازند؛ startup واقعی HTTP، pair
با سورس‌ساخته‌شده‌ها و native update/rollback هنوز جداگانه باید اثبات شوند. MIT
همان ۱۴ فایل native build است، نه launcher/QA یا کل app.

### startup واقعی HTTP، فقط در CI خصوصی — ۲۰۲۶-۱۰-۱۹

**39215968473 / 7634e93 موفق**: entry بدون site پیش از import app، سپس migrator،
create_app و Uvicorn واقعی روی TCP loopback؛ live/ready، SPA ساخته‌شده، OpenAPI،
رد بدون login/login غلط/CSRF غایب و ورود cookie واقعی. دو process تازه همان DB و
ID سفارش‌ها را حفظ کردند؛ چهار PDF از route عادی در هر process، مجموع هشت PDF
۱/۴صفحه‌ای A4، وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم Regular و ۱۰ رقم فارسی Bold، SHA asset و
پاک‌سازی سخت‌گیرانه. دو درخواست موازی client موفق؛ render به‌سبب قفل فعلی DB
سریالی (peak=1) بود و ادعای دو render هم‌زمان نداریم. هیچ قفل/محاسبه‌ای تغییر نکرد.

این شاهد **SDK/۲۷ DLL با font adapter تزریقیِ process QA** است، نه startup عادی/
production یا source21 pairing. اولین تلاش HTML داد و رد شد؛ نقص cache با regression
اصلاح و failure حفظ شد. ۱۴ کنترل رفتاری/workflow و دو کنترل شاهد؛ **۶۸۶ بک‌اند**
موفق. [گزارش](docs/reports/pdf-private-http-fa.md)، [proof](docs/dependencies/pdf-private-http-proof.json). شش گیت باز، grant همان MIT۱۴ فایل native-build؛
نه شامل worker/launcher/QA یا کل app. نصب/راه‌انداز عادی/staging/Inno/updater/داده/
محاسبات/نسخه/tag/release تغییر نکرده‌اند؛ درخواست تست/نصب کاربر نداریم.

### جفت‌کردن HTTP واقعی و سورسِ اعلان‌دار، فقط CI خصوصی — ۲۰۲۶-۱۰-۱۹

**39226693623 / b04440e موفق**: archive احرازشده → کامپایل تازهٔ۲۰ درخت با binary cache
خاموش → audit مستقل۲۱ DLL → launcher بدون site → factory/lifespan/Uvicorn و
TCP/auth/CSRF/SQLite واقعی. دو PID، DB و IDهای یکسان، هشت PDF واقعی۱/۴صفحه‌ای،
وزیرمتن۴۰۰/۷۰۰،۳۰ رقم Regular/۱۰ فارسی Bold، ACP65001، hash TTF، صفر قلم سیستم
و پاک‌سازی هر سند؛ نسخهٔ function واقعی Pango=`1.58.0-vira-local-source`.
SDK۲۷/1.58.2 و شاهدهای قدیمی مستقل و بدون بازنویسی‌اند؛ preflight SDK منشأ سورس
نیست. `ffi-8.dll` سورس با `libffi-8.dll` احتمالی CPython یکی فرض نمی‌شود.
client موازی ولی peak واقعی۱؛ قفل و محاسبه تغییر نکرده و throughput ادعا نمی‌شود.

شکست انتقال شاهد در39220310210/f479 حفظ شد؛ تمام مراحل فیزیکی موفق، ولی workflow
کلی ناموفق بود. traceback اصلی در دسترس نبود؛ regression حجم واقعی، مشکل حجم
متن تکراری inventory را نشان داد. projection صریح، تمام فیلدهای binding را نگه
می‌دارد و inventory کامل در artifact باقی است؛ سقف۳۲بخش/guardها تغییر نکردند.
اجرای اصلاح‌شده دوباره تمام کامپایل/HTTP را انجام داد و موفق شد.۲۶ کنترل،۹ آزمون
synthetic و۲ کنترل شاهد واقعی؛۷۲۳ بک‌اند موفق. [گزارش](docs/reports/pdf-source-http-fa.md)،
[proof](docs/dependencies/pdf-source-http-proof.json). هر شش گیت باز، MIT همان۱۴فایل
native-build و نه QA/HTTP/کل app؛ default عادی/نصب/Inno/updater/داده/محاسبات/نسخه/
tag/release تغییر نکردند. پذیرش نصب و حقوق CRT/EULA/تحویل پایدار نتیجه گرفته نمی‌شوند.

### آماده‌سازی PDF متعلق به app — ۲۰۲۶-۱۰-۱۹؛ نه proof جدید Windows

service جدید `PdfRenderer` و `PrivatePdfPolicy` تغییرناپذیرِ فقط‌مسیر؛ factory با
keyword خصوصی، renderer همان app را انتخاب می‌کند و route از Request.app.state
استفاده می‌کند. default بدون policy دقیقاً legacy است؛ setting/env/HTTP/UI برای
فعال‌سازی اضافه نشده و launcher نصب‌شده mode خصوصی را انتخاب نمی‌کند. در انتخاب
خصوصی، عمر cache/config هر سند در خود app مدیریت می‌شود، بدون monkeypatchِ QA یا
configuration factory ورودی. خطا/interrupt/cleanup نباید بایت موفق برگردانند؛
خروجی غیرPDF رد می‌شود و fallback HTML/CSP عادی، context/math/قفل DB حفظ شده‌اند.
factory/route تغییر دارند؛ pdf.py/pdf_fontconfig.py و bootstrap native تغییر ندارند.

۲۲ کنترل synthetic/ASGI/import؛ **۷۴۵ بک‌اند** بدون skip، Ruff/Mypy۸۶/Bandit و
MIT۱۴ موفق. OpenAPI دو mode یکسان است. این آزمون‌ها عمداً fake هستند، نه اجرای
native/TCP/قلم در Windows؛ شاهد source21 قدیمی برای wiring جدید بازنام‌گذاری نشد.
Windows HTTP و source21 با policy متعلق به app هنوز **اثبات‌نشده** است؛ آزمون بعدی
باید بدون جایگزینی renderer با FontAudit اجرا شود. policy/review هم‌زمان به‌روز،
شش گیت باز؛ default قلم، نصب/launcher/staging/Inno/updater/نسخه/tag/release/دادهٔ
واقعی تغییر نکردند. MIT شامل app/service/QA جدید نیست.
[گزارش](docs/reports/pdf-app-owned-preparation-fa.md)، [شاهد محدود محلی](docs/dependencies/pdf-app-owned-preparation-evidence.json).

### HTTP واقعی Windows با قلم متعلق به app — ۲۰۲۶-۱۰-۱۹؛ نه default نصب

SDK `39243690293` با۲۷ DLL/Pango1.58.2 موفق؛ سورس مستقل `39243690330` نیز
پس از archive احرازشده/کامپایل سرد۲۰درخت۲۱DLL و function تغییرکردهٔ Pango موفق.
مسیر regression قدیمی جدا و سپس app-owned بدون جایگزینی render_pdf/تحویل
configuration factory از QA اجرا شد. هویت callable/محل تعریف با unwrap ثابت؛
observer فقط دادهٔ سادهٔ lifecycle را می‌خواند، نه native object یا رفتار renderer.
هر مسیر دو process، DB/ID ثابت،۸ PDF واقعی۱/۴صفحه‌ای؛ مجموع۱۶ app-owned، نه PDFهای
regression/شاهد قدیمی. factory/lifespan/TCP/login/CSRF/SQLite/SPA/OpenAPI، وزیرمتن
۴۰۰/۷۰۰ و۳۰/۱۰رقم، TTF SHA، صفر قلم سیستم، cleanup font/cache و سه negative واقعی
موفق‌اند. client موازی اما peak واقعی۱؛ قفل/محاسبه عوض نشده. envelope بعد از owned
دوباره احراز شد؛ callback ctypes منشأ FFI سورس را ثابت نمی‌کند.

شکست واقعی worker در39242791845 (نبود active) حفظ و با regression/بازاجرای کامل
اصلاح شد.۱۷ guard،۲ schema synthetic و۲ کنترل شاهد؛۷۶۶ بک‌اند، Ruff/Mypy۸۶/Bandit
و MIT۱۴ موفق. [گزارش](docs/reports/pdf-app-owned-http-fa.md)، [proof SDK](docs/dependencies/pdf-app-owned-sdk-http-proof.json)،
[proof سورس](docs/dependencies/pdf-app-owned-source-http-proof.json). شش گیت باز؛
policy/review همگام، MIT نه app/QA. این هنوز caller خصوصی/interpreter با manifest
تغییرکرده است، نه startup عادی/نصب/امضا/minOS/EULA/CRT/تحویل عمومی/پذیرش نصب.
default legacy و launcher/staging/Inno/updater/نسخه/tag/release/داده/محاسبه تغییر نکردند.

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
