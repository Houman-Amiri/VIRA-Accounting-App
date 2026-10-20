# فاز ۱ از شش بخش باقی‌مانده — bootstrap سورس متعلق به برنامه

**تاریخ: ۲۰۲۶-۱۰-۲۰**

> اتصال خصوصی به موتور ساخته‌شده از سورس، همراه با آزمون واقعی Windows، موفق شد.
> این فاز به معنی فعال‌سازی startup معمول، نصب روی دستگاه شما یا مجوز انتشار نیست.

## هدف و نتیجه

طبق توافق، این فاز تمامِ بخش اول را پوشش داد: پیاده‌سازی اتصال سورس، guardها، رفع
اشکال آزمون‌ها، ساخت سرد، regression و اثبات bootstrap/HTTP/PDF واقعی؛ نه تحویل
یک زیرمرحلهٔ آماده‌سازی به‌عنوان فاز مستقل.

API صریح `activate_private_source(plan)` اضافه شد. plan فقط با **digest خارجیِ
source audit** وارد mode سورس می‌شود؛ API قدیمی SDK سورس را رد می‌کند و API سورس
هم plan بدون audit را نمی‌پذیرد. در کد app هیچ import از QA/script، renderer callback
یا configuration factory وارد نشده است. مسیر نصب‌شده همچنان این API را انتخاب نمی‌کند.

## پیاده‌سازی و مرزهای کنترل

- اعتبارسنجی Source21 اکنون داخل `app/private_pdf_bootstrap.py` است: archive و فایل
  اعلان‌دار Pango، receipt manifest، ساخت از سورس محلی با binary cache خاموش، تابع
  تغییرکردهٔ اجراشده، ۲۰ درخت و owner/hash هر ۲۱ DLL با audit مستقل تطبیق داده می‌شوند.
- preflightهای فقط‌خواندنی قبلی حفظ شدند: hashهای مستقل manifest/inventory، پوشش
  کامل فایل‌ها، رد Python/DLL اضافه، alias/escape و symlink/reparse، مبدأ کد و app،
  CPython خصوصی 3.11، `-I -S -B -X utf8` و مسیر Unicode/فاصلهٔ runner/profile/state.
- در مرز activation دوباره بررسی انجام می‌شود؛ snapshot قبلی مجوز عبور نیست.
  CFFI پیش از ctypes/app/WeasyPrint، `ffi-8.dll` **سورس** را با مسیر کامل pin می‌کند؛
  ACP واقعی 65001، مبدأ preload و DLLهای inventory که mapped باشند کنترل می‌شوند.
- همان lifecycle مشترک، native preload و DLL-directory handle را تا پایان body
  نگه می‌دارد و env/path/TEMP را بازمی‌گرداند. native object/handle از API خارج نمی‌شود.
  bootstrap workspace هر process تازه است؛ stateِ DB در restart مجزا و ثابت می‌ماند.
- نام بعضی helperهای قدیمی SDK برای سازگاری باقی مانده؛ **role و audit digest سورس
  مستقل و صریح‌اند**. `ffi-8.dll` سورس با `libffi-8.dll` احتمالی CPython یکی نیست؛
  هیچ rename/alias یا استنتاج منشأ callbackهای ctypes انجام نشده است.

native moduleهای importشده و DLLهای OS پس از scope unload نمی‌شوند؛ ورود تازه
process تازه می‌خواهد. این بررسی cooperative است، نه تضمین ACL/hardlink/TOCTOU
در برابر مالک متخاصم کد. hash هم امضا نیست.

## اجرای واقعی مستقل Windows

[اجرای 39388243191](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39388243191)،
commit `88180ea9ad6027c27533b9bd87187ec63c0a3ed3`، هر دو job موفق‌اند:

1. preflight واقعیِ SDK در VM جدا، با bootstrap متعلق به برنامه؛
2. job سورس `118514621733`: احراز producer/آرشیو اعلان‌دار، استخراج و کامپایل سردِ
   ۲۰ درخت بدون binary cache؛ auditِ ۲۱ DLL و اجرای Pango با مقدار
   `1.58.0-vira-local-source`؛ regressionهای قبلی؛ سپس mode جدید bootstrap سورس.

SDK در job سورس باینری جایگزین نبود. host tools و downloadهای ساخت مجازند؛ از این
اجرا offline یا bitwise reproducibility نتیجه نمی‌گیریم.

archive همان `b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2`،
فایل اعلان‌دار Pango همان
`a530b81e21d8799996032c68398651ec802d62017bac88c6c9d3b7cebd89719a` و kit manifest
همان `784c8d196ad0da899e7d6b65d26aff4d4bf9bb00551526692cda9b47c43c2023` است.
**پس از bootstrap و HTTP جدید نیز envelope سورس دوباره تأیید شد.**

### نتیجهٔ mode جدید، جدا از regressionها

- PIDهای واقعی **6792 و 8708**، دو bootstrap workspace تازه؛ همان SQLite و IDهای
  سفارش در restart. **۸ PDF جدید واقعی**: ۴ سند در هر process، ۱/۴ صفحهٔ A4.
- route عادی، factory/migrator/lifespan و Uvicorn واقعی روی TCP loopback؛ login،
  CSRF، رد دسترسی بدون مجوز و login غلط، SPA ساخته‌شده، OpenAPI و shutdown طبیعی.
- renderer خود app، بدون جایگزینی callableها یا config factory از QA؛ hash دو TTF،
  وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم Regular از سه مجموعه و ۱۰ فارسی Bold، صفر قلم سیستم،
  font/cache مستقل و cleanup هر ۸ سند؛ inspection بیرون process app انجام شد.
- mappingِ ۲۱ DLL، ACP 65001، UTF-8/no-site/isolated و بازگردانی env/path/TEMP و حذف
  TEMP bootstrap کنترل شدند. baseline خصوصی در هر دو process سالم ماند.
- **پنج negative واقعی**: نبود no-site، ctypes زودهنگام، inventory digest غلط،
  Python خارج از manifest، و source-audit digest غلط؛ همگی بدون receipt موفق رد شدند.
- دو client موازی، اما peak واقعی چرخهٔ سند در هر دو process **۱** بود. قفل
  `BEGIN IMMEDIATE` و محاسبات تغییر نکردند؛ native throughput موازی ادعا نمی‌شود.

PDFهای regressionِ legacy QA و app-owned قبلی روی همین build جدا اجرا شدند؛ به
شمار ۸ PDFِ bootstrap جدید اضافه نشده‌اند و شواهد تاریخی بازنام‌گذاری نشده‌اند.

## اصالت شاهد و محدودیت دریافت artifact

[شاهد مستقل](../dependencies/pdf-bootstrap-source-http-evidence.json) **119672 بایت**،
SHA256 `3c134b431fe977f2937e84b6139ec3daa19517c407cf5a6de904bdbeb2043a5d` است.
۱۰ بخش annotation کامل و digest مستقل از همان check/job/head احراز شد.
[provenance](../dependencies/pdf-bootstrap-source-http-proof.json) به metadata artifact
شمارهٔ `12250199759` وصل است؛ **ZIP در sandbox مستقلاً دانلود یا hash نشده است**.

SHA256 audit native:
`7b95ee89d0319570f8a3a7dcd18173dbce2ea5fdc0c524e0276c61a357f4e358`.
فیلدهای لازمِ inventory کامل اعتبارسنجی و در شاهد projection شده‌اند؛ تکرار متن
copyright/receipt حذف شده، نه bindingهای ۲۰ درخت/۲۱ DLL. inventory کاملِ byte-hashed
در artifact باقی است. hash کد در provenance مربوط به bytes canonical مخزن است،
نه ادعای فایل PS1 با CRLF در payload ویندوز.

## آزمون‌ها و گیت‌های خودکار

۲۳ کنترل تازهٔ سورس **ساختگی** هستند: schema/integrity، جلوگیری از اختلاط SDK/source،
عدم fallback، notice/archive/tree/owner/hash/version/cache، audit/digest/negative،
ترتیب workflow و pin سورس. یک تست دیگر integrity شاهد واقعیِ ضبط‌شده را می‌سنجد؛
pytest خودش Native Windows یا cold build تازه تولید نمی‌کند.

**۹۰۵ تست کامل، 95.02 ثانیه، صفر failure/error/skip**. Ruff، Mypy برای ۸۷ فایل،
گیت موجود Bandit و MIT۱۴ موفق‌اند. SDK مستقلِ همین کد `39388243073` و CI عادی
`39388243225` با هر پنج job موفق‌اند. [رسید checkpoint و آزمون‌ها](../dependencies/pdf-bootstrap-source-checkpoint-ci.json).
commit نهاییِ witness/docs نیز جداگانه تا نتیجهٔ CI خودش پیگیری می‌شود.

## شکست نهاییِ حفظ‌شده و اصلاح آن

اجرای CI نهایی `39394669426 / aee483d` **ناموفق** بود؛ چهار job موفق و Windows
در تست بازخوانی شاهد شکست خورد. [رسید و annotation اصلی](../dependencies/pdf-bootstrap-source-final-ci-failure.json)
حفظ شده است. بازسازی audit در تست با `write_text` روی Windows، newline را از LF
به CRLF تبدیل می‌کرد؛ نه فایل native و نه شاهد اصلی تغییر نکرده بودند.

تست اکنون bytes دقیقِ UTF-8/LF را با `write_bytes` می‌نویسد؛ expected digest همان
`7b95ee89...` مانده است. هیچ skip یا کاهش کنترل نداریم. مجموعهٔ کامل ۹۰۵تایی دوباره
موفق شد و CI کامل تکرار می‌شود. اجرای واقعی سورس `39388243191` همچنان موفق است؛
این شکستِ تست را به آن نسبت نمی‌دهیم و اجرای ناموفق CI را موفق بازنام‌گذاری نمی‌کنیم.

## وضعیت شش بخش توافق‌شده

| بخش | وضعیت |
|---|---|
| ۱ — اتصال bootstrap به موتور سورس و اثبات خصوصی Windows | انجام شد |
| ۲ — یکپارچه‌سازی با راه‌انداز واقعی برنامه | هنوز شروع نشده |
| ۳ — نصب و native delta/rollback بدون از دست‌رفتن داده | باقی است |
| ۴ — نهایی‌کردن شروط حقوقی و بستهٔ توزیع | باز؛ قابل پیگیری موازی |
| ۵ — آزمون روی نصب واقعی شما | طبق خواستهٔ شما موکول به پایان کارهای خودکار |
| ۶ — انتشار نسخهٔ بعد، پس از یادداشت فارسی و اجازهٔ شما | مجاز نشده |

این شش بخش کاری با شش گیت حقوقی/توزیع ثبت‌شده یکی نیستند: **هر شش گیت همچنان
بازند**. پذیرش همین فاز، تأیید CRT/EULA، حداقل Windows/امضا، تحویل عمومی پایدار
source، تعویض DLL نصب‌شده، native Inno/delta/rollback یا پذیرش کاربر نیست.

main/factory/route/settings، راه‌انداز نصب‌شده و stage script، version/tag/release،
schema، اطلاعات و محاسبات قیمت تغییر نکردند. stager موجود فایل‌های source را معمولاً
copy می‌کند، ولی هیچ startup معمول این mode را انتخاب نمی‌کند. MIT فقط همان ۱۴
فایل native-build است، نه کل app/QA. از کاربر نصب، حذف برنامه یا دادهٔ تست نخواستیم.
