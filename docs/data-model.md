# V.I.R.A — Core Data Entities & Relationships (Phase 1)

> Phase 1 deliverable: the core data entities, fields, and relationships centered on **"products to sell"** and **warehouse inventory items**, feeding the dynamic dashboard. This is the planning-level model; Phase 4 turns it into the full SQLite schema (STRICT tables, scaled integers, Alembic migrations) and must honor everything here.

---

## 1. Conventions (apply to every entity)

| Concern | Rule |
|---|---|
| IDs | `TEXT` UUIDv7 (generated app-side) |
| Dates | stored Gregorian ISO `YYYY-MM-DD`; **displayed Jalali** (fa-IR) |
| Timestamps | UTC ISO-8601 `TEXT` |
| Money | **scaled integers ×10,000** (exact Toman/IRR; see currency decision in `project brief.md`) |
| Quantities | scaled integers ×10,000 (exact decimal grams/pieces) |
| Booleans | `INTEGER` 0/1 with `CHECK` |
| Enums | `TEXT` + `CHECK` (values listed per entity) |
| Audit | every table: `created_at`, `updated_at`, `created_by`; ledger-grade tables also use `version_id` (optimistic locking) |

---

## 2. Entities

### 2.1 Suppliers — `suppliers` (تأمین‌کنندگان)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | TEXT | نام تأمین‌کننده |
| `contact_name` | TEXT | |
| `phone`, `email` | TEXT | |
| `address` | TEXT | آدرس (required by the main idea) |
| `price_score` | INTEGER 0–10 | قیمت |
| `quality_score` | INTEGER 0–10 | کیفیت |
| `delivery_score` | INTEGER 0–10 | زمان ارسال |
| `is_active` | 0/1 | |
| `notes` | TEXT | |

Derived: `total_score = w_p·price + w_q·quality + w_d·delivery` (weights in `app_settings`, default 0.40/0.35/0.25). Optional **`supplier_score_events`** (supplier_id, scores, changed_at) keeps score history for trends.

### 2.2 Warehouse inventory items — `inventory_items` (اقلام انبار)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `item_type` | CHECK `FILAMENT`, `MODEL`, `PACKAGING`, `SUPPLIES` | فیلامنت / مدل تولیدی / بسته‌بندی / سایر |
| `name` | TEXT | e.g. filament name |
| `unit` | CHECK `GRAM`, `KILOGRAM`, `SPOOL`, `PIECE` | موجودیت/واحد |
| `weight_per_unit_g` | qty | وزن (per stock unit) |
| `color` | TEXT | رنگ |
| `unit_price` | money | قیمت (purchase price/unit) |
| `received_date` | DATE | تاریخ |
| `supplier_id` | FK → suppliers | `ON DELETE RESTRICT` |
| `quantity_on_hand` | qty | **cached**; source of truth = movements (recomputed/validated) |
| `reorder_threshold` | qty | آستانه هشدار |
| `reorder_lot_qty` | qty | suggested reorder lot |
| `location` | TEXT | shelf/bin |
| `notes` | TEXT | |

Indexes: `(item_type, name)`, `(supplier_id)`, `(quantity_on_hand)`.

### 2.3 Products to sell — `products` (محصولات)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `sku_code` | TEXT UNIQUE | |
| `name`, `description` | TEXT | |
| `net_weight_g` | qty | filament consumed per unit |
| `print_hours_per_unit` | qty | print time per unit |
| `has_chain_variant` | 0/1 | زنجیر دار supported |
| `suggested_price` | money | from the price calculator (§4.3 of the product spec) |
| `is_active` | 0/1 | |

A product, once produced, also exists as an `inventory_items` row of type `MODEL` (kept in sync via `product_id` on the model item, or a dedicated link table).

### 2.4 Bill of materials — `product_materials`

`id`, `product_id` FK, `item_id` FK, `quantity_per_unit` qty, `variant` (`BOTH`/`PLAIN`/`CHAIN` — e.g. chain item only for chain variant). UNIQUE `(product_id, item_id, variant)`.

### 2.5 Customers — `customers` (مشتریان)

`id`, `full_name` (نام کامل), `phone` (شماره تماس), `address` (آدرس), `notes`. Index on `phone`.

### 2.6 Sales orders — `sales_orders` + `sales_order_lines` (سفارش‌ها)

**`sales_orders`**

| Field | Notes |
|---|---|
| `id`, `order_number` | `order_number` UNIQUE sequential (`SO-<jalali-year>-<seq>`) |
| `order_date` | DATE |
| `customer_id` | FK → customers (`RESTRICT`) |
| `status` | CHECK `DRAFT`, `CONFIRMED`, `IN_PRODUCTION`, `READY`, `SHIPPED`, `COMPLETED`, `CANCELLED` |
| `channel` | CHECK `DIRECT`, `MARKETPLACE` (+ `external_ref` e.g. Digikala id) |
| `discount`, `subtotal`, `total` | money (scaled) |
| `notes`, `version_id` | |

**`sales_order_lines`**

`id`, `order_id` FK (`CASCADE` only while DRAFT; `RESTRICT` after — enforced service-side + triggers), `product_id` FK, `variant` (`PLAIN`/`CHAIN`), `quantity` qty, `unit_price` money, `discount` money, `line_total` money (computed + checked).

### 2.7 Purchases — `purchases` + `purchase_lines` (خرید)

**`purchases`**: `id`, `purchase_number` UNIQUE, `supplier_id` FK, `purchase_date`, `status` (`DRAFT`, `RECEIVED`, `CANCELLED`), totals, notes.  
**`purchase_lines`**: `id`, `purchase_id` FK, `item_id` FK, `quantity` qty, `unit_price` money, `line_total` money.

### 2.8 Production — `production_orders` + `production_consumptions` (تولید)

**`production_orders`**

| Field | Notes |
|---|---|
| `id`, `production_number` | UNIQUE (`PR-<jalali-year>-<seq>`) |
| `sales_order_line_id` | FK nullable (make-to-order) |
| `product_id` | FK |
| `variant` | `PLAIN`/`CHAIN` |
| `quantity_planned`, `quantity_produced` | qty |
| `status` | CHECK `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` |
| `started_at`, `completed_at` | timestamps |
| `notes` | |

**`production_consumptions`**: `id`, `production_order_id` FK, `item_id` FK, `quantity_planned` qty, `quantity_actual` qty (nullable until confirmed), UNIQUE `(production_order_id, item_id)`.

### 2.9 Inventory movements — `inventory_movements` (گردش انبار)

| Field | Notes |
|---|---|
| `id` | UUID |
| `item_id` | FK |
| `movement_type` | CHECK `PURCHASE_IN`, `PRODUCTION_OUT`, `PRODUCTION_IN`, `SALE_OUT`, `ADJUSTMENT` |
| `quantity` | qty (**signed semantics by type**: IN positive, OUT negative — store signed, `CHECK` sign matches type) |
| `unit_cost` | money (cost basis at movement time) |
| `reference_type`, `reference_id` | polymorphic link (`purchase`, `production_order`, `sales_order`, `adjustment`) |
| `occurred_at`, `reason` | timestamp + optional note (required for ADJUSTMENT) |

**Rule:** `quantity_on_hand` is a cache of `Σ movements.quantity` per item; services maintain it inside the same write transaction; reconciliation job verifies.

### 2.10 Price calculator — `price_calculations` + `app_settings`

**`price_calculations`**: `id`, `product_id` FK nullable, `variant`, `channel`, `inputs_json` (w, t, q…), `constants_json` (P, F, E, D, R, C, N, CH, S, L, B), `results_json` (all intermediate + final values, exact scaled strings), `created_at`, `created_by`.  
**`app_settings`**: key/value JSON (pricing constants, supplier score weights, display currency `Toman`, fiscal-year start `1 Farvardin`, …) — validated via pydantic models per key.

### 2.11 Platform entities (detailed in later phases)

- **`users`** — auth (`owner`/`bookkeeper`/`auditor`/`ingest_api`), Argon2id hashes (Phase 5).
- **Accounting core** — `accounts`, `journal_entries`, `transaction_splits`, `fiscal_periods`, `audit_logs`, `exchange_rates` … (Phase 4; double-entry engine Phase 2).
- **Documents** — content-addressed (SHA-256) storage for proformas, receipts, uploads (Phase 5).
- **Ops** — `idempotency_keys`, `bank_import_batches`, `reconciliation_sessions`, `security_audit_logs` (Phase 4/5).

---

## 3. Relationship overview

```
suppliers 1───n inventory_items 1───n inventory_movements
    │ 1                      ▲ n
    └──n purchases 1──n purchase_lines ──┘
    └──n supplier_score_events

products 1───n product_materials n───1 inventory_items
products 1───n sales_order_lines
customers 1───n sales_orders 1───n sales_order_lines
sales_order_lines 1───n production_orders 1───n production_consumptions n───1 inventory_items
production_orders ──> inventory_movements (PRODUCTION_OUT / PRODUCTION_IN)
sales_orders      ──> inventory_movements (SALE_OUT)
products / orders ──> price_calculations
app_settings      ──> pricing constants, score weights
```

**Key FK behaviors:** delete `RESTRICT` for anything with history (suppliers with purchases, items with movements, products with lines); order lines cascade only while the order is `DRAFT`.

---

## 4. State machines

- **Sales order:** `DRAFT → CONFIRMED → IN_PRODUCTION → READY → SHIPPED → COMPLETED`; `CANCELLED` from any pre-`SHIPPED` state. Backward transitions forbidden (corrections via new orders/adjustments).
- **Production order:** `PLANNED → IN_PROGRESS → COMPLETED` (`CANCELLED` before completion).
- **Purchase:** `DRAFT → RECEIVED` (`CANCELLED` while DRAFT).
- **Reconciliation/ledger statuses** follow Phase 4 (`UNRECONCILED`/`CLEARED`/`RECONCILED`; `DRAFT`/`POSTED`/`VOIDED`).

---

## 5. Derived aggregates (dashboard & reports)

| Aggregate | Source | Used by |
|---|---|---|
| `quantity_on_hand` | Σ inventory_movements | inventory, alarms |
| Inventory value | Σ (qty × unit_cost) | landing chart, dashboard |
| Low-stock / days-of-stock | qty vs threshold + consumption rate | alarms feed |
| Sales per period | orders (non-cancelled) by `order_date` | reports, KPIs, trend |
| Production throughput | production_orders by completed_at | dashboard |
| Supplier total_score | weighted scores | leaderboard, suggestion |
| Receivables/payables | ledger (journal entries) | dashboard KPIs |
| COGS | ledger + movement unit costs | P&L |

---

## 6. Accounting integration touchpoints

| Operational event | Ledger effect (summary; exact templates in Phase 2/4) |
|---|---|
| Purchase received | Dr Inventory / Cr Cash-or-Accounts-Payable |
| Production completed | Dr Finished-goods (MODEL items) / Cr Raw-materials; production overhead (power/depreciation) to Expense/COSG |
| Sale completed | Dr Cash-or-Accounts-Receivable / Cr Revenue; Dr COGS / Cr Inventory |
| Adjustment | Dr/Cr Inventory + reason-coded expense account |
| Price calculation | **no** ledger posting (analytical only) |

---

## 7. Phase 4 handoff requirements

The full SQLite schema must: use STRICT tables with the conventions in §1; add `CHECK`s for enum/sign rules (esp. `inventory_movements` sign-by-type and split debit/credit exclusivity); keep `quantity_on_hand`/money caches transactionally consistent with their sources; index foreign keys and `(order_date, status)`-style report paths; and keep every rule in this document testable via pytest/Hypothesis.

---

## 8. Phase 4 persistence policy (implemented 2026-10-14)

**Money & TypeDecorators.** All money persists as scaled INTEGERs (×10 000; FX rates ×1e8). Central conversion lives in `app/money.py` (`to_scaled`/`from_scaled`, banker's rounding, `MAX_ABS_AMOUNT=1e14`, aggregate guard at 1e18) **and** in SQLAlchemy `TypeDecorator`s (`app/db_types.py`: `ScaledMoneyType`, `ScaledFxRateType`) used by the Phase 4 tables — Python sees exact `Decimal`, SQLite sees INTEGER. `float`/`bool` inputs raise `MoneyError`. Equivalent client-side helpers: `frontend/src/lib/money.ts` (decimal.js).

**Currency policy (Toman/Rial — resolved).** The ledger's canonical storage unit is the **Rial** (`base_currency="IRR"`, ISO 4217 in every `currency` column). The product displays **Toman** (`display_currency="IRT"`) with the fixed factor 1 Toman = 10 Rials applied **exactly once** at the presentation edge: `<Money />` divides by 10 (`rialToToman`), the journal form multiplies entered Tomans by 10 on submit (`tomanToRial`). Foreign currencies (USD/EUR/AED/TRY/GBP — `currencies` registry table) display as-is with their ISO code. The price calculator (`قیمت نهایی.xlsx` model) is Toman-native and passes `currency="TOMAN"` to `<Money />` to skip conversion.

**Versioning.** `journal_entries.version_id` / `accounts.version_id` are application-managed optimistic locks (service checks + `409 stale_version`) rather than SQLAlchemy `version_id_col`, because the ledger composes multi-row atomic postings and must control version bumps explicitly. The observable contract is identical.

**New schema (Alembic 0002_persistence).** `currencies`, `reconciliation_sessions` (+ `transaction_splits.reconciliation_session_id` FK `ON DELETE SET NULL`), `idempotency_keys`, `account_balance_snapshots`, rollup view `v_account_balances` (POSTED splits only), keyset index `ix_journal_entries_date_id (transaction_date DESC, id DESC)`, and FTS5 `search_fts` + 6 sync triggers (skipped gracefully when the SQLite build lacks FTS5).

**Idempotency.** `POST /api/v1/journal-entries` accepts `Idempotency-Key`: atomic claim + request-hash, stored response replay, `409 idempotency_key_reuse` / `idempotency_conflict` on misuse; failed (4xx) requests are not stored (retry re-executes).

**Pagination & search.** Registers use keyset/cursor pagination (`cursor` + `X-Next-Cursor`, stable `(transaction_date, id)` tie-breaker); OFFSET remains only for legacy callers. `GET /api/v1/search` runs FTS5 (unicode61, prefix tokens) with RapidFuzz re-ranking and a tested `LIKE` fallback (`?like=1` forces it).

**Reconciliation.** Sessions store account + statement date + beginning/ending balances (Decimals). `link_split` marks splits `RECONCILED` and links them to the session; `session_progress` compares the linked signed sum to `ending − beginning`; history is never overwritten.

**Backups.** Online backup API (`sqlite3.Connection.backup`), verification = `integrity_check` + `foreign_key_check` + **Alembic migration version** + ledger debit=credit. `create_backup_bundle` adds receipts copy + manifest and optional Fernet encryption (PBKDF2-HMAC-SHA256, 480k iterations, per-file salt). `scripts/backup_vira.ps1` supports `-PassphraseFile` and `-InstallScheduledTask` (daily Task Scheduler job).

**Benchmark (representative local data — 25 000 entries / 50 000 splits, 32 MB).** keyset page 0.15 ms · OFFSET @10k 0.29 ms · rollup view 42 ms · snapshot aggregation 35 ms · LIKE search 2.9 ms · FTS5 search 0.22 ms (median of 5, `scripts/benchmark_db.py`).
