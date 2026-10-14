# V.I.R.A — Product Specification (Phase 1)

> Phase 1 deliverable. Covers the main idea, module-level features, the live landing page, the dynamic dashboard, and the normalized Sales Price Calculations model derived from `قیمت نهایی.xlsx`. Context file: [`../project brief.md`](../project%20brief.md). Entity model: [`data-model.md`](data-model.md). Full compiled requirements: [`../MASTER_PROMPT.md`](../MASTER_PROMPT.md).
>
> UI is **Persian-only (`fa-IR`), RTL**, with **Jalali dates** and **Persian numerals**; monetary values display in **Toman** by default. Persian labels are given next to each concept and are the canonical UI strings (final wording may be polished in Phase 3/7 translation files).

---

## 1. Vision & Users

**V.I.R.A** is the accounting and operations app for a small 3D-printing business that sells produced models (via marketplaces such as Digikala and directly) and manages the raw materials (3D-printing filaments and packaging) used to produce them. It covers **Warehouse → Production → Orders → Invoice/Reports**, supervised by a fully dynamic dashboard, on top of a rigorous double-entry accounting engine.

**Roles** (enforced from Phase 5): `owner` (مدیر — full control), `bookkeeper` (حسابدار — entries/imports/reconcile), `auditor` (بازرس — read-only). Day-to-day users are the owner and one bookkeeper; the app must stay comprehensible to a non-accountant while keeping ledger-grade integrity underneath.

---

## 2. Module: Warehouse (انبار)

### 2.1 Warehouse item model

A warehouse item is any stocked good: **filament**, **produced model** (finished product held in stock), **packaging/supplies** (nylon, labels, chains), or **other**.

| Field (fa) | Field | Notes |
|---|---|---|
| نام فیلامنت / کالا | `name` | e.g. "فیلامنت PLA مشکی" |
| وزن | `weight` | weight per stock unit (g); for spools: net grams |
| موجودیت / واحد | `unit` | `GRAM` گرم, `KILOGRAM` کیلوگرم, `SPOOL` قرقره, `PIECE` عدد |
| رنگ | `color` | free-text color name (+ optional swatch) |
| قیمت | `unit_price` | purchase price per unit (Toman, exact) |
| تاریخ | `received_date` | date received (stored ISO, shown Jalali) |
| نام تأمین‌کننده | `supplier` | FK to supplier (نام + آدرس kept on the supplier record) |
| آدرس تأمین‌کننده | `supplier.address` | |
| موجودی | `quantity_on_hand` | derived from movements, cached on the item |
| آستانه هشدار | `reorder_threshold` | stockout alarm threshold |
| محل نگهداری | `location` | shelf/bin note |

Stock changes only through **inventory movements** (`PURCHASE_IN`, `PRODUCTION_OUT`, `PRODUCTION_IN`, `SALE_OUT`, `ADJUSTMENT`) — never by editing `quantity_on_hand` by hand (adjustments must create a movement with a reason).

### 2.2 Stockout / inventory-shortage alarm (هشدار موجودی)

- An item is **low-stock** when `quantity_on_hand ≤ reorder_threshold`; **out-of-stock** at `≤ 0`.
- Alarms surface on the dashboard banner, a dedicated «هشدارها» list (with Jalali dates, item, shortfall, suggested reorder quantity), and as chart highlights (red/amber) on the inventory widgets.
- Optional **days-of-stock estimate**: recent consumption rate from `SALE_OUT`/`PRODUCTION_OUT` movements → estimated days until stockout; sorts the alarm list by urgency.
- Each alarm suggests a reorder quantity: `max(reorder_threshold × 2 − quantity_on_hand, economic lot)` with the lot size configurable per item.

### 2.3 Supplier registry & suggestion (پیشنهاد تأمین‌کننده)

- Supplier fields: name, contact, phone, email, **address**, notes, active flag.
- **Scoring model** — the user scores each supplier on three criteria (0–10):
  - `price_score` قیمت, `quality_score` کیفیت, `delivery_score` زمان ارسال.
  - `total_score = w_p·price + w_q·quality + w_d·delivery`, weights configurable in settings; **default weights: price 40%, quality 35%, delivery 25%**.
  - Scores are recalculated on edit and optionally versioned over time (score history) so the dashboard can show score trends.
- **Suggestion engine** (per item / per restock alarm): rank suppliers who can supply the item (purchase history for that item or same category) by `total_score` (tie-break: latest successful delivery, then lowest last unit price). Show the top 3 with the score breakdown so the user sees *why*.
- Supplier purchase history (from `purchases`) feeds quality/delivery insights: average lead time, average unit price vs. market.

---

## 3. Module: Orders (سفارش‌ها)

### 3.1 Customers (مشتریان)

`full_name` نام کامل, `phone` شماره تماس, `address` آدرس, notes. Customers are reusable across orders; phone is the practical dedup key (manual merge tool later).

### 3.2 Sales orders

| Field | Notes |
|---|---|
| `order_number` | sequential, human-readable (e.g. `SO-1404-0007`) |
| `order_date` | stored ISO, shown Jalali |
| `customer_id` | FK |
| `status` | lifecycle below |
| lines | product, quantity, unit price, discount, variant (`PLAIN` / `CHAIN` «زنجیر دار»), line total |
| totals | subtotal, discount, grand total (exact Toman) |
| notes / source | e.g. Digikala order id, phone order |

**Status lifecycle** (Persian UI labels):

`DRAFT` پیش‌نویس → `CONFIRMED` ثبت‌شده → `IN_PRODUCTION` در حال تولید → `READY` آماده ارسال → `SHIPPED` ارسال‌شده → `COMPLETED` تکمیل‌شده  
Cancellation (`CANCELLED` لغو‌شده) allowed before `SHIPPED`; completed/cancelled orders are immutable (corrections via adjustments, consistent with the ledger rules).

### 3.3 Sales Proforma Invoice (پیش‌فاکتور فروش)

- Generated from an order (or standalone draft) with: company identity, customer info (Jalali date), line items (Persian numerals, Toman), totals, validity/terms notes, signature block.
- **Export: PDF** (WeasyPrint, RTL Persian typography, print-perfect) **and Word (.docx)** (`python-docx`, editable) — both named `Pish-Faktor-<order_number>-<jalali-date>`.
- Proforma generation is idempotent per (order, revision); documents are content-addressed (SHA-256) per the Phase 5 storage rules.

### 3.4 Sales reports (گزارش فروش)

- **Daily / Weekly / Monthly / Annual** views (Jalali calendar periods: week شنبه→پنجشنبه, month, fiscal year from 1 Farvardin), plus custom Jalali date range.
- Metrics: order count, items sold, revenue, discount, average order value; breakdown tables by product, customer, status, and channel.
- **Search & filter** on every view: free text (customer name, phone, order number, product), status multi-select, price range, product, channel. Filters live in URL search params (TanStack Router).
- Export report to PDF/Excel (Phase 3 wiring; spec here defines the data).

---

## 4. Module: Production (تولید)

### 4.1 Products & bill of materials

- **Product** = "product to sell" (مدل تولیدی): `sku`, name, description, `net_weight_g` (filament per unit), `print_hours_per_unit`, `has_chain_variant`, active flag.
- **BOM (`product_materials`)**: per unit, which warehouse items are consumed and how much (filament grams, nylon, label, chain if variant). The default BOM is generated from the pricing constants (see §4.3) and can be edited per product.

### 4.2 Production orders

- Created from order lines (or standalone for stock): product, quantity planned, variant, status (`PLANNED` برنامه‌ریزی‌شده → `IN_PROGRESS` در حال تولید → `COMPLETED` تکمیل‌شده / `CANCELLED` لغو‌شده), start/completion timestamps.
- **Consumption**: planned consumption = BOM × quantity; actual consumption recorded per material (`production_consumptions`) and posted to inventory as `PRODUCTION_OUT`; finished quantity posts `PRODUCTION_IN` for the product (now a warehouse MODEL item).
- If materials are insufficient, the production order is blocked and the shortage alarms fire — production is explicitly **based on order details and warehouse inventory**.
- Variance (actual vs planned consumption) is shown on the production order and feeds cost analysis.

### 4.3 Sales Price Calculations page (محاسبه قیمت فروش)

The calculator implements the Excel workbook `قیمت نهایی.xlsx`, **normalized** ("compile every relation and make it as perfect as you can"). All inputs are editable; constants live in `app_settings` (defaults below, taken from the workbook). All arithmetic is exact (`Decimal` / `decimal.js`), Toman.

#### 4.3.1 Inputs

**Constants (ثابتها) — defaults from the workbook:**

| Symbol | Name (fa) | Default | Unit |
|---|---|---|---|
| `P` | توان مصرفی پرینتر | 1.3 | kW |
| `F` | قیمت هر گرم فیلامنت | 3,000 | Toman/g |
| `E` | قیمت هر کیلو وات برق | 1,400 | Toman/kWh |
| `D` | استهلاک پرینتر در هر ساعت | 10,000 | Toman/h |
| `R` | ضریب سود (multiplier) | 2.5 | × |
| `C` | کمیسیون دیجی‌کالا | 13.1 | % |
| `N` | نایلون بسته‌بندی | 2,000 | Toman/unit |
| `CH` | حلقه و زنجیر | 8,000 | Toman/unit |
| `S` | هزینه ارسال محموله | 150,000 | Toman/shipment |
| `L` | هزینه لیبل | 8,000 | Toman/unit |
| `B` | بافر ریسک/مرجوعی | 10 | % |

**Product inputs:** weight `w` (g), print time `t` (h), quantity `q` (pcs), variant `v ∈ {plain, chain}` (زنجیر دار), channel `k ∈ {direct, marketplace}`.

#### 4.3.2 Normalized formulas

**Per-unit production cost:**
```
c_filament = w × F
c_energy   = P × t × E                 ← improved vs. sheet (sheet omitted P)
c_depr     = t × D
c_chain    = CH  if v = chain else 0
unit_production_cost = c_filament + c_energy + c_depr + c_chain
```

**Batch & delivery:**
```
batch_production_cost = q × unit_production_cost
c_ship_unit           = S / q
unit_delivery_cost    = N + L + c_ship_unit        ← label counted ONCE, nylon included
```

**Pricing (marketplace channel — Digikala):**
```
unit_sale_price    = unit_production_cost × R
unit_commission    = unit_sale_price × C / 100     ← variant-aware (sheet reused plain commission)
merchandise        = unit_sale_price + unit_commission
buffer             = merchandise × B / 100
unit_final_price   = merchandise + unit_delivery_cost + buffer
```
**Direct channel:** `unit_final_price = unit_sale_price + (optionally local delivery) + buffer` — no commission, no marketplace label.

**Batch totals** are always `q × unit_*` (the sheet mixed totals and per-unit values in `B32`).

#### 4.3.3 Mapping from the workbook & deliberate fixes

| Sheet cell | Sheet formula | Normalized | Deviation |
|---|---|---|---|
| B18 | `B13*B3` | `w×F` | — |
| B19 | `B4*B14` | `P×t×E` | **fix:** uses unused power constant `B2` |
| B20 | `B5*B14` | `t×D` | — |
| B22 | `B21/B15` | `S/q` | — |
| B24 | `B23+B22` | `N+L+S/q` | **fix:** includes unused nylon `B8`; label once |
| B25 | `SUM(B18:B20)` | `q×(unit cost)` | **fix:** explicit per-unit/batch scaling |
| E25 | `B25+B15*B9` | `q×(unit+CH)` | — |
| B28/E28 | `B25*B6` | `batch×R` | — |
| B29/E29 | `B28/B15` | `unit×R` | — |
| B31 | `B29*13.1/100` | `sale×C/100` | **fix:** references `C` (`B7`), variant-aware (sheet used plain `B29` for chain `E33`) |
| B32 | `B28+B24` | (removed) | **fix:** dimensional error (total+unit); batch totals defined uniformly |
| B33/E33 | `B29+B31` | `sale+commission` | — |
| B34/E34 | `B33+B23` | `+L` | — |
| B35/E35 | `B34+B24+B34*10%` | `merchandise+delivery+buffer` | **fix:** label not double-counted; buffer base = merchandise (`B` configurable) |

**Rounding:** compute exactly; round only for display (banker's rounding, whole Toman). Stored quotes keep full precision (scaled integers).

#### 4.3.4 Behavior

- Two parallel result columns (plain vs. chain), like the sheet's «زنجیر دار» column; quantity-aware per-unit and batch totals; live recalculation as the user types (decimal.js).
- Save a calculation as a **quote snapshot** (`price_calculations`: inputs, constants, results, Jalali timestamp) — attachable to a product (sets suggested price) or an order line.
- Print/export the calculation (PDF) for cost documentation.

---

## 5. Landing page (صفحه اصلی زنده)

A **live-looking** public-ish home (inside the app shell, first screen after login):

1. **Hero strip:** greeting (Persian, Jalali date), live KPIs: total inventory value (Toman), open orders, in-production count, low-stock alarm count — each with sparkline/trend.
2. **Warehouse inventory chart (نمودار موجودی انبار):** beautiful interactive ECharts — default horizontal bar of quantity-on-hand per item (top 10) with low-stock colored red/amber; toggle to donut of inventory **value** share by category (filament / models / packaging).
3. **Recent products (محصولات اخیر):** table/cards — name, color, weight, price (Toman, Persian numerals), Jalali date, stock badge — the "recent products with some details" requirement.
4. **Live behavior:** TanStack Query polling (30–60 s) with a subtle "زنده" pulse indicator; smooth chart transitions; no page reload. Fully responsive RTL; dark/light themes.

---

## 6. Dashboard (داشبورد پویا — supervises everything)

The dashboard is the **control surface** over all modules — "fully dynamic": user-configurable widgets, global filters, and direct actions.

**Global controls:** Jalali date-range picker (day/week/month/year presets), entity filters (status, product, customer, supplier), refresh/pause-live toggle.

**Widget set** (each can be shown/hidden and reordered; layout persisted per user in local store):

| Widget | Content | Actions |
|---|---|---|
| KPI cards | sales (today/week/month), receivables, production throughput, inventory value | drill-down |
| Sales trend | line/area chart (Jalali axis) | change period |
| Inventory health | stock levels + value; low-stock highlighted | open item, create restock |
| Alarms feed | stockout alarms sorted by urgency | acknowledge, suggest supplier |
| Orders pipeline | counts per status (funnel/bar) | open list filtered |
| Production board | active production orders, progress % | start/complete |
| Supplier leaderboard | total scores, trends | open supplier, edit scores |
| Price calculator shortcut | last quotes / quick calculate | open calculator |
| Reports quick links | daily/weekly/monthly/annual | open report |
| System health (owner) | backup status, update status (Phase 8), migration revision | ops actions |

Role-aware: auditors see read-only widgets; bookkeepers see operational actions; owner sees everything including system/ops.

---

## 7. Cross-module workflows

1. **Restock:** alarm → supplier suggestion → purchase (record supplier invoice) → `PURCHASE_IN` movements → inventory + journal entry.
2. **Make-to-order:** order `CONFIRMED` → production order(s) per line → consume materials → `PRODUCTION_IN` → order `READY` → `SHIPPED` → `COMPLETED` (COGS + revenue postings).
3. **Make-to-stock:** production order without a sales order (stock build-up), same movement flow.
4. **Pricing:** calculator quote → suggested product price → used as default unit price on new order lines (always overridable).
5. **Month close:** sales reports + inventory valuation + fiscal period close (Phase 4/6 tooling).

---

## 8. Acceptance criteria (Phase 1 done when…)

- [x] Main idea captured per module (Warehouse / Orders / Production) with attributes and features — this document.
- [x] Live landing page specified (§5) with inventory chart + recent products.
- [x] Core entities, fields, relationships defined — [`data-model.md`](data-model.md).
- [x] Sales Price Calculations relations compiled and normalized from `قیمت نهایی.xlsx` (§4.3).
- [x] `project brief.md` written with the actual selected stack and non-negotiable constraints.
