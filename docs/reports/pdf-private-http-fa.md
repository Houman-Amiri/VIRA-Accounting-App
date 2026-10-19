# راه‌اندازی خصوصی backend و PDF واقعی از HTTP — ۲۰۲۶-۱۰-۱۹

> **راه‌اندازی واقعی backend و PDF از HTTP خصوصی در ویندوز موفق شد.**
> scope فقط SDK پین‌شده و adapter تزریقی همان process است؛ نه startup عادی نصب.

## محدوده و مسیر اجرا

entry قبلی فقط با `--http-proof` به worker ثابت و hash-بررسی‌شدهٔ HTTP می‌رود؛
بدون این flag، همان worker قبلی فعال است. مسیر target دلخواه، shell evaluation،
sitecustomize یا تغییر راه‌انداز نصب‌شده وجود ندارد. حالت HTTP هم همان `-I -S
-B -X utf8`، CPython خصوصی ۳٫۱۱، baseline و inventory با digestهای خارجی، SDK
پین‌شدهٔ **۲۷ DLL**، libffi پیش از ctypes/app و ACP واقعی **۶۵۰۰۱** را لازم دارد.
فایل worker جدید، app/main و migrator نیز باید در baseline باشند.

پس از bootstrap، worker در همان process موارد زیر را اجرا می‌کند:

1. داده، SQLite، receipt، log، TEMP و cache کاملاً زیر پروفایل فارسیِ runner؛
   مهاجرت واقعی Alembic با migrator موجود، نه `create_all` و نه DB واقعی کاربر.
   حساب مالک فقط با رمز تصادفی مخصوص همین QA seed می‌شود؛ رمز/cookie/DB در artifact
   قرار نمی‌گیرند. scheduler خاموش است و تنظیمات داده به مسیر خصوصی محدودند.
2. **create_app واقعی و Uvicorn واقعی**، socket TCP loopback با port سیستم، lifespan
   روشن و خروج graceful. TestClient/ASGITransport جای سرور استفاده نشده‌اند.
3. GET سلامت live/ready، revision مهاجرت، SPA ساخته‌شده و OpenAPIِ route واقعی؛
   GET پیش‌فاکتور بدون login، login غلط و POST بدون CSRF باید رد شوند؛ login صحیح
   cookie واقعی HttpOnly می‌دهد و CSRF واقعی برای POST معتبر استفاده می‌شود.
4. ایجاد دو سفارش ساختگی از **API عادی**، یک/صد ردیف؛ در restart همان IDها و totals
   از همان DB خوانده می‌شوند. route معمولی context را از SQLite و قالب اصلی می‌سازد؛
   context آمادهٔ renderer یا route جعلی جای آن ننشسته است.
5. دریافت PDF کوتاه/بلند از route واقعی، سپس دو درخواست HTTP موازی، و بررسی مستقل
   هر چهار فایلِ دریافت‌شده. Content-Type، disposition، `%PDF-`، هش و تعداد بایت
   باید با فایل بررسی‌شده برابر باشند؛ HTML fallback به هیچ وجه قبولی نیست.

## تزریق خصوصی و مرز هم‌زمانی

adapter قلمِ مرحلهٔ قبل **فقط در process همین QA** به تابع renderer تزریق می‌شود؛
کد app factory، route، قالب، renderer عادی و تنظیمات تولید تغییر نکرده‌اند.
برای هر سند configuration مستقل حافظه‌ای، دو TTF وزیرمتن مطابق SHA asset، صفر
قلم سیستم در configuration فعال و حذف سخت‌گیرانهٔ پوشهٔ موقت کنترل می‌شود. تابع
اصلی renderer در finally برگردانده می‌شود؛ این قابلیت default نصب یا مجوز انتشار نیست.

در طرح اولیهٔ تست، barrier داخل renderer و الزام دو render هم‌زمان گذاشته شد.
آزمون محلی شکست واقعی را نشان داد: transactionهای فعلی SQLite از `BEGIN IMMEDIATE`
استفاده می‌کنند و دو request می‌توانند پشت قفل DB سریالی شوند؛ barrier در این نقطه
فرض نادرستی بود. قفل، busy_timeout، کد DB و محاسبات تغییر نکردند. barrier به سمت
client، **پیش از ارسال دو درخواست** منتقل شد؛ تعداد render هم‌زمان واقعاً مشاهده و
گزارش می‌شود، نه اینکه عدد ۲ به آن تحمیل یا ادعای concurrency native شود. هر چهار
چرخهٔ configuration/TEMP باید کامل و مجزا باشند و هر دو درخواست باید موفق شوند.

## تفاوت آزمون محلی و شاهد native

۱۴ کنترل رفتاری/workflow و دو کنترل دائمی شاهد، شامل guardهای مسیر/state/restart، ورودی stdlib-only، رد فراخوانی
مستقیم، baseline worker، restore محیط در failure، ترتیب GITHUB_ENV و immutable
بودن شاهد تاریخی‌اند. آزمون TCP محلی واقعاً factory/auth/CSRF/order/restart/shutdown
را اجرا می‌کند، اما **PDF جعلیِ صریحاً نامعتبر** و static fixture دارد؛ به‌عنوان
شاهد PDF بومی یا build شدن SPA معرفی نمی‌شود. تست جداگانه HTML fallback را failure
می‌داند. بررسی native فقط در Windows workflow و با inspection خارج از site-packages
تولید انجام می‌شود؛ pypdf و pefile نباید در interpreter برنامه موجود باشند.

محلی: **۶۸۶ تست بک‌اند موفق**؛ Ruff، Mypy برای ۸۵ فایل، gate موجود Bandit و مجوز
MIT همان **۱۴ فایل native-build** موفق‌اند. فایل‌های جدید launcher/worker/QA زیر
این grant قرار نگرفته‌اند.

در سند واقعی route، وزیرمتن Regular باید هر **۳۰ رقم ASCII/فارسی/عربی** را از
دادهٔ ساختگی مشتری/محصول و Bold هر **۱۰ رقم فارسی** را در total واقعی داشته باشد.
هیچ context/قالبی برای تحمیل ارقام به وزن Bold دست‌کاری نشده است؛ این معیار با شاهد
قبلی که هر دو وزن را با ۳۰ رقم مستقیم رندر می‌کرد تفاوت دارد.

## نتیجهٔ واقعی ویندوز و شکست ثبت‌شده

**[39215968473 / 7634e93](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39215968473)**
موفق؛ job **117939764052**. دو process تازه با PIDهای **۴۰۰۸ و ۵۵۴۸**، همان
inventory/baseline، DB و ID سفارش‌ها؛ هر دو migrator واقعی را گذراندند و readiness
با revision **0006_item_catalog** موفق بود. در هر process چهار PDF واقعاً از
HTTP دریافت و مستقل بررسی شد: دو سند **۱صفحه‌ای** و دو سند **۴صفحه‌ای A4**؛ مجموع
**هشت PDF**. وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم Regular و ۱۰ رقم فارسی Bold تأیید شدند.

دو درخواست هم‌زمان client واقعاً موفق شدند، اما **peak render در هر دو process
برابر ۱** بود؛ نه دو renderer موازی و نه throughput جدید ادعا می‌شود. هشت config/
پوشهٔ TTF مجزا، صفر قلم سیستم فعال، SHA دو asset و پاک‌سازی کامل کنترل شدند. هر
۲۷ DLL واقعاً از private/native/pdf/bin بار شدند، Pango **1.58.2** و callbackهای
ctypes سالم بودند. خروج Uvicorn/lifespan graceful و خروج parent موفق بود.

سه حالت منفیِ حذف `-S`، ctypes زودهنگام و digest نادرست نیز در ویندوز واقعاً
رد شدند؛ app/WeasyPrint/uvicorn پیش از ورود bootstrap غایب بودند. credential،
session token، cookie و DB در شاهد ذخیره نشده‌اند.

- [proof احرازشده](../dependencies/pdf-private-http-proof.json) و
  [شاهد کامل](../dependencies/pdf-private-http-evidence.json): **۳۷۶۱۱ بایت** از
  **۲ قطعهٔ annotation**، SHA256:
  `5d083bc6072a8bdd40b67bb5360f3751879cedffda7f385845353d785056518b`.
- artifact **12169508388** با نام
  `private-real-http-pdf-evidence-no-app-db-dlls-not-source-proof`؛ private و ۹۰روزه،
  نه تحویل anonymous پایدار سورس. metadata و annotation احراز شدند؛ دانلود/بازرسی
  ZIP از این sandbox ادعا نمی‌شود.
- حالت قبلیِ launcher هم در **39215518803 / 693386e** مستقلاً موفق شد؛ شاهدهای
  تاریخی **39182480848** و سورس‌ساخته‌شدهٔ **39175100427** تغییر/بازنام‌گذاری نشده‌اند.

اجرای اول **39215518781 / 693386e** به HTML fallback رسید و **شکست خورد**؛ این
شکست به قبولی تبدیل نشده است. backend، migration، auth، CSRF و ایجاد سفارش آن
اجرا شده بودند، اما PDF بومی کامل نشده بود. [رکورد failure](../dependencies/pdf-private-http-render-failure.json)
stderr اصلی renderer را **ثبت‌نشده** می‌داند چون route آن exception را برای fallback
می‌گیرد. بازبینی کد و بازتولید محلی یک نقص قطعی یافت: constructor پوشهٔ cache
موردنیاز adapter را نمی‌ساخت؛ `configuration_xml` وجود آن را الزام می‌کند. ساخت
پوشه، regression مستقیم با همان تابع و traceback بدون locals اضافه شدند. اجرای
بعدی با همان SDK، route و معیار رد HTML موفق شد؛ هیچ assertion بومی/هش یا قفل DB
برای این اصلاح کاهش نیافت. تشخیص اختیاری native روی Linux هم نبود Pango سیستم را
نشان داد و به‌عنوان قبولی یا جایگزین شاهد Windows شمرده نشد.

## CI پایان مرحله

**[39216907772 / 5701143](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39216907772)**:
هر **پنج job موفق** — بک‌اند، frontend، OpenAPI، Playwright و smoke واقعی Windows.
مجموع محلی **۶۸۶ تست بدون failure/skip**؛ subset PDF **۳۲۸ تست موفق** است.
بازاعتبارسنجی مستقل HTTP روی همین snapshot **39216907955** هم موفق شد؛ witness
دائمی همچنان به producer اصلیِ موفق **7634e93** بسته است.

مواد مجوز **39216907977**، مونتاژ/بازبینی source kit **39216907972** و kit کامل
سورس اصلاح‌شده **39216908050** نیز موفق‌اند؛ این‌ها ساخت دوبارهٔ ۲۱ DLL یا حق
انتشار نیستند. [رکورد دائمی CI](../dependencies/pdf-private-http-final-ci.json)
به **5701143** بسته است و فایل‌های runtime/workflow با producer ویندوز مقایسه
شدند و تغییر نکرده‌اند. commit بعدی صرفاً ثبت همین نتیجه و گزارش است.

محافظ‌های CI و digestهای خارجی برای کنترل پیوستگی QA هستند، نه sandbox یا
امضای مستقل در برابر مهاجمی که مالک فایل‌ها/هارنس است. readonly بودن TTF اثبات
ACL نصب نیست؛ ارائهٔ index ساخته‌شده هم پذیرش بصری browser/UI نصب‌شده نیست.
rollbackهای عمومیِ موجود، اثبات native delta/rollback جدید شمرده نشده‌اند.

## گیت‌هایی که بسته نمی‌شوند

این مرحله از SDK پین‌شده استفاده می‌کند، نه ساخت تازه یا مصرف ۲۱ DLL سورس‌ساخته‌شده
با launcher جدید. شاهدهای قبلی بازنویسی نمی‌شوند. startup عادی/تنظیمات production،
پذیرش UI نصب‌شده، minimum OS/امضای interpreter اصلاح‌شده، Inno، native delta و
rollback، تعویض LGPL در نصب، CRT و تحویل anonymous پایدار سورس همچنان موضوع گیت‌های
بازند؛ هر شش گیت باز می‌مانند. راه‌انداز عادی، staging عادی، نسخه، tag/release،
داده و محاسبات کاربر تغییر نکرده‌اند. پایان این مرحله درخواست نصب یا تست دستی کاربر نیست.
