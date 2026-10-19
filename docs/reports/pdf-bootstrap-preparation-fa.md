# آماده‌سازی preflight راه‌انداز PDF متعلق به برنامه — ۲۰۲۶-۱۰-۱۹

> **این گام آماده‌سازی قرارداد است، نه فعال‌سازی startup نصب‌شده یا اثبات تازهٔ
> Windows/PDF.** DLL بارگذاری، سرور اجرا، دیتابیس migrate یا نسخه‌ای منتشر نمی‌شود.

## نتیجهٔ فنی

در `app/private_pdf_bootstrap.py` یک verifier متعلق به کد برنامه اضافه شد؛ وابستگی
به QA/script و import کتابخانهٔ ثالث ندارد. اکنون قراردادِ بررسی پیش از native
loading در خود app تعریف شده، اما launcher موجود هنوز آن را انتخاب نمی‌کند.
این کار زمینهٔ انتقال مسئولیت از caller خصوصی را آماده می‌کند، نه اینکه ادعا کند
این انتقال در runtime نصب‌شده انجام شده است.

دو API صریح و متفاوت داریم:

- `verify_private_plan`: بررسی فقط‌خواندنی فایل‌ها؛ قابل اجرا روی Linux و مستقل
  از Windows. **به‌تنهایی ترتیب import یا سلامت process را تأیید نمی‌کند.**
- `prepare_private_plan`: علاوه بر آن، guardهای process خصوصی را بررسی می‌کند؛
  Windows/CI، CPython بسته‌بندی‌شدهٔ 3.11 با `-I -S -B -X utf8`، نبود importهای
  حساس قبلی، مبدأ خود preflight/بستهٔ app/interpreter و مسیرهای خصوصی را لازم دارد.
  این API هم native loader یا entrypoint سرور نیست.

ورودی `PrivateBootstrapPlan` و خروجی `VerifiedPrivatePlan` داده‌ای و immutable‌اند:
مسیر payload/state و hashهای مستقل، فهرست مرتب hashهای DLL، مسیر preload و cache.
configuration factory، renderer callback یا فایل QA به‌عنوان ورودی نداریم.
خروجی capability برای عبور از بررسی‌های بعدی نیست؛ activator آینده باید دوباره
فایل‌ها و hashهای مورد انتظار را درست پیش از بارگذاری تأیید کند.

## چه چیزهایی بررسی می‌شوند؟

1. مسیر absolute بدون traversal؛ state و payload مجزا؛ state فقط تازه/خالی.
   فایل یا state موجود حذف و با دادهٔ کاربر جایگزین نمی‌شود.
2. SHA256 خارجیِ manifest و inventory، بدون محاسبهٔ دوباره و پذیرش خودکارِ digest
   نامعتبر؛ JSON تکراری/غیرمتناهی و اندازهٔ boolean به‌جای عدد پذیرفته نمی‌شود.
3. هر فایل baseline با اندازه/hash؛ **پوشش کامل فایل‌های payload**: Python یا DLL
   خارج از manifest نیز رد می‌شود، نه فقط فایلِ manifestشده‌ای که تغییر کرده است.
4. نام canonical، escapeهای POSIX/Windows، ADS، DOS device، case alias، فاصله/نقطهٔ
   انتهایی، symlink و reparse bit رد می‌شوند. برای بررسی reparse از `lstat` استفاده
   می‌شود تا دنبال‌کردن junction و حتی `exists` ناموفق، آن را پنهان نکند.
5. اعضای الزامی app/interpreter/دو TTF/CFFI؛ کد verifier در payload مطابق همین
   نسخه؛ version خصوصی و receiptِ interpreter با manifest تغییرکرده.
6. فعلاً **فقط SDK مستقل ۲۷ DLL** با SHA آرشیو pinشده، وضعیت توزیع مسدود، preload
   دقیق `libffi-8.dll` و بدون DLL اضافه/alias. **Source21 صریحاً رد می‌شود**؛ هیچ
   fallback یا تغییر نام `ffi-8.dll` نداریم. پشتیبانی سورس binding جداگانه می‌خواهد.
7. در API خصوصی، root/profile/state/CWD فقط زیر runner و با مسیر Unicode/فاصله؛
   prefix/executable و فایل module و `app.__path__` خارجی قبل از خواندن payload رد
   می‌شوند. `app.main`، CFFI، ctypes، WeasyPrint، Uvicorn یا site customization زودهنگام
   اجازهٔ عبور ندارند.

## آزمون‌های انجام‌شده و دامنهٔ آن‌ها

**۹۴ کنترل جدید** همگی داده/باینری **ساختگی** دارند: integrity، alias/escape، پوشش
manifest، state موجود، پیوند، hash مستقل، عدم fallback SDK/source، receipt، snapshot
پس از mutation، guardهای process و مبدأ کد/بسته. بیت reparse با stub آزموده شده،
نه junction واقعی NTFS.

در process تازهٔ `-I -S -B -X utf8` هم import خود module و هم اجرای verifier روی
payload ساختگی انجام شد؛ هیچ app، کتابخانهٔ ثالث، CFFI/ctypes/WeasyPrint یا DLLهای PDF وارد نشد. filesystem، env،
sys.path و TEMP در بررسی فقط‌خواندنی تغییر نکردند. مسیر مثبت `prepare` نیز با
flags/pathهای شبیه‌سازی‌شده کنترل شد؛ **این Windows واقعی نیست**.

- مجموعهٔ کامل: **۸۶۰ تست موفق در 88.67 ثانیه؛ صفر failure/error/skip**.
- Ruff موفق؛ Mypy برای **۸۷ فایل** موفق؛ گیت فعلی Bandit موفق.
- MIT همچنان **فقط همان ۱۴ فایل native-build**؛ شامل module/test جدید یا کل app نیست.
- [رسید محدود محلی](../dependencies/pdf-bootstrap-preparation-evidence.json) hash کد،
  شمار آزمون‌ها و مرزِ شبیه‌سازی/واقعی را صریحاً ثبت می‌کند.

یک خطای اولیهٔ تست از مقایسهٔ کل `sys.modules` بود: decoder استاندارد `utf-8-sig`
می‌تواند lazy وارد شود. assertion به نبود import حساس/ثالث و عدم تغییر حالت محدود
شد، نه ممنوعیت import استانداردِ مجاز؛ کنترل جداگانه در process تازه نیز برقرار است.
هیچ تست یا guard native حذف/skip نشده است.

## چیزهایی که هنوز ثابت نشده‌اند

- این قرارداد هنوز در caller/launcher واقعی wired نیست؛ ACP 65001، preload، DLL
  origin، lifetime و cleanup واقعی یا ساخت/PDF تازه از این module نتیجه نمی‌شود.
- receiptِ modified PE با فعال‌شدن واقعی ACP یکی نیست. hash امضا نیست؛ بررسی
  cooperative است، نه sandbox علیه مالک متخاصم، ACL/hardlink/TOCTOU یا تضمین NTFS.
- شواهد قبلی SDK/source مربوط به کد و baseline خودشان باقی می‌مانند؛ برای این
  preflight بازنام‌گذاری نشده‌اند. در این گام cold build یا native HTTP اجرا نشد.
- مرحلهٔ فنی بعدی، اتصال صریح و خصوصیِ activator به این قرارداد همراه با اثبات
  تازهٔ Windows است؛ پیش از import و بدون جایگزینی renderer. هنوز انجام نشده است.

## بدون تغییر در نصب و حقوق انتشار

رفتار پیش‌فرض factory همان legacy است؛ main/route/settings/env switch یا launcher
نصب‌شده تغییر نکرد. scriptِ staging دست‌نخورده است؛ چون app را معمولاً copy می‌کند،
module جدید نیز فایل عادی app خواهد بود، **اما هیچ startup آن را خودکار فعال نمی‌کند**.
Inno، updater، version/tag/release، داده، schema و محاسبات قیمت تغییری نکردند.

هر شش گیت بازند؛ policy/review فقط وضعیت **آماده‌سازی** را همسان ثبت می‌کنند و
native activation/Windows/source21 برای قرارداد جدید همچنان false است. مجوز CRT،
EULA، تحویل عمومی پایدار source، نصب/تعویض DLL/rollback native و پذیرش کاربر از این
کار نتیجه گرفته نمی‌شود. از کاربر نصب یا دادهٔ تست درخواست نمی‌شود.
