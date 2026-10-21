# فاز ۳ — نصب Inno و delta/rollback بومی

**۲۰۲۶-۱۰-۲۱ — در حال پیاده‌سازی؛ تکمیل نشده است.**

ادامهٔ کار مالک، مجوز همین فاز است، نه انتشار، بستن گیت حقوقی، فعال‌سازی startup
عمومی یا دست‌زدن به نصب `D:\3D PRINT\VIRA-Accounting`.

## تغییرات جاری و فعال‌نشده در مسیر عمومی

- preset صریح `PrivateSourceCI` در **همان** `installer/vira.iss`، با AppId و registry
  مستقل، مسیر انتخابی اجباری، profile موقت محدود به runner و رد نصب مجدد روی anchor
  موجود. context مستقلِ سه digest بیرون payload نصب می‌شود؛ uninstall خصوصی هیچ داده
  یا anchor را حذف نمی‌کند و به backup task عمومی دست نمی‌زند. رفتار پیش‌فرض عمومی
  همچنان CMD قبلی است. preset خصوصی باید روی Windows کامپایل/اجرا و سپس با بستهٔ
  Source21 واقعی اثبات شود؛ صرف وجود فایل ISS اثبات نصب نیست.
- `app/private_installed_source.py` یک bridge متعلق به app و فقط خصوصی CI است؛ anchor
  بیرونی و manifest و bootstrap را کنترل، برای هر اجرا launch/request تازه تولید و
  **همان `start_vira.cmd --private-source-candidate` واقعی** را فراخوانی می‌کند.
  migration/factory/renderer از QA گرفته نمی‌شوند. verifier جداگانه فقط‌خواندنی است.
- branch خصوصی در **همان** `vira_updater.ps1`: فقط با context صریح و GHA، کنترل digest
  بیرونی manifest قدیمی و تمام بایت‌های runtime، قفل updater مشترک و کپی controller
  و Python قدیمی بیرون install root؛ بنابراین Python/DLLهای در حال جایگزینی، میزبان
  transaction نیستند. مسیر عمومی و allowlist عمومی native تغییر نکرده‌اند.
- controller stdlib خصوصی `scripts/private_source_update.py`: کنترل hash خارجی ZIP و
  manifestها، رد traversal/Windows aliases/reparse/duplicate/case collision، سقف بایت،
  تطبیق دقیق عملیات با فایل‌های تغییرکرده، کنترل hash/size و BSDIFF40 محدود؛ فایل
  دست‌نخورده نباید وارد payload delta شود. ابتدا target کامل در TEMP مونتاژ و verifier
  متعلق به app با Python خود target اجرا می‌شود. سپس shutdown cooperative، backup
  فایل/DB، journal، اعمال، anchor جدید، startup و health/build gate؛ شکست باید فایل‌ها،
  DB و anchor قبلی را برگرداند. این توصیف **کد در حال آزمون** است، نه ادعای موفقیت
  transaction واقعی Source21. در حالت rollback تأییدنشده قفل حفظ و startup متوقف می‌شود؛
  recovery پس از قطع برق/kill هنوز اثبات نشده است.

هیچ‌یک از ۱۶ فایل اجرایی freeze‌شدهٔ شاهد فاز ۲ تغییر نکرده است. هیچ renderer،
فرمول مالی، schema، نسخهٔ عمومی یا tag جدیدی انتخاب نشده است. scriptهای جدید داخل
محدودهٔ MIT چهارده‌فایلی قرار داده نشده‌اند؛ شش گیت همچنان بازند.

## آزمون‌های موجود، با محدودهٔ دقیق

- **۵۲ تست جدید مصنوعی** برای byte transport، patch واقعی تولیدشده با bsdiff4 روی
  بایت‌های opaque، anchor/schema/path controls، tampering و عدم تغییر baseline.
  فایل‌های با پسوند DLL/Python در این تست‌ها **native یا interpreter واقعی نیستند**.
- **۹۹۷ تست backend محلی موفق، 81.843 ثانیه، بدون skip/error/failure**؛ شامل تمام
  replayهای قبلی، بدون تغییر هش‌های تاریخی. Ruff، Mypy روی ۸۹ فایل، Bandit در gate
  موجود و MIT محدود ۱۴ فایل موفق‌اند.
- workflow جدید preflight برای Windows: کامپایل دو preset واقعی Inno و نصب/uninstall
  یک fixture صریحاً opaque در مسیر فارسی/فاصله/`! &`؛ اجرای interpreter یا DLL این
  fixture ممنوع است. حتی موفقیت آن، به‌تنهایی پذیرش native delta/rollback یا تکمیل
  فاز ۳ محسوب نمی‌شود. نتیجهٔ واقعی اجرا پس از پایان ثبت خواهد شد.

## کارهای لازم پیش از تحویل فاز ۳

1. رفع هر خطای preflight و تثبیت installer/updater خصوصی با آزمون‌های failure path؛
2. بستهٔ واقعی Source21 با PE/ACP و source audit مستقل، نصب Inno در مسیر انتخابی،
   launch واقعی، DB/رسید/secret/session پایدار و PDF واقعی؛
3. اتصال کامل انتخاب delta و تأیید کاربر در مسیر خصوصی in-app، نه فقط فراخوانی مستقیم
   helper؛ صحت package/anchor و جلوگیری از fallback نصب کامل برای آپدیت عادی؛
4. apply و rollback واقعی با برنامه/Native در حال اجرا، cold DB snapshot، تغییرات
   add/replace/patch/delete، شکست startup و کنترل عدم فقدان داده و صحت PDF پس از restart؛
5. failure/timeout/stale-lock/recovery و آزمون مستقل بستهٔ native، احراز شاهد کامل در
   artifact/jobهای جدا با رعایت سقف ۵۰ annotation/job، سپس CI نهایی و همگام‌سازی دو master.

**فاز ۳ فعال و ناقص است؛ این گزارش تحویل فاز یا درخواست اجازهٔ فاز ۴ نیست.**


Phase3 initial Windows preflight39583808465 and CI39583808447/4e2ecef failed.
Opaque-byte pytest parameter IDs exceeded Windows PYTEST_CURRENT_TEST env32767
limit: exact byte data retained, short explicit IDs added; no skipped controls.
Security gate found9 newly reported vulnerabilities in certifi2026.7.22/Pillow12.3.0;
lock upgraded to2026.10.19/13.0.0, no audit ignore. Local audit now clean (old seeded
setuptools tool upgraded separately, not added as app dependency).
[Preserved failure](../dependencies/phase3-initial-preflight-failure.json).
App bridge uses proven raw CMD quoting/profile-owned CWD; generated Inno uninstaller
is outside fully manifested payload. Added real Windows CMD-only fixture check;
no native-runtime execution claim.53 focused tests PASS locally; next Windows
preflight/CI still required. Phase3 remains ACTIVE/INCOMPLETE.


## اصلاح خطاهای Windows و وضعیت جاری

اجرای دوم `39584663309 / 4516a48` پیش از preflight در بازیابی کمکی log قدیمی متوقف
شد؛ فقط آن بازیابی حذف شد، نه آزمون. CI عادی `39584663404` در چهار job غیر Windows
موفق شد؛ Windows یک خطای جدید replay داشت: خواندن سورس UTF8 با cp1252 پیش‌فرض در
AST test. encoding صریح اصلاح شد؛ hash و دادهٔ آزمون تغییر نکرده‌اند.
[رسید شکست دوم](../dependencies/phase3-second-preflight-failure.json) حفظ شد.

اکنون **۱۰۰۴ تست محلی موفق در 78.304 ثانیه، بدون skip/error/failure**؛ ۵۹ کنترل
متمرکز شامل شش آزمون transaction با filesystem/ZIP/patch و SQLite واقعی، اما
process boundaryهای صریحاً mock‌شده. بازگشت دادهٔ integer/ID، schema و quarantine
پایگاه‌دادهٔ failed-target بررسی شد؛ rollback تأییدنشده قفل را نگه می‌دارد. این‌ها
اجرای برنامهٔ حسابداری/Native نیستند. اصلاح encoding و قفل‌ها هیچ gate را نمی‌بندد.

نصب Source21 واقعی، اتصال خصوصی in-app و اثبات واقعی native apply/rollback هنوز
انجام نشده‌اند؛ workflow ساخت سرد جدید برای فاز ۳ هنوز آغاز نشده است.


اجرای سوم `39585368010 / fffbb1f` به‌درستی در دو آزمون writer مصنوعی SQLite ناموفق
شد: context تراکنش sqlite3 به‌تنهایی connection را نمی‌بندد و Windows جابه‌جایی
DB باز را رد کرد. test writer با `closing` و context تراکنش اصلاح شد؛ ابزار DB
تولیدی از قبل connection را می‌بندد. [شکست سوم](../dependencies/phase3-third-preflight-failure.json)
حفظ شد؛ هیچ موردی skip نشد و هیچ موفقیت native یا Inno از آن نتیجه نمی‌شود.
