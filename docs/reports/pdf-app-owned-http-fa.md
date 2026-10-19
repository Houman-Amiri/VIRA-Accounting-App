# HTTP واقعی Windows با مدیریت قلم متعلق به برنامه — ۲۰۲۶-۱۰-۱۹

> هر دو مسیر مستقل SDK و سورس با مدیریت قلم متعلق به app **موفق‌اند**؛ فقط
> CI خصوصی، نه startup عادی نصب‌شده، مجوز انتشار یا پذیرش کاربر.

## چه چیزی دیگر تزریق QA نیست؟

bootstrap خصوصی همچنان خارج از startup نصب‌شده است: baseline و hashهای مستقل،
CPython خصوصی با manifest تغییرکرده، `-I -S -B -X utf8`، ACP 65001، preload با
مسیر کامل و مبدأ native کنترل می‌شوند. تنها بعد از این کنترل‌ها، worker به
factory واقعی `PrivatePdfPolicy` داده‌ای می‌دهد. renderer دقیقاً `PdfRenderer`
خود app است و context/configuration در خود service ساخته و بسته می‌شود.

در این مسیر **نه `pdf.render_pdf` جایگزین می‌شود، نه configuration factory از QA
تحویل داده می‌شود**. هویت سه callable قبل/بعد HTTP مقایسه می‌شود؛ محل کدِ اصلیِ
آن‌ها زیر app/services baseline است. برای تابع contextmanager، `inspect.unwrap`
محل تعریف اصلی را بررسی می‌کند، نه wrapper استاندارد `contextlib.py` را.

مشاهده‌گر صرفاً `logging.Handler` است و رویدادهای plain-valueِ started/completed/
failed را می‌خواند؛ شیء configuration، C pointer، template/context مشتری، cookie
یا credential به payload رویداد سپرده نمی‌شود؛ رویداد failed می‌تواند traceback
استانداردِ خطا را نیز همراه داشته باشد، بدون dump کردن locals. رویداد completed پس از cleanup هر دو منبع
font و cache ثبت می‌شود. handler جایگزین رفتار renderer نیست؛ این مدل همکاری و
baseline، sandbox امنیتی در برابر مالکِ متخاصم کد/log نیست.

## شواهد SDK، جدا از سورس

[اجرای 39243690293](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39243690293)،
commit `66e3b8d575be879b574ec1c0c3328e74b23b7ce2` و job `118030332960` موفق‌اند.
[شاهد](../dependencies/pdf-app-owned-sdk-http-evidence.json) **43918 بایت**، SHA256
`43c6783a9881c9313a1ff4ddb6b5e594400de36a3b1473fad2ab78e3035e5270`، از دو بخش
annotation همان check/job با digest مستقل بازیابی شد. [provenance](../dependencies/pdf-app-owned-sdk-http-proof.json)
به artifact metadata شمارهٔ `12182607402` و همان head متصل است. ZIP در sandbox
دانلود/به‌طور مستقل hash نشده است؛ این را با تأیید محتوای ZIP یکی نمی‌دانیم.

دو PID واقعی `2804` و `2332`، همان DB و ID سفارش‌ها، migrator/factory/lifespan/
Uvicorn واقعی روی TCP loopback، login و CSRF، SPA ساخته‌شده و OpenAPI کنترل شدند.
چهار PDF در هر process، مجموع هشت PDF واقعیِ یک/چهارصفحه‌ای A4، از route عادی
دریافت و بیرون app با inspector بررسی شدند؛ HTML موفقِ HTTP به‌جای PDF قبول نشد.

وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم ASCII/فارسی/عربی Regular و ۱۰ فارسی Bold، SHA دو TTF،
صفر قلم سیستم فعال و پاک‌سازی font/cache هر هشت سند موفق‌اند. هر سند cache و font
folder مستقل داشت. دو درخواست client موازی، ولی peak واقعی چرخهٔ سند در هر دو
process **۱** بود؛ قفل `BEGIN IMMEDIATE` تغییر نکرد و throughput یا دو native render
هم‌زمان ادعا نمی‌شود. SDK همان ۲۷ DLL / Pango 1.58.2 است؛ **سورس را ثابت نمی‌کند**.

## ساخت تازهٔ سورس و همان HTTP متعلق به app

[اجرای 39243690330](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39243690330)، commit `66e3b8d575be879b574ec1c0c3328e74b23b7ce2`، هر دو job موفق؛
job سورس `118031848901`. ابتدا VM جداگانهٔ preflight SDK؛ سپس احراز producer/آرشیو
اعلان‌دار و **کامپایل تازهٔ۲۰ درخت با binary cache خاموش**، audit مستقل۲۱ DLL و
اجرای function تغییرکردهٔ Pango=`1.58.0-vira-local-source`. SDK در job سورس نقش
باینری جایگزین ندارد؛ host tools/downloads هنوز مجازند، پس offline/bitwise نیست.

archive همان `b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2`،
فایل اعلان‌دار Pango `a530b81e21d8799996032c68398651ec802d62017bac88c6c9d3b7cebd89719a`
و manifest `784c8d196ad0da899e7d6b65d26aff4d4bf9bb00551526692cda9b47c43c2023` است.
هر hash/owner DLL و hash/count درخت به audit مستقل و candidate baseline وصل است.

مسیر قدیمیِ QA به‌عنوان regression روی همان build جداگانه اجرا شد؛ بعد mode جدید
app-owned با **دو process دیگر** و state خصوصی خودش اجرا شد. سند/DB مربوط به هر
دو mode مخلوط نمی‌شود؛ هشت PDF regression به شمار هشت PDF app-owned افزوده نمی‌شوند.
پس از اجرای جدید، envelope سورس دوباره احراز شد.

- PIDهای app-owned سورس `7372` و `8344`، DB/IDها
  ثابت؛۸ PDF۱/۴صفحه‌ای، وزیرمتن۴۰۰/۷۰۰،۳۰/۱۰رقم، صفر قلم سیستم، hash asset و
  پاک‌سازی font/cache همان معیار SDK را گذراندند. peak واقعی۱ در هر process.
- [شاهد سورس](../dependencies/pdf-app-owned-source-http-evidence.json)، **118067 بایت**،
  SHA256 `68846c77f82cd4ebfb4bbc6177cfce8a53cd3249bcc23c7ec730aed36a4beadf`؛ 10 بخش کامل با
  digest مستقل از annotationهای همان check/job احراز شد. [provenance](../dependencies/pdf-app-owned-source-http-proof.json).
- audit native SHA256: `447f7c3ca3635f44a859fbc993cb4aa4f3120f06f6af1c692080a2c86b7485b8`؛ API artifact
  `12184648677` به همان head متصل است؛ ZIP مستقلاً در sandbox دانلود نشده است.
- هر۲۱ DLL از native/pdf/bin خصوصی بارگذاری شدند؛ callbackِ ctypes به معنی استفاده
  از `ffi-8.dll` سورس نیست. no-site/isolated/UTF-8/ACP65001، baseline کامل و هر سه
  negative واقعی بدون no-site/import زودهنگام/digest غلط در mode جدید کنترل شدند.

SDK۲۷/1.58.2 و سورس۲۱/1.58.0-vira-local-source **دو شاهد مستقل** دارند. در مجموع
**۱۶ PDF app-owned واقعی**؛ نه بازنام‌گذاری PDFهای QA یا شاهد تاریخی.

## آزمون‌ها و CI

۱۷ کنترل جدید اجرای خصوصی/observer/schema/guard،۲ schema سورس کاملاً synthetic و
۲ کنترل شاهد واقعیِ immutable؛ **۷۶۶ بک‌اند**، Ruff/Mypy۸۶/Bandit گیت موجود و MIT۱۴
موفق‌اند (اجرای کامل نهایی: 91.45 ثانیه، بدون skip/error/failure). syntheticها از schema تاریخی فقط برای قرارداد استفاده می‌کنند و artifact
native تازه نمی‌سازند. failure محلیِ دو تست ثبت log با فعال/restore صریح capture
اصلاح شد؛ tests skip، pin ضعیف، یا تغییر قفل/محاسبه نداریم. CI عادی همان کد اجرایی
و regressionهای SDK جدا از دو native app-owned workflow بررسی شدند؛ commit بعدیِ
صرفاً witness/docs نیز تا نتیجهٔ CI خودش پیگیری می‌شود.


[رسید CI کد اجرایی و regressionها](../dependencies/pdf-app-owned-http-checkpoint-ci.json)
حفظ شده است: CI عادی `39243690469 / 66e3b8d` هر پنج job موفق؛ HTTP legacy SDK
در همان head و launcher legacy SDK در fb331 نیز موفق‌اند. source supersededِ
`39242791683 / fb331` لغوشده است، نه موفق؛ شاهد سورس فقط اجرای تازهٔ 66e3 است.

## شکست حفظ‌شده و اصلاح واقعی

اجرای `39242791845 / fb331f5` ناموفق است. پاسخ‌های چهار PDF در log دیده شدند ولی
worker در کنترل نهاییِ `audit.active` با `AttributeError` شکست خورد؛ external
inspection کامل، restart یا workflow موفق از این تلاش نتیجه گرفته نمی‌شود.
[رسید و traceback اصلی](../dependencies/pdf-app-owned-http-worker-failure.json)
حفظ شده‌اند. observer اکنون همان شمارنده را از مجموعهٔ lifecycleهای فعال برمی‌گرداند؛
regression صفر→فعال→تکمیل→صفر اضافه شد. هیچ کنترل PDF، cleanup یا guard کاهش نیافت.

اجرای کامل محلی ابتدا دو خطای تست ثبت log داشت: Alembic `fileConfig` می‌تواند
loggerهای ازپیش‌ساخته را غیرفعال کند. در caller خصوصی، capture به‌صراحت logger
تشخیصی را فعال و سپس level/disabled/handler را restore می‌کند؛ انتخاب renderer
یا native config برای رفع این خطا تغییر نکرد. caller در خود app hook اجرایی ندارد.

## محدودهٔ اثبات و توقف‌های حقوقی/نصب

default factory بدون policy همان `LEGACY_DEFAULT` است؛ انتخاب خصوصی از env،
HTTP، settings یا UI نداریم. launcher نصب‌شده، staging معمول، نسخه، tag، release،
Inno/updater، داده و محاسبات دست‌نخورده‌اند. تغییر این مرحله در private service/
caller/observer و خود آزمون‌هاست؛ عادی‌بودن startup تولید، امضا، حداقل OS، EULA/
تعویض DLL در نصب، native delta/rollback یا پذیرش کاربر نتیجه گرفته نمی‌شود.

هر شش گیت بازند؛ MIT همان ۱۴ فایل native-build است، نه کل app یا service/QA جدید.
artifact خصوصی ۹۰روزه تحویل عمومی پایدار نیست. callbackهای ctypes به‌تنهایی منشأ
FFI سورس را ثابت نمی‌کنند: `ffi-8.dll` سورس با `libffi-8.dll` مجزای احتمالی CPython
یکی نیست و فایل‌ها rename/alias نمی‌شوند. از کاربر نصب یا دادهٔ تست درخواست نمی‌شود.
