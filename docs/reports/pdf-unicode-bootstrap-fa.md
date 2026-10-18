# bootstrap خصوصی PDF و قلم در مسیرهای Unicode — ۲۰۲۶-۱۰-۱۹

> **اثبات خصوصی موفق:** پیش‌آزمون مستقل و سپس ساخت تازه از سورس/رندر واقعی Unicode
> در دو فرایند تأیید شدند. این قبولی، ادغام مسیر عادی، نصب یا مجوز انتشار نیست.

## هدف و مرز اختیار

app، DLL، interpreter، پروفایل/LOCALAPPDATA، cache، TEMP و working directory
نامرتبط باید فارسی/Unicode و فاصله‌دار باشند. فرایند تازه همان state را دوباره
مصرف کند؛ PDF واقعیِ یک/چهارصفحه‌ای A4، وزیرمتن ۴۰۰/۷۰۰ و هر ۳۰ رقمِ فارسی، عربی
و لاتین با بازرسی فایل PDF بررسی شوند. نامزد از نصب و دادهٔ کاربر جداست.

این مرحله **مجوز انتشار، تغییر نصب، تغییر محاسبات یا بستن گیت حقوقی نیست**.
مرحلهٔ عادی staging، راه‌انداز عمومی، Inno، native delta/rollback، DB/schema و
نسخه/tag/release تغییر نکرده‌اند. پذیرش تجاری نصب طبق خواست کاربر به بعد موکول است.

## شکست‌های واقعی و تشخیص تفکیک‌شده

۱. تست ویندوز، سورس UTF-8 را با `read_text()` و پیش‌فرض CP1252 می‌خواند؛ traceback
بایت `0x81` در offset 3970 را نشان داد. اصلاح همان خواندن صریح UTF-8 بود؛ نه حذف
تست یا تغییر سراسری encoding محیط CI. اجرای **39170525117 / bd728bf** با هر پنج
job موفق است؛ این قبولیِ CI عمومی را نباید قبولیِ رندر Unicode دانست.
[رکورد تست](../dependencies/pdf-unicode-bootstrap-test-failure.json).

۲. اجرای بومی **39170525115 / bd728bf** واقعاً ۲۰ درخت را کامپایل و ۲۱ DLL را
ممیزی کرد، ولی رندر در WeasyPrint 70.0، `text/fonts.py:244` شکست خورد: تبدیل مسیر
فارسیِ فایل TTF موقت با `PREFERRED_ENCODING=cp1252`. اجرای private interpreter با
`-I -B -X utf8` و الزام صریح حالت UTF-8 این لایه را اصلاح کرد. نه ماژول WeasyPrint
monkeypatch شد و نه محیط تست‌های عادی به UTF-8 اجباری تغییر کرد.
[رکورد رندر](../dependencies/pdf-unicode-bootstrap-render-failure.json).

۳. پیش‌آزمون SDK در **39174213646 / b39c91b** باز هم شکست خورد، این بار با قلم
NULL در Pango. آزمون تشخیصی **39174537102 / cb81dcb** علت لایهٔ بومی را جدا کرد:
Python UTF-8 فعال و encoding صحیح بود، ولی `GetACP()` ویندوز هنوز **۱۲۵۲** بود.
دو `FcConfigAppFontAddFile` با مسیر فارسی هر دو FALSE، و با نسخهٔ کنترل ASCII
از همان TTFها هر دو TRUE شدند؛ شمار قلم‌های application به‌ترتیب صفر و دو بود.
کپی‌های ASCII فقط کنترلِ پیش‌آزمون، با configuration جدا و پاک‌شده پیش از رندرند؛
هیچ‌کدام fallback رندر یا شاهد ساخت از سورس نیستند.

۴. اصلاح private PE manifest در **39174821766 / 4cf8bf7** از مرحلهٔ embedding
گذشت، اما چاپ مسیر فارسی توسط interpreter توسعه در `build_manifest.py` با CP1252
شکست خورد. فقط فراخوانی همان harness خصوصی، `python -X utf8` شد؛ هیچ تست یا
assertion حذف و هیچ محیط عادی mask نشد.
[رکورد پیش‌آزمون و کنترل‌های بومی](../dependencies/pdf-unicode-bootstrap-preflight-failure.json).

## قرارداد bootstrap خصوصی

- configuration سندی با `FcConfigCreate`، XML حافظه‌ای UTF-8، `reset-dirs` و cache
  صریح ساخته می‌شود؛ directory قلم سیستم، include و config کمکی ASCII ندارد.
  مسیر `FONTCONFIG_FILE` عمداً ناموجود و فارسی است تا وابستگی پنهان به getenv رد شود.
- adapter فقط قرارداد بازبینی‌شدهٔ WeasyPrint **70.0** را می‌پذیرد. پیش از import
  بومی در ویندوز، هم Python UTF-8 mode و هم **process ACP 65001** الزامی‌اند.
- private CPython با `-I -B -X utf8` اجرا می‌شود؛ libffi ممیزی‌شده قبل از ctypes
  pin و callback صحیح/اعشاری کنترل می‌شود. وابستگی توسعه وارد interpreter نمی‌شود.
- فقط **کپی موقت و خصوصی** `python/python.exe` تغییر PE resource می‌گیرد: `mt.exe`
  خودِ Windows SDK ابتدا manifest اصلی را استخراج می‌کند و `activeCodePage=UTF-8`
  به همان تنظیمات می‌افزاید؛ manifest جاسازی‌شده دوباره استخراج و کنترل می‌شود.
  دو هش EXE، هر دو manifest، نسخه/هش ابزار و وضعیت Authenticode ثبت می‌شوند.
  این EXE را **نباید باینری دست‌نخوردهٔ upstream** معرفی کرد. SDK یا ابزار آن در
  payload توزیع نمی‌شود. مرحلهٔ معمول `stage_app_payload.ps1` تغییر نکرده است.
- baselineِ manifestِ **این payload خصوصی** پس از تغییر PE و افزودن native candidate
  دوباره ساخته می‌شود؛ دو worker باید همان baseline جدید را بدون تغییر نگه دارند.
  این نتیجه، آزمون updater نصب‌شده روی EXE تغییرکرده یا اثبات امضای انتشار نیست.
- قابلیت `activeCodePage` به Windows 10 نسخهٔ 1903 به بعد وابسته است؛ worker به‌جای
  فرض سازگاری، مقدار واقعی `GetACP()==65001` را بررسی می‌کند. خودِ Windows 10/11
  نصب‌شده، حداقل نسخهٔ محصول، notices مربوط به CPython و راهبرد امضای EXE هنوز
  موضوع بازبینی تولیدند؛ اجرای `windows-latest` همهٔ نسخه‌های ویندوز را اثبات نمی‌کند.
- مالکیت referenceهای Fontconfig/Pango صریح است. در پایان هر سند cacheهای سندی و
  font-map آزاد، اشاره‌گرهای آزادشده invalid و پوشهٔ موقت حذف می‌شود؛ خطای پاک‌سازی
  پنهان نمی‌شود. TTFهای موقت زیر TEMP فارسی باید دقیقاً هش دو وزیرمتن همراه app باشند.
- صفر قلم سیستم مربوط به **configuration فعال سند** است، نه ادعای اینکه هیچ کد
  آغازین کتابخانه هرگز configuration پیش‌فرض را بررسی نکرده است.
- TTFهای asset فقط read-only می‌شوند؛ این **شاهد ACL یا نصب غیرقابل‌نوشتن نیست**.
  reuse مسیر/state در فرایند دوم نیز ادعای cache hit دیسکی نیست.
- `render_pdf` فقط تزریق اختیاری داخلی دارد؛ پیش‌فرض و API HTTP همان قبلی‌اند.
  helper خصوصی به مسیر عادی برنامه متصل نشده است.

## پیش‌آزمون موفق، نه منشأ سورس

پیش‌آزمون **39175100427 / fa68e2a**، job **117816018002** موفق است: مقدار واقعی
ACP **۶۵۰۰۱**؛ Python/WeasyPrint UTF-8؛ هر دو query قلمِ فارسی TRUE و شمار قلم‌ها
دو؛ PDF واقعیِ یک/چهارصفحه‌ای و اجرای دوم از همان profile/state موفق شدند.

این job از SDK upstream با SHA256
`ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53`
و **۲۷ DLL** استفاده می‌کند، نه از ۲۱ DLL ساخته‌شده از سورس. artifact آن
`private-unicode-stock-sdk-preflight-no-dlls-not-source-proof` است و هرگز شاهد
منشأ ساخت تلقی نمی‌شود. شکست پیش‌آزمون مانع شروع ساخت پرهزینه می‌شود؛ قبولی‌اش
الزام ساخت مستقل از سورس را حذف نمی‌کند.

## شاهد مستقل ساخت از سورس

**[اجرای 39175100427 / fa68e2a](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39175100427) موفق**؛ job مستقل
`unicode-consumer`، شمارهٔ **117816508451**. هر دو job موفق‌اند.

- [شاهد از سورس](../dependencies/pdf-unicode-bootstrap-proof.json)،
  [دادهٔ کامل شاهد](../dependencies/pdf-unicode-bootstrap-evidence.json) و
  [پیش‌آزمونِ غیرمنشأ](../dependencies/pdf-unicode-bootstrap-preflight-proof.json).
- شاهد واقعی 9 قطعه، **88464 بایت**؛
  SHA256: `5396a1431461249a6c1b21832553cf1dc6ac0c96034e569728a99e7aec71abf0`.
- هر دو فرایند واقعاً ۲۱ DLL تازه را از payload فارسی بار کردند؛ Pango اجراشده
  `1.58.0-vira-local-source`، ctypes صحیح/اعشاری و نبود وابستگی توسعه تأیید شدند.
- Python UTF-8، encoding مسیر WeasyPrint و **ACP 65001** هر سه ثبت و بررسی شدند؛
  manifest اصلی CPython، جز افزودن activeCodePage، همان semantics را دارد.
- هر دو PDF در هر دو فرایند، وزیرمتن ۴۰۰/۷۰۰ و هر ۳۰ رقم دارند؛ TTFهای TEMP فارسی
  با هش asset تطبیق و پوشهٔ موقت هر سند پاک شد. configuration فعال صفر قلم سیستم
  و manifest خصوصی پس از restamp بدون تغییر باقی ماند. source envelope در پایان
  دوباره احراز شد. این‌ها قبولی نصب، امضای انتشار یا حقوق redistribution نیستند.

این job روی runner جدا، آرشیو دارای اعلانِ قبلی را با احراز producer/commit/
artifact/digest و manifest مستقل دریافت می‌کند. آرشیو
`b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2`
با cache باینری خاموش، پیش از وابستگی‌های app، دوباره ساخته می‌شود. ۲۰ درخت،
۲۱ DLL و Pango نشانه‌گذاری‌شده باید به **همین** ساخت، هر دو فرایند رندر و هش
ممیزی بومی متصل باشند؛ envelope سورس در پایان دوباره احراز می‌شود.

## کنترل‌های خودکار تا این لحظه

- **۶۲۶ تست بک‌اند** در اجرای کامل محلی موفق‌اند؛ دو کنترل دائمیِ شاهد هم اضافه شد.
  **۱۷** موردِ فایل bootstrap،
  به‌اضافه کنترل تزریق داخلی در تست renderer، به این مسیر مربوط‌اند.
- مجموعهٔ متمرکز PDF نیز **۲۶۸ تست موفق** دارد؛ این‌ها جای شاهد واقعی Windows نیستند.
- Ruff و Mypy برای **۸۵ فایل** موفق‌اند.
- Bandit مطابق gate موجود CI با `-ll` موفق است: صفر finding متوسط/شدید؛ اسکن بدون
  فیلتر ۲۳ finding کم‌اهمیت دارد، از جمله import سازندهٔ XML که XML ورودی نمی‌خواند.
  policy یا suppression تازه‌ای برای عبور دادن این مرحله اضافه نشده است.
- ممیزی MIT محدود به **۱۴ فایل** موفق است؛ helper، worker، workflow و QA تحت آن
  grant قرار نگرفته‌اند. مجوز کل برنامه عوض نشده است.
- Pango بومی در Linux این sandbox موجود نیست؛ آزمون mock یا نبود کتابخانه، شاهد
  رندر بومی محسوب نشده و تست شکست‌خورده skip نشده است.

## آنچه همچنان باز است

هر **شش گیت** حقوقی/فنی در policy باز می‌مانند: notices و بازبینی اجزا؛ حق واقعی
CRT؛ تکمیل بازبینی کیت/ابزار گیرنده؛ تحویل عمومی و پایدار سورس؛ EULA و تعویض DLL
در نصب؛ bootstrap عمومی/Inno/native update/rollback و پذیرش نصب‌شدهٔ معوق.

bootstrap خصوصی اکنون یک EXE با manifest تغییرکرده هم دارد؛ موفقیت آزمایش نه
مجوز حقوقی/امضای تولید آن است، نه اجازهٔ افزودنش به نصب فعلی. artifact خصوصیِ
۹۰روزه نیز تحویل پایدار و ناشناسِ سورس به گیرنده نیست.

## CI عمومی و ممیزی وابستگی

اجرای **39175100368 / fa68e2a** در `pip-audit` پیش از migrations/tests شکست خورد؛
چهار job دیگر موفق بودند. signed log از sandbox قابل دریافت نبود، پس علت اصلی
**نامعلوم** ثبت شده و نه آسیب‌پذیری و نه خطای موقتی به آن نسبت داده شده است.
ممیزی محلی بدون آسیب‌پذیری شناخته‌شده موفق شد، ولی جای failure در CI شمرده نشد.
فرمان audit و exit status اصلی حفظ، فقط ذخیرهٔ log و annotation محدود اضافه شد؛
اجرای بعدی **39176130737 / 152203e** واقعاً از gate ممیزی و بک‌اند گذشت.
[رکورد و پیگیری](../dependencies/pdf-unicode-bootstrap-dependency-audit-failure.json).

<!-- FINAL_CI_RESULT_PENDING -->
