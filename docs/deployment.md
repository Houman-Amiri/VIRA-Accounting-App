# V.I.R.A — Windows-Native Deployment & Operations (Phase 6)

راهنمای استقرار و بهره‌برداری ویرا. **بدون Docker** — همه چیز بومی روی ویندوز
اجرا می‌شود. این سند مکمل [`docs/security.md`](security.md) است.

## 1. نسخه‌های پشتیبانی‌شده

| ابزار | نسخه | نصب |
|---|---|---|
| Python | 3.12 (3.11+ سازگار) | python.org یا winget |
| uv | آخرین (اختیاری ولی توصیه‌شده) | `pip install uv` / astral.sh |
| Node.js | 22 LTS | nodejs.org یا winget |
| pnpm | 9+ | `corepack enable` یا `npm i -g pnpm` |
| SQLite | 3.45+ (همراه Python) | — |
| Inno Setup 6 | برای ساخت نصب‌کننده (فاز ۸) | jrsoftware.org |

## 2. راه‌اندازی اولیه

```powershell
git clone https://github.com/Houman-Amiri/VIRA-Accounting-App
cd VIRA-Accounting-App
.\scripts\setup_windows.ps1
```

اسکریپت انجام می‌دهد: ساخت `.venv` و نصب وابستگی‌ها (`uv sync --frozen` یا pip)،
نصب وابستگی‌های فرانت (`pnpm install --frozen-lockfile`)، ساخت مسیرهای داده در
`%LOCALAPPDATA%\VIRA` (data, receipt_storage, backups, logs)، اعتبارسنجی SQLite
(≥ 3.37 برای STRICT tables)، و اجرای **چرخه امن مهاجرت** (بخش ۵).

راه‌اندازی / توقف:

```powershell
.\scripts\start_vira.bat      # بک‌اند روی http://127.0.0.1:8787 (+ SPA ساخته‌شده)
.\scripts\stop_vira.bat
```

- توسعه فرانت: `cd frontend; pnpm dev` (Vite روی 5173 با proxy به 8787).
- دیتابیس پیش‌فرض: `%LOCALAPPDATA%\VIRA\data\vira.sqlite3` — قابل تغییر با
  `SQLITE_DATABASE_PATH`. دیتابیس، پشتیبان‌ها، کلیدها و رسیدها **هرگز** داخل
  مخزن نیستند (`.gitignore` + `.gitattributes`).

## 3. وظایف زمان‌بندی‌شده (Task Scheduler)

**پشتیبان روزانه** (رمزگذاری‌شده):

```powershell
.\scripts\backup_vira.ps1 -InstallScheduledTask -TaskTime 02:00 -PassphraseFile C:\secure\vira-pass.txt
```

**اجرای هنگام ورود کاربر** (اختیاری):

```powershell
$action  = New-ScheduledTaskAction -Execute "$PWD\scripts\start_vira.bat"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
Register-ScheduledTask -TaskName VIRA-Startup -Action $action -Trigger $trigger
```

**سرویس ویندوز** (اختیاری): از یک wrapper نگهداری‌شده مانند **NSSM** با حساب
کم‌امتیاز استفاده کنید — هیچ‌گاه سرویس مبتنی بر container نسازید:

```powershell
nssm install VIRA "$PWD\.venv\Scripts\python.exe" "-m" "uvicorn app.main:app --host 127.0.0.1 --port 8787"
nssm set VIRA AppDirectory "$PWD\backend"
nssm set VIRA Start SERVICE_AUTO_START
```

## 4. ساخت تکرارپذیر (Reproducible Builds)

- بک‌اند: `uv sync --frozen` (قفل `uv.lock`) یا `pip install -e ".[dev]"`.
  پیش‌نیازهای بومی ویندوز: **WeasyPrint** به Pango/GTK رندر نیاز ندارد (فونت‌ها
  داخلی‌اند)؛ در صورت کمبود فونت فارسی، Vazirmatn را نصب کنید. OCR اختیاری:
  Tesseract (بدون آن، OCR محلی غیرفعال می‌شود — مسیر LLM فقط با opt-in).
  `python-magic`/Pillow برای اعتبارسنجی آپلودها؛ در ویندوز از امضای داخلی
  (`sniff_kind`) استفاده می‌شود و نیازی به libmagic نیست.
- فرانت: `pnpm install --frozen-lockfile` → `pnpm openapi-ts` → `pnpm lint` →
  `pnpm typecheck` → `pnpm build`.
- **هم‌گامی lockfile**: CI با `uv lock --check` و `pnpm install --frozen-lockfile`
  روی هر push/PR در صورت ناهمگامی `pyproject.toml`/`package.json` با lockfileها
  **با پیام واضح شکست می‌خورد** (وابستگی‌ها را بات بازنویسی نمی‌کند).
- **تولید تایپ‌های API**: `pnpm openapi-ts` از `backend/openapi.json`. جاب CI
  «OpenAPI contract is in sync» اسکیما را از یک FastAPI زنده (دیتابیس موقت)
  دوباره تولید می‌کند و در صورت تفاوت با فایل‌های کامیت‌شده شکست می‌خورد —
  تغییرات اسکیما همیشه در GitHub Web قابل مرور و review هستند.

**تولید مهاجرت Alembic** (نیازمند review و تست قبل از اعمال روی داده کاربر):

```powershell
cd backend
$env:SQLITE_DATABASE_PATH = "$env:LOCALAPPDATA\VIRA\data\vira.sqlite3"
..\ .venv\Scripts\python.exe -m alembic revision --autogenerate -m "add table x"
# → فایل جدید را در GitHub Web بازبینی کنید؛ CI باید سبز باشد؛ سپس با migrate_vira.ps1 اعمال کنید
```

## 5. چرخه امن مهاجرت پایگاه‌داده (§7)

```powershell
.\scripts\migrate_vira.ps1
# یا با گزارش JSON:
.\scripts\migrate_vira.ps1 -Report migration-report.json
```

ترتیب دقیق (پیاده‌سازی: `scripts/migrate_vira.py`):

1. **قفل تک‌فرآیندی** — فایل `*.migrate.lock` (SQLite advisory lock ندارد).
2. **پشتیبان آنلاین** با `sqlite3.Connection.backup()` در
   `%LOCALAPPDATA%\VIRA\backups\pre-migration-<timestamp>.sqlite3` +
   `PRAGMA integrity_check` روی خود snapshot.
3. `alembic upgrade head` — تک فرآیند، روی همان فایل دیتابیس.
4. **دروازه سلامت**: `PRAGMA foreign_key_check` + بازنگری Alembic مورد انتظار +
   تراز `sum(debits) = sum(credits)` — فقط در صورت موفقیت «migrated».
5. خطا ⇒ خروج غیرصفر + دستور restore تست‌شده.

**بازیابی (در صورت شکست مهاجرت):**

```powershell
# سرویس/برنامه را متوقف کنید (stop_vira.bat) سپس:
.\scripts\migrate_vira.ps1 -Restore "$env:LOCALAPPDATA\VIRA\backups"
```

`restore_bundle` ابتدا snapshot را verify (integrity_check) و سپس جایگزین
می‌کند؛ فایل قبلی با پسوند `.replaced-<timestamp>` نگه داشته می‌شود.

## 6. پشتیبان‌گیری رمزگذاری‌شده و «سیستم و عملیات» (§8)

- **زمان‌بندی‌شده**: Task Scheduler → `backup_vira.ps1` (بخش ۳) — snapshot آنلاین
  + کپی رسیدها + رمزنگاری (PBKDF2-480k + AES). آپلود به S3/خارجی فقط در صورت
  پیکربندی (`-Destination`)؛ پیش‌فرض فقط دیسک محلی/شبکه داخلی.
- **درون برنامه**: مسیر **«سیستم و عملیات»** در SPA (پس از احراز هویت مجدد/Sudo):
  نسخه و کامیت، بازنگری مهاجرت، وضعیت زمان‌بند، آخرین پشتیبان (زمان/حجم)،
  **«پشتیبان رمزنگاری‌شده اکنون»**، **«راستی‌آزمایی پشتیبان»** (restore به مسیر
  موقت + integrity/FK/تراز) و **«بررسی به‌روزرسانی»** (بخش ۷).
- API مربوطه: `GET /api/v1/system/status`، `POST /api/v1/system/backup`،
  `GET /api/v1/system/backup/download` (محافظت path-traversal)،
  `POST /api/v1/system/backup/verify` — همگی پشت Sudo.

## 7. «بررسی به‌روزرسانی» (§8، محرک فاز ۸)

`GET /api/v1/system/check-updates` فایل `latest.json` را از آخرین Release
گیت‌هاب می‌خواند و نسخه فعلی/جدید را نشان می‌دهد. جریان کامل نصب
به‌روزرسانی («نسخه جدیدی موجود است، دانلود و نصب شود؟» + دلتا + پشتیبان
قبل از به‌روزرسانی) در **فاز ۸** تکمیل می‌شود؛ در این فاز فقط وضعیت نمایش
داده می‌شود و هرگز دانلود/نصب خودکار انجام نمی‌شود.

## 8. GitHub Actions (§5) — بدون service container

| جاب | چه می‌کند |
|---|---|
| `backend` | ruff, mypy, bandit, pip-audit · `uv lock --check` · دیتابیس موقت + `alembic upgrade head` · pytest/Hypothesis (JUnit report) |
| `frontend` | `pnpm install --frozen-lockfile` · prettier, eslint, tsc · `pnpm audit` (دروازه critical) · Vitest · build + آپلود dist |
| `contract` | بازتولید `openapi.json`/`schema.d.ts` از اپ زنده و `git diff --exit-code` |
| `e2e` | Playwright (chromium) علیه uvicorn + Vite بومی |
| `windows-native` | smoke روی `windows-latest`: uv sync، مهاجرت، pytest، build |

**Release workflow** (`.github/workflows/release.yml`) فقط با تگ‌های annotated
`vX.Y.Z`: اجرای کل تست‌ها → build SPA → `scripts/package_release.ps1` (بسته
قابل حمل + `latest.json` + `SHA256SUMS.txt` + یادداشت فارسی) → کامپایل Inno
Setup (فاز ۸) → بسته‌های دلتا (فاز ۸) → آپلود artifact و انتشار GitHub Release.
`dependabot.yml` فقط برای `uv`، `npm` و `github-actions` تنظیم شده (بدون Docker).

**Secrets**: مقادیر محرمانه فقط در GitHub Actions Secrets یا Windows Credential
Manager / متغیرهای محیطی محدودشده خارج از مخزن — هرگز کامیت نمی‌شوند
(به [`docs/security.md`](security.md) §4 مراجعه کنید).

```powershell
# ذخیره رمز عبور پشتیبان در Credential Manager (مثال):
cmdkey /generic:VIRA-Backup /user:vira /pass:(Read-Host "Passphrase")
```

اگر از self-hosted runner استفاده می‌کنید: دسترسی مخزن/محیط را محدود کنید،
محیط production را محافظت‌شده بگذارید و runner را در معرض کد PRهای غیرقابل
اعتماد قرار ندهید.

## 9. لاگ‌ها، سلامت و دسترسی خصوصی (§9)

- **چرخش لاگ**: `backend/app/logging_setup.py` — RotatingFileHandler در
  `%LOCALAPPDATA%\VIRA\logs\vira.log` (۲ مگابایت × ۵ نسخه). لاگ‌ها بدون
  رمز/PII (pipeline حذف حساس در `security/redact.py`).
- **سلامت**: `GET /api/v1/health/live` (زنده) و `GET /api/v1/health/ready`
  (اتصال دیتابیس، pragmaها، بازنگری Alembic، مسیر رسیدها قابل‌نوشتن،
  invariantهای حسابداری، وضعیت زمان‌بند).
- **بازیابی پس از crash**: Task Scheduler با `RestartCount`/`RestartInterval`
  روی اکشن اجرایی، یا NSSM با `AppRestartDelay` (بخش ۳).
- **دسترسی**: پیش‌فرض loopback (127.0.0.1). برای دسترسی از راه دور از
  **Tailscale** استفاده کنید (Firewall ویندوز + MagicDNS) —
  جزئیات در [`docs/security.md`](security.md) §9. فایل SQLite و پورت‌های
  اضافه هرگز در معرض عموم قرار نمی‌گیرند.

### Phase 7 additions (Enhancements & Localization)

| Variable | Purpose |
|---|---|
| `STORAGE_PROVIDER` | `local` (default) or `s3` for receipt storage |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_SSE` | S3-compatible bucket (MinIO/R2/AWS); server-side encryption on write (`AES256` default); `GET /documents/receipts/{id}` issues a 300-s presigned redirect |
| `VITE_UMAMI_WEBSITE_ID`, `VITE_UMAMI_SCRIPT_URL` | Opt-in privacy-first Umami analytics (both must be set; zero-PII redaction wrapper) |

UI localization is Persian-only: react-i18next namespaces under `frontend/src/locales/fa/` (`common`, `ledger`, `reports`, `validation`) with no language switcher or numeral toggle; the fiscal year is the full Iranian year starting 1 Farvardin.
