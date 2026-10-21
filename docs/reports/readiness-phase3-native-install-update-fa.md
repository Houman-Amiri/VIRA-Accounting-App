# فاز ۳ — نصب Inno و delta/rollback بومی

**۲۰۲۶-۱۰-۲۱ — فعال و ناقص؛ تحویل نهایی فاز انجام نشده است.**

ادامهٔ کار مالک، مجوز همین فاز است، نه انتشار، بستن گیت حقوقی، فعال‌سازی startup
عمومی یا دست‌زدن به نصب `D:\3D PRINT\VIRA-Accounting`. فازهای ۱ و ۲ تحویل شده‌اند؛
کنترل‌های زیر، فازهای مستقل جدید یا مجوز فاز ۴ نیستند.

## تغییرات جاری، بدون فعال‌سازی مسیر عمومی

- preset صریح `PrivateSourceCI` در **همان** `installer/vira.iss`، با AppId/registry
  مستقل، profile موقت محدود به runner، مسیر انتخابی خالی و رد state خصوصی موجود.
  anchor مستقلِ سه digest بیرون payload قرار می‌گیرد. uninstaller تولیدشده نیز بیرون
  payload کاملاً manifest‌شده است؛ uninstall خصوصی داده/anchor را حذف نمی‌کند و
  به backup task عمومی دست نمی‌زند. preset عمومی همچنان CMD قبلی را انتخاب می‌کند.
- bridge متعلق به app، `app/private_installed_source.py`: کنترل anchor بیرونی و
  bootstrap قبل از اجرا، تولید launch/request تازه و فراخوانی **همان CMD واقعی**
  با `--private-source-candidate`. quoting خامِ اثبات‌شده و CWD متعلق به profile
  استفاده می‌شود؛ کنترل Unicode/CWD ضعیف نشده است. verifier جداگانه فقط‌خواندنی است.
- branch خصوصی در **همان** `vira_updater.ps1`: فقط context صریح و GHA، کنترل digest
  بیرونی manifest قدیمی و تمام بایت‌های runtime، قفل updater مشترک و کپی controller
  و Python قدیمی بیرون install root؛ میزبان transaction در میان فایل‌های جایگزین‌شونده
  قرار نمی‌گیرد. مسیر عمومی و allowlist عمومی native تغییر نکرده‌اند.
- controller stdlib خصوصی `scripts/private_source_update.py`: hash خارجی ZIP و
  manifestها، رد traversal/Windows aliases/reparse/duplicate/case collision، سقف بایت،
  تطبیق دقیق عملیات با فایل‌های تغییرکرده، hash/size و BSDIFF40 محدود. فایل دست‌نخورده
  نباید وارد delta شود. ابتدا target کامل در TEMP مونتاژ و verifier خود app با Python
  همان target اجرا می‌شود؛ سپس shutdown، backup فایل/DB و journal، اعمال و anchor جدید،
  startup و health/build gate. شکست باید فایل‌ها، DB و anchor قبلی را برگرداند.
  rollback تأییدنشده قفل را نگه می‌دارد؛ recovery پس از قطع برق/kill هنوز اثبات نشده است.

این توصیف **کد در حال آزمون** است، نه اثبات transaction واقعی Source21. factory،
renderer و migration از QA گرفته نمی‌شوند. ۱۶ فایل freeze‌شدهٔ فاز ۲ تغییر نکرده‌اند.
schema، محاسبات، UI و نسخهٔ عمومی تغییر نکرده‌اند؛ فایل‌های جدید وارد MIT چهارده‌فایلی نشده‌اند.

## شواهد موفق با محدودهٔ دقیق

[اجرای محدود 39585771427](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39585771427)
در `e5103ad` موفق شد؛ [رسید احرازشده](../dependencies/phase3-inno-limited-preflight-proof.json):

- **۵۹ تست متمرکز در Windows موفق**؛ دو preset واقعی Inno کامپایل شدند.
- نصب و uninstall واقعی Inno در مسیر فارسی/فاصله/`! &` با fixture **opaque** انجام شد؛
  anchor خارج payload کپی شد، نصب مجدد روی anchor موجود رد شد و دادهٔ مصنوعی عمومی و
  خصوصی پس از uninstall حفظ شد. این فقط مکانیک Inno است؛ نه پذیرش بصری wizard.
- fixture حاوی فایل‌هایی با نام `python.exe` و `synthetic.dll` بود که **interpreter/DLL
  واقعی نیستند و اجرا نشدند**. این اجرا، نصب یا PDF یا delta بومی Source21 را اثبات نمی‌کند.
- کنترل‌های orphan state و مجموعهٔ دقیق فایل‌های payload نیز در اجرای جداگانهٔ
  [39586235223](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39586235223)
  روی `9c7b764` موفق شدند؛ [رسید مستقل](../dependencies/phase3-inno-orphan-preflight-proof.json).
  این نتیجه به اجرای قدیمی e5103ad نسبت داده نشده است.

**۱۰۰۴ تست backend محلی موفق در 77.446 ثانیه، بدون skip/error/failure**؛ Ruff، Mypy
روی ۸۹ فایل و Bandit در gate موجود موفق‌اند. ۵۹ کنترل متمرکز شامل شش آزمون transaction
با filesystem/ZIP/BSDIFF و SQLite واقعی، اما process boundaryهای صریحاً mock‌شده است.
integer/ID، schema، receipt/secret و quarantine پایگاه‌دادهٔ failed-target بررسی شدند؛
این schema مصنوعی است، نه اجرای نصب‌شدهٔ حسابداری. CMD quoting نیز با batch واقعی
Windows بررسی شد؛ اجرای interpreter یا native PDF از آن نتیجه نمی‌شود.

گیت pip-audit ابتدا ۹ آسیب‌پذیری تازه در certifi/Pillow گزارش کرد. فقط lock به
certifi `2026.10.19` و Pillow `13.0.0` ارتقا یافت؛ هیچ ignore اضافه نشد. audit محلی
اکنون پاک است. setuptools قدیمیِ seed محیط ابزار محلی جداگانه ارتقا یافت و به
وابستگی‌های برنامه اضافه نشد. کنترل مجوز MIT همچنان فقط همان ۱۴ فایل است.

در checkpoint `9c7b764`، CI `39586234984` با هر پنج job، license `39586235299`،
source kit `39586235160` و modified kit/Windows recipient `39586235248` همگی موفق‌اند.
[رسید checkpoint ناقص](../dependencies/phase3-incomplete-checkpoint-ci.json) صریحاً
`phase3_complete=false` دارد. سخت‌سازی بعدی، install root خصوصی را به runner TEMP
محدود و anchor/manifest قدیمی را پیش از clone از نظر reparse کنترل می‌کند؛ نتیجهٔ
این تغییرات باید برای commit بعدی جداگانه بررسی شود.

## شکست‌های حفظ‌شده، بدون حذف آزمون

| اجرا / کد | علت و اصلاح | محدودهٔ اثبات‌نشده |
|---|---|---|
| `39583808465 / 4e2ecef` و CI `39583808447` | ID پیش‌فرض byte parameter در pytest از سقف 32767 متغیر محیطی Windows گذشت؛ ID کوتاه صریح، با همان بایت‌ها. audit نیز دو dependency آسیب‌پذیر یافت و lock اصلاح شد. | Inno/native اجرا نشد. |
| `39584663309 / 4516a48` و CI `39584663404` | بازیابی کمکی log قبل از preflight شکست خورد؛ فقط بازیابی حذف شد. Windows CI در AST test جدید، UTF-8 را با cp1252 خواند؛ encoding صریح شد. | آزمون/expected hash حذف یا ضعیف نشد. |
| `39585368010 / fffbb1f` | test writer مصنوعی، sqlite3 connection را با context تراکنش می‌بست اما connection بسته نمی‌شد؛ Windows quarantine را رد کرد. `closing` همراه context تراکنش اضافه شد؛ ابزار DB تولیدی از قبل درست می‌بست. | دو failure جدید رفع شدند، نه skip. |
| `39585596841 / 9d8d778` | ۵۹ تست Windows و compile عمومی موفق؛ ISPP تابع Pascal `Chr` ندارد. quoting literal در entryهای conditional جایگزین شد. | private compile ناموفق؛ نصب هنوز اجرا نشده بود. |

رسیدها: [اول](../dependencies/phase3-initial-preflight-failure.json)،
[دوم](../dependencies/phase3-second-preflight-failure.json)،
[سوم](../dependencies/phase3-third-preflight-failure.json)،
[چهارم](../dependencies/phase3-fourth-preflight-failure.json).

Inno 6.7.1 عبارت **Non-commercial use only** در banner دارد؛ تست CI، حق انتشار
تجاری ایجاد نمی‌کند. بررسی entitlement و سایر شرایط توزیع در فاز ۴ باز می‌ماند.
هر شش گیت حقوقی/توزیع بازند؛ هیچ tag یا release جدید ساخته نشده است.

## باقی‌ماندهٔ همین فاز، پیش از اعلام تکمیل

1. بستهٔ واقعی Source21 با PE/ACP و source audit مستقل، نصب Inno در مسیر انتخابی،
   launch واقعی و DB/رسید/secret/session پایدار، همراه PDF واقعی؛
2. اتصال کامل انتخاب delta و تأیید کاربر در مسیر خصوصی **in-app**، نه فقط فراخوانی
   مستقیم helper؛ صحت package/anchor و جلوگیری از fallback نصب کامل در آپدیت عادی؛
3. apply/rollback واقعی با برنامه و native در حال اجرا، cold DB snapshot، عملیات
   add/replace/patch/delete و شکست startup؛ صحت داده و PDF پس از restart؛
4. failure/timeout/stale-lock/recovery، احراز کامل شاهد با رعایت سقف annotation/job
   و CI نهاییِ همان نسخه، سپس همگام‌سازی نهایی هر دو master.

**ساخت سرد Source21 مخصوص فاز ۳ هنوز آغاز نشده است. فاز ۳ فعال و ناقص است؛ نصب و
دادهٔ واقعی کاربر دست‌نخورده‌اند و فاز ۴ یا انتشار آغاز/تأیید نشده است.**
