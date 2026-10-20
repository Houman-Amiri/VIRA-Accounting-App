# فاز ۲ از شش بخش باقی‌مانده — اتصال لانچر واقعی به startup متعلق به برنامه

**تاریخ: ۲۰۲۶-۱۰-۲۰ — تکمیل در محدودهٔ خصوصی SOURCE توافق‌شده**

> `scripts/start_vira.cmd` واقعی اکنون مسیر صریح خصوصی SOURCE دارد؛ migration، seed،
> factory، renderer، سرور foreground و shutdown متعلق به app هستند، نه QA.
> حالت پیش‌فرض نصب‌شده فعال نشده و این نتیجه مجوز انتشار یا پذیرش دستگاه کاربر نیست.

## پیاده‌سازی

`backend/app/desktop_entry.py` request و سه digest مستقل manifest/inventory/source audit
را کنترل می‌کند. preflight فقط‌خواندنی، marker خصوصی، رد reparse/symlink، قفل عمر
پردازه و قفل update پیش از import native/app انجام می‌شوند. activation سورس دوباره
همهٔ bindingها را در مرز بارگذاری بررسی می‌کند. workspace تازهٔ bootstrap برای هر
پردازه از state تجاری خصوصی و ماندگار جداست.

سپس migrator و seed واقعی، session secret ماندگار، factory واقعی و Uvicorn foreground
روی loopback اجرا می‌شوند؛ دو health endpoint کنترل و مرورگر اختیاری فقط پس از
readiness انتخاب می‌شود. در آزمون headless مرورگر باز نشده؛ این را آزمون بصری مرورگر
نمی‌نامیم. shutdown، cleanup و آزادشدن قفل ثبت می‌شود. QA فقط process/HTTP client
بیرونی است؛ callback یا factory/renderer جایگزین به app داده نشده است.

CMD خصوصی با DisableDelayedExpansion و Python بسته‌بندی‌شدهٔ `-I -S -B -X utf8`
کار می‌کند. بدنهٔ مسیر پیش‌فرض نسبت به فاز ۱ با SHA مستقل
`a385c16ae8eaf49a61b06f8016fc1b22deaa000bcb3bc01554b9ad8eb0229cf4` ثابت مانده است.

## اجرای واقعی Windows و نتایج

[اجرای 39437161409](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39437161409)
در commit اجرایی `f64649eee502d6a29547798e386f5572d3dd5e3c`، هر دو job موفق:
SDK/کنترل سریع جداگانه `118677276979` و سورس `118679715648`.

ساخت سرد از ۲۰ درخت با binary cache خاموش، audit مبدأ ۲۱ DLL، اجرای تابع Pango
`1.58.0-vira-local-source` و regressionهای قبلی موفق شدند. پس از اجرای CMD واقعی،
بستهٔ اعلان‌دار سورس دوباره بررسی و موفق شد. audit این اجرا:
`1b73804a34668b08f4c79af677d17842e4cc02cf10fca53a1f34029a12983630`.

- دو پردازهٔ واقعی PIDهای **2360 و 2380** با همان DB خصوصی و IDهای fixture؛
  session قبلی پیش از login جدید پذیرفته شد و secret حفظ شد.
- migration واقعی و seed نخست: ۶ currency، ۲۲ account و یک user؛ seed پس از
  restart: هر سه صفر. sentinel دادهٔ ارث‌رسیده و DB هنگام update مسدود حفظ شدند.
- **۸ PDF تازهٔ همین فاز** از HTTP واقعی، نه پاسخ HTML: چهار PDF در هر پردازه،
  تک‌صفحه و چهارصفحه، شامل دو درخواست client موازی. PDFهای regression قبلی در این
  هشت مورد شمرده نشده‌اند. peak واقعی native در هر پردازه **۱** بود؛ throughput
  هم‌زمان native اثبات نشده و قفل‌های محاسبه/DB تغییر نکرده‌اند.
- inspection مستقل: Vazirmatn وزن‌های ۴۰۰/۷۰۰ و glyphهای عددی مطابق verifier؛
  دو hash فونت، صفر system font در config خصوصی، resource مستقل هر سند و cleanup
  تمام font/cache/bootstrap TEMPها؛ هر دو shutdown graceful و قفل آزاد شده‌اند.
- مسیرهای فارسی، فاصله، `!` و `&`، فونت‌های منبع readonly، ACP واقعی 65001،
  `ffi-8.dll` سورس و DLLهای mapped از `native/pdf/bin` همان candidate کنترل شدند.
  `libffi-8.dll` داخلی CPython همان کتابخانهٔ Source21 نیست؛ rename یا alias نداریم.
- چهار negative واقعی، همگی پیش از native/app: manifest غلط، source audit غلط،
  instance هم‌زمان و update lock. احراز هویت، CSRF، SQLite route context و SPA واقعی
  نیز توسط HTTP client بیرونی کنترل شدند.

## شاهد کامل، بدون حذف license/copyright

[شاهد](../dependencies/pdf-desktop-source-http-evidence.json) **544380 بایت** دارد؛ SHA256:
`3eb97ba7c340e6d6fdb0326e8412a8d73d22591b28d9ab1727cc961a4b2e89cf`.
[proof و زنجیرهٔ احراز](../dependencies/pdf-desktop-source-http-proof.json) شامل hash
۱۶ فایل اجرایی از Git blob همان commit است؛ replay با LF canonical انجام می‌شود و
این hashها را hash فایل‌های staged با CRLF ویندوز معرفی نمی‌کنیم.

بودجهٔ محافظه‌کارانهٔ شاهد قبلی + inventory کامل، ۵۶ بخش لازم داشت؛ ظرفیت ۳۲ به ۶۴
در هشت step افزایش یافت و regression انتقال byte-for-byte پیش از build موفق شد.
با این حال سقف **۵۰ annotation برای کل job**، با وجود کمتر از ۱۰ notice در هر step،
باعث شد API فقط ۱۲ بخش نهایی این فاز را نگه دارد. job واقعی و artifact کامل موفق
بودند؛ این رخداد خطای اجرای برنامه یا PDF نبود.

بازیابی بدون تغییر کد اجرایی یا اجرای دوبارهٔ native از همان artifact انجام شد:
[39447134103](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39447134103)،
commit `695ceee2258841316ca3bc4a3b459e86acc4583b`، **۸ job مستقل موفق**.
هر job ZIP اصلی artifact `12277476098` را دانلود و SHA بایت‌های واقعی ZIP را با
metadata مستقل تطبیق داد:
`854f9cfe9f60073a381fb855a65a2c21c5c5d5cf4c0f90ae98c408f90d765888`.
همگی digest اصلی همان check بومی، شاهد کامل و binder اصلی در checkout ثابت f64649e
را دوباره کنترل کردند؛ سپس ۵۶ بخش یکتا از هشت check بازسازی شد و hash/تعداد بایت با
digest اصلی مطابقت کرد. ZIP در این workspace دانلود نشده؛ hash مستقل ZIP در jobهای
بازیابی انجام شده است، نه با نامیدن metadata به‌عنوان دانلود محلی. برای شاهد بزرگ
باید artifact کامل یا jobهای مستقل استفاده شود؛ افزودن step به یک job سقف ۵۰ را رفع نمی‌کند.

artifact دارای انقضای ۹۰روزه است؛ توزیع عمومی و پایدار corresponding source از آن
نتیجه نمی‌شود. هیچ inventory/license/copyright یا binding برای کوچک‌کردن شاهد حذف نشده است.

## شکست‌های حفظ‌شده و اصلاحات

1. `39416463306 / c09b77d`: ساخت‌نشدن پوشهٔ والد request در QA بیرونی، پیش از CMD؛
   صفر PDF جدید. [رسید](../dependencies/pdf-desktop-source-driver-failure.json).
   parents اصلاح و کنترل سریع CMD/مسیر قبل از build سرد اضافه شد.
2. `39423104695 / e3e617b`: startup انجام شد اما PDF اول HTML fallback بود؛
   [رسید](../dependencies/pdf-desktop-source-logging-failure.json). dictConfig پیش‌فرض
   Uvicorn، LifecycleFile متعلق به app را می‌بست؛ `ValueError: write to closed file`
   محلی بازتولید شد. `log_config=None` logging app را حفظ می‌کند؛ regression TCP واقعی
   با رویداد مصنوعی صریح اضافه شد. renderer، سیاست فونت و hash مورد انتظار ضعیف نشدند.
3. اجرای میانی `39431706305 / ba29f42` به‌سبب push اصلاح پیشگیرانهٔ انتقال، هنگام
   compile منسوخ/لغو شد؛ نه موفقیت native است و نه شکست سوم runtime.

## آزمون‌ها و مرز تحویل

- **945 تست backend موفق، 66.864 ثانیه، صفر failure/error/skip**؛ شامل ۲۶ replay/
  mutation شاهد، تست‌های startup، regression logging و انتقال کامل inventory.
  replay محلی، اجرای native محلی نیست؛ native از اجرای Windows بالا احراز شده است.
- Ruff، Mypy روی ۸۸ فایل، Bandit در gate موجود و کنترل MIT محدود به ۱۴ فایل موفق.
- CI commit اجرایی `39437161229` هر پنج job موفق؛ CI checkpoint نهایی docs/evidence
  جداگانه ثبت می‌شود. frontend/OpenAPI/Windows/Playwright را از تست backend نتیجه نمی‌گیریم.

مسیر نصب `D:\3D PRINT\VIRA-Accounting`، دادهٔ واقعی، version/tag/release، schema،
محاسبات و UI دست‌نخورده‌اند. تغییر فقط branch خصوصی SOURCE همان لانچر واقعی است؛
startup پیش‌فرض عمومی فعال نشده. کنترل‌ها cooperative هستند، نه ACL یا تضمین در
برابر مالک متخاصم کد؛ hash امضا نیست و stale lock خودکار حذف نمی‌شود.

**فازهای ۱ و ۲ در محدودهٔ توافق‌شده تکمیل شدند؛ فازهای ۳ تا ۶ باقی‌اند.** native Inno
clean install/delta/rollback با حفظ داده، تکمیل قانونی/CRT/EULA و source پایدار،
پذیرش نصب واقعی/مرورگر/Ctrl+C/بستن پنجره و انتشار فقط با اجازهٔ جداگانه باقی می‌مانند.
هر شش گیت توزیع باز است؛ MIT فقط همان ۱۴ فایل build است، نه کل برنامه یا حقوق CRT.
فاز ۳ آغاز نشده و نسخه‌ای منتشر نشده است.
