# جفت‌کردن ساخت سورسِ دارای اعلان تغییر با راه‌انداز بدون site و HTTP — ۲۰۲۶-۱۰-۱۹

> نتیجهٔ اجرای اصلاح‌شده: **موفق، فقط اثبات خصوصی CI؛ نه مجوز انتشار یا پذیرش نصب.**

## مرز مرحله

هدف، اتصال همان factory/route واقعی HTTP به **۲۱ DLL تازه‌ساخته‌شده از ۲۰ درخت
سورسِ ثبت‌شده** است؛ نه بازنام‌گذاری شاهد قبلی SDK/۲۷ DLL یا شاهد قدیمی Unicode.
فقط `--http-proof` همراه digest مستقل `--source-audit-sha256` حالت سورس را انتخاب
می‌کند. بدون انتخاب صریح، حالت SDK و رد سورس به همان صورت باقی می‌ماند؛ target
دلخواه، fallback به SDK، تغییر app factory/route/قالب یا startup عادی نداریم.

## اتصال archive → compile → candidate → bootstrap → HTTP

- ابتدا preflight جداگانهٔ SDK/HTTP اجرا می‌شود؛ این job **هیچ منشأ سورسی را ثابت
  نمی‌کند**. consumer سورس در VM جداگانه، SDK fixture را دریافت/اجرا نمی‌کند.
- producer و artifact دقیقِ آرشیو دارای اعلان تغییر از GitHub API احراز می‌شوند؛
  manifest خارجی، تمام envelope و extraction دوباره بررسی می‌شوند. آرشیو ثابت
  SHA256 برابر `b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2`،
  manifest برابر `784c8d196ad0da899e7d6b65d26aff4d4bf9bb00551526692cda9b47c43c2023`
  و فایل Pangoِ اعلان‌دار برابر
  `a530b81e21d8799996032c68398651ec802d62017bac88c6c9d3b7cebd89719a` است.
- هر ۲۰ target از درخت‌های local مطلوب با binary cache خاموش ساخته می‌شوند؛
  host tool/source downloads هنوز مجازند، پس offline یا bitwise rebuild ادعا نمی‌شود.
  audit مستقل، درخت‌های واقعی build، مالک/هش/مبدأ ۲۱ DLL، عدم تغییر ورودی، متن
  اعلان تغییر و اجرای واقعی `pango_version_string` را بررسی می‌کند.
- candidate از همان audit ساخته می‌شود. یک نسخهٔ دقیق `source-audit.json` در
  baseline خصوصی قرار می‌گیرد؛ digest بیرونی آن هم باید با inventory برابر باشد.
  guardها archive/manifest/file pins، ۱۹ درخت اصلی و یک درخت تغییرکرده، مجموعهٔ
  packageها، hash/count هر درخت و hash/owner هر DLL را متصل می‌کنند. صرف origin
  یا version resource و صرف وجود ۲۱ فایل به معنی اثبات ساخت نیست.
- پس از کنترل کامل baseline، `-I -S -B -X utf8`، CPython خصوصی، پروفایل/TEMP فارسی
  و ACP 65001، libffi مخصوص همین closure با مسیر کامل پیش از app/WeasyPrint pin
  می‌شود. worker ثابت بعد از bootstrap وارد migrator، create_app و Uvicorn واقعی
  روی TCP loopback می‌شود. adapter قلم فقط در process QA تزریق می‌شود، نه default
  تولید. سازوکار تزریق/guardهای CI ضد‌دست‌کاری مستقل در برابر مالک فایل‌ها نیست.

## تفاوت مهم نام DLLهای FFI

closure سورس **`ffi-8.dll`** و Pango بدون prefix یعنی `pango-1.0-0.dll` دارد؛ SDK
نام‌های متفاوتی دارد. فایل‌ها rename/alias نمی‌شوند و DLL از SDK برای پُرکردن
closure سورس قرض گرفته نمی‌شود. CPython ممکن است برای `_ctypes` از **`libffi-8.dll`
مجزای bundle خودش** استفاده کند. قبولی callbackهای ctypes به معنی استفادهٔ آن از
FFI سورس‌ساخته‌شده نیست؛ مبدأ بارگذاری هر ۲۱ DLL closure و نسخهٔ function واقعی
Pango جداگانه باید بررسی شوند. مجوز/منشأ CPython و CRT همچنان گیت‌های بازند.

## کنترل HTTP و آزمون‌ها

دو process تازه باید همان DB/ID سفارش‌ها را حفظ کنند؛ migrator واقعی، سلامت/
readiness، SPA ساخته‌شده، OpenAPI، رد بدون login/login غلط/CSRF غایب، cookie واقعی
و سفارش‌های یک/صدردیفی از API عادی کنترل می‌شوند. چهار PDF در هر process از route
واقعی دریافت و با inspector بیرونی بررسی می‌شوند؛ HTML fallback شکست است.

معیار قلم/سند همان مسیر HTTP قبلی است: A4 یک/چهارصفحه‌ای، وزیرمتن ۴۰۰/۷۰۰،
۳۰ رقم ASCII/فارسی/عربی Regular و ۱۰ رقم فارسی Bold در total واقعی؛ TTFهای TEMP
مطابق SHA asset، صفر قلم سیستم فعال و پاک‌سازی هر سند. دو درخواست client موازی‌اند؛
قفل فعلی DB تغییر نمی‌کند و تعداد واقعی render هم‌زمان گزارش می‌شود، نه عدد تحمیلی.

۲۶ کنترل جدید، جداسازی role SDK/source، digest/receipt/notice، فساد DLL/مالک/درخت،
رد حالت سورس بدون HTTP و ترتیب archive→compile→audit→HTTP را پوشش می‌دهند. آزمون‌های
schema/binder که داده‌های تاریخی را ترکیب می‌کنند **صریحاً synthetic** هستند؛ هیچ
فایل شاهد تاریخی را تغییر نمی‌دهند و از آن‌ها شاهد تازهٔ ساخت نمی‌سازند.

اجرای اولیهٔ محلی **۷۱۲ تست** و سپس با ۹ کنترل binder/حجم **۷۲۱ تست موفق**،
Ruff، Mypy برای ۸۵ فایل، gate
موجود Bandit و grant محدود MIT۱۴ موفق‌اند. فایل‌های launcher/HTTP/QA جدید زیر grant
native-build نیستند. تغییر banner QA فقط برای بیان درست scope و dependencyهای
workflow ثبت شد؛ اجرای superseded به معنی قبولیِ ساخت/HTTP سورس نیست.

## شکست واقعی انتقال شاهد و اصلاح بدون عبور از آن

اجرای `39220310210 / f479f70` شکست‌خورده باقی می‌ماند: کامپایل، audit، HTTP،
restart، binder و احراز مجدد envelope همگی در API دارای conclusion موفق‌اند؛
اما `Source HTTP evidence group 0` شکست خورد و workflow کلی **موفق نیست**.
[رسید کامل وضعیت job و annotationها](../dependencies/pdf-source-http-evidence-transport-failure.json)
حفظ شده است. دریافت log اصلی از host بیرون از دسترس sandbox با EOF روبه‌رو شد؛
متن traceback اصلی مشاهده نشده و بازسازی نمی‌شود.

آزمون با حجم واقعی inventory upstream نشان داد تکرار metadata/متن‌های copyright
دو inventory در شاهد inline از سقف ۳۲ بخش فراتر می‌رود. اصلاح، projection صریحِ
فیلدهای **قبلاً اعتبارسنجی‌شده** است: hash/owner هر DLL، hash/count هر درخت،
منشأ، گیت توزیع، digest audit و Pango/FFI pins همگی باقی‌اند؛ inventory کامل با
متن notices همچنان در artifact و digest آن در baseline/launcher حفظ می‌شود.
projection خودش همان فایل byte-hashed اصلی نامیده نمی‌شود. audit کامل، شواهد
HTTP، سقف ۳۲×۳۰۰۰، guardها و هیچ کنترل PDF تغییر نکردند. یک regression با حجم
واقعی مجوزها اضافه شد؛ به جای تغییر نام failure یا قبول اجرای ناقص، workflow
کاملِ تازه با کامپایل دوباره از همان سورس آغاز شد.

## نتیجهٔ واقعی اجرای اصلاح‌شده

- [اجرای 39226693623](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39226693623)،
  commit `b04440eaef218a3f7a2a7942231b21e7443babcb`، هر دو job **success**؛ job سورس `117975682474`.
- witness جدید [pdf-source-http-evidence.json](../dependencies/pdf-source-http-evidence.json)،
  **112123 بایت**؛ SHA256 `5bdaf15379c3e22516b8c26a85cf047f54e803fb4a39e66de060458dbe237a94`.
  10 بخش authenticated، شمارش کامل و digest مستقل
  از annotationهای همان check/job بازیابی شد. API artifact `12178137356` هم
  به همان head متصل است؛ ZIP در sandbox دانلود نشده و محتوای ZIP independently
  با hash تأییدشده معرفی نمی‌شود. [سند provenance](../dependencies/pdf-source-http-proof.json).
- digest مستقل audit native: `9cdb03d862df1ead6f19c30f77f469abc98173cd6b4d1580113700523087e568`؛۲۰ درخت،۲۱ DLL،
  function Pango تغییرکرده `1.58.0-vira-local-source` اجرا شد و envelope بعد از PDF
  دوباره احراز شد. هیچ نسخهٔ SDK یا صرف Boolean worker جای compilation ثبت نشده است.
- دو PID واقعی `6624` و
  `5184`، DB/fixture IDs
  یکسان؛ چهار PDF در هر process، یک/چهارصفحه‌ای A4. preflight SDK جداگانه موفق است.
- هر۲۱ DLL از native خصوصی، no-site/isolated/UTF-8/ACP65001 و سه negative واقعی
  (بدون no-site، import زودهنگام ctypes، digest غلط) احراز شدند. font400/700 و
  معیار دقیق۳۰/۱۰رقم، hash asset و cleanup هر۸ سند موفق‌اند. دو client موازی،
  native peak واقعی۱ در هر دو process؛ ادعای دو native render هم‌زمان نداریم.
- ۲۶ guard،۹ binder/volume synthetic و۲ آزمون immutable witness؛ **۷۲۳ تست بک‌اند**
  محلی موفق، Ruff/Mypy۸۵/Bandit و MIT۱۴ موفق. شاهد SDK و source قدیمی بدون تغییرند.

این دو process QA با adapter تزریقی به factory واقعی وصل شده‌اند؛ این نتیجه
**ordinary production HTTP startup، staging/launcher نصب‌شده یا پذیرش کاربر نیست**.


## آزمون محلی و CI کد اجرایی

اجرای کاملِ پس از افزودن شاهد واقعی: **۷۲۳ تست در 85.32 ثانیه موفق**؛ Ruff،
Mypy/۸۵ فایل، Bandit با گیت موجود و grant MIT/۱۴ فایل موفق‌اند. CI عادیِ همان
implementation `b04440e` در [39226693656](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39226693656)
هر پنج job موفق است: backend، frontend، Playwright، OpenAPI و Windows-native
smoke. CI عادی و هر دو regression خصوصی SDK در f479 نیز موفق‌اند.
[رسید checkpoint](../dependencies/pdf-source-http-checkpoint-ci.json) صریحاً متعلق
به implementation است، نه ادعای پیشاپیش دربارهٔ commit بعدیِ docs/witness؛ پس از
ثبت نهایی، CI همان head هم جدا بررسی می‌شود. Source/runtime frozen در b044 است؛
commit نهایی فقط شاهد، آزمون شاهد، گزارش/plan و progress خصوصی policy را می‌افزاید.

## مواردی که با این مرحله بسته نمی‌شوند

هر شش گیت حقوقی/CRT/recipient toolchain/source delivery/نصب و پذیرش باز می‌مانند؛
ساخت تازه و PDF واقعی، حق انتشار اجزا یا توزیع interpreter اصلاح‌شده را صادر نمی‌کند.
artifact خصوصی ۹۰روزه، منبع anonymous پایدار نیست. startup production عادی، امضا/
minimum OS matrix، Inno، native delta/rollback، تعویض LGPL در نصب/EULA و پذیرش
کاربر نصب‌شده اثبات نمی‌شوند. staging عادی، راه‌انداز نصب‌شده، داده، محاسبات، نسخه،
tag و release تغییر نمی‌کنند؛ نصب/تست دستی از کاربر درخواست نمی‌شود.
