# فاز ۳ — نصب Inno و delta/rollback بومی

**۲۰۲۶-۱۰-۲۵ — فعال و ناقص؛ تحویل نهایی فاز انجام نشده است.**

**آخرین وضعیت:** CI کد7bb72e0 با40189290259 هر۵job موفق و preflight ویندوز
40189290266 با۱۴کنترل terminal و۱۲کنترل clone موفق است. اما مرحلهٔ NativeB در
40183092030/55e65f5 شکست خورده است؛ ساخت و نصب/HTTP پایه موفق بوده، نه NativeB
و نه دلتا/rollback. artifact شکست موجود است ولی دانلود مستقیم لاگ و artifact
از sandbox خطای EOF دارد؛ job تشخیصی فقط‌خواندنی برای بازیابی علت اضافه شد.
فاز۳ ناقص است؛ همهٔ۶گیت باز و نصب/دادهٔ کاربر و انتشار بدون تغییر هستند.




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
renderer و migration از QA گرفته نمی‌شوند. ادعای بدون‌تغییر بودن ۱۶ فایل مربوط
به checkpoint قبلی بود؛ در اصلاح قرارداد نسخه، دو ماژول و workflow گسترش یافتند
و بایت‌های اصلی آن سه برای صحت شواهد تاریخی جدا نگه داشته شدند (شرح در ادامه).
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


## ادامهٔ اتصال update خصوصی — ۲۰۲۶-۱۰-۲۱

- مسیر خصوصی اکنون به download/staging/dispatch/status همان سرویس update وصل است؛
  marker محیطی به‌تنهایی کافی نیست. CI/profile/state/Settings و anchor نصب قبلی
  باید تطبیق کنند. بسته و metadata پیش از اجرا دوباره کنترل می‌شوند و فقط helper
  نصب‌شدهٔ قدیمی انتخاب می‌شود، نه helper دانلودشده. مسیر عمومی native را نمی‌پذیرد.
- digest هدف در ZIP به manifest متصل است؛ port و سیاست browser قابل تغییر نیستند.
  clone controller بیرون profile داده قرار می‌گیرد. قفل channel و شناسهٔ attempt،
  نتیجهٔ اجرای قبلی را از polling جدید جدا می‌کنند. finally تو در تو مانع از جا ماندن
  mutex هنگام خطای انتشار نتیجه می‌شود؛ recovery قفل stale هنوز اثبات نشده است.
- manifest با بایت UTF8 نوشته می‌شود؛ آزمون CLI برابر بودن بایت manifest بسته و
  delta را حتی با نام فارسی بررسی می‌کند. ۲۳ تست جدید **مصنوعی** هستند؛ هیچ DLL،
  interpreter یا helper مصنوعی اجرا نشده است.
- کل تست محلی: **۱۰۲۷ موفق در ۷۷٫۲۹ ثانیه، بدون شکست/خطا/skip**؛ Ruff و Mypy
  (۹۰ فایل) موفق. Bandit با سطح CI (`-ll`) موفق؛ اجرای بدون فیلتر ۲۷ مورد low
  گزارش می‌دهد و ادعای صفر finding نداریم. audit اولیهٔ venv تازه روی setuptools
  قدیمی شکست خورد؛ seed ابزار محلی به 84.2.1 ارتقا یافت و audit دوباره موفق شد.
  lockfile، dependency تحویلی و نسخهٔ برنامه تغییر نکرده‌اند.
- workflow ویندوز برای parse کامل PowerShell و تست‌های جدید گسترش یافته است؛
  نتیجهٔ commit تازه باید جدا ثبت شود و CI قبلی تأیید این تغییرات نیست.

**وضعیت همچنان ناقص است:** cold build جدید Source21، نصب runtime واقعی، apply
واقعی از API با رضایت، rollback تأییدشده با حفظ همهٔ داده‌ها و crash/stale recovery
هنوز انجام نشده‌اند. این checkpoint تحویل فاز، مجوز فاز ۴ یا انتشار نیست.


### نتیجهٔ ویندوز و کنترل تکمیلی مسیرها

- commit `263fe1f`: CI کامل `39596502047` در هر پنج job موفق شد؛ بررسی محدود ویندوز
  `39596501961` نیز موفق است: parse واقعی PowerShell، تست‌های مصنوعی channel و
  compile/install/uninstall واقعی Inno روی payload غیرقابل‌اجرای مصنوعی. این‌ها
  پذیرش نصب یا update بومی Source21 نیستند.
- چهار تست تکمیلی، symlink/junction در data، مسیر DB، updates و نسخهٔ staging را
  قبل از نوشتن رد می‌کنند. جمع جدید: **۲۷ تست متمرکز؛ کل suite برابر ۱۰۳۱ تست
  موفق در ۶۸٫۳۲ ثانیه، بدون شکست/خطا/skip**. این follow-up به CI جدا نیاز دارد.
  Ruff، Mypy، Bandit سطح CI و audit دوباره موفق‌اند. ۱۶ Git blob ثابت فاز ۲
  دوباره تطبیق داده شدند؛ هیچ تفاوتی ندارند.
- **مانع integration مشخص شد و دور زده نشد:** guard فعلی bootstrap خصوصی فازهای
  ۱/۲ فقط نسخهٔ `0.0.0-private-unicode-proof` را قبول می‌کند. fixture نسخهٔ 99.30.x
  صرفاً تست channel است و نمی‌تواند عبور native bootstrap واقعی را ثابت کند.
  پیش از build و transaction واقعی، قرارداد صریح نسخهٔ نصب‌شده با anchor مستقل
  و تست‌های مثبت/منفی لازم است؛ نباید guard عمومی یا کنترل‌های قبلی ضعیف شوند.

جزئیات قابل‌ماشین‌خواندن در
`docs/dependencies/phase3-private-channel-checkpoint-ci.json` ثبت است.
فاز ۳ همچنان فعال/ناقص است؛ هیچ cold build جدید، tag، release یا تغییری در نصب و
دادهٔ واقعی کاربر انجام نشده است.


## اصلاح قرارداد نسخهٔ نصب‌شده — ۲۰۲۶-۱۰-۲۱

قرارداد schema2 به anchor مستقل، نسخهٔ صریح اضافه می‌کند. manifest کامل ابتدا
تأیید می‌شود و فایل version.json پوشش‌داده‌شده با همان نسخه تطبیق می‌کند. درخواست
نصب خصوصی از همان CMD واقعی می‌گذرد و anchor، state، port و سیاست browser باید
هم‌خوان باشند. مسیر قبلی هنوز نسخهٔ آزمایشی ثابت را می‌خواهد؛ مسیر عمومی و
SDK با marker محیطی وارد حالت جدید نمی‌شوند. generator/stager/controller نیز
نسخهٔ هدف و ممنوعیت downgrade قرارداد را کنترل می‌کنند.

**تغییر شفاف شواهد:** این اصلاح دو ماژول اجرایی و workflow فاز ۲ را گسترش می‌دهد؛
دیگر ادعای «هر ۱۶ فایل جاری بدون تغییر» درست نیست. بایت دقیق قدیمی این سه فایل
جدا نگه داشته شده و با hash اصلی تطبیق دارد؛ ۱۳ فایل دیگر تغییری ندارند. hash
یا witness تاریخی بازنویسی نشده و موفقیت قبلی ویندوز، اثبات کد جدید نیست.

۲۸ تست جدید مصنوعی، از جمله ساخت ZIP/BSDIFF و مونتاژ و بررسی دوبارهٔ payload
کامل مصنوعی Source21، موفق‌اند. اجرای کامل اول روی snapshot workflow خطا داد؛
با نگهداری بایت‌های اصلی آن اصلاح شد، نه با skip یا تغییر hash شاهد. نتیجهٔ نهایی
محلی: **۱۰۵۹ تست موفق در ۸۷٫۵۹ ثانیه، بدون شکست/خطا/skip**. Ruff، Mypy (۹۰ فایل)،
Bandit سطح CI و audit وابستگی‌ها موفق‌اند.

درایور اجرای واقعی نصب نسخه‌دار در مسیر انتخابی، HTTP/PDF، restart و حفظ نشست و
دادهٔ ساختگی به همان workflow cold source وصل شده است. تا نتیجهٔ تازه جمع‌آوری
نشود، ادعای موفقیت واقعی نداریم. حتی موفقیت این نصب، اثبات delta/rollback بومی و
crash recovery نیست؛ این موارد همچنان در همین فاز ۳ باقی‌اند. نسخهٔ 99.30.0 فقط
QA خصوصی و موقت است؛ نسخهٔ عمومی، نصب و دادهٔ واقعی کاربر دست‌نخورده‌اند.


### مانع اجرای ویندوز در اتصال فعلی

کد `17989b3` با موفقیت push و ref راه دور تأیید شد، اما برای همین SHA هیچ run،
check suite یا check run تازه‌ای در Actions پیدا نشد. علت اجرا نشدن خودکار هنوز
مشخص نیست. تلاش اجرای صریح workflow و خواندن تنظیمات مجوز Actions هر دو با
**HTTP 403 — Resource not accessible by integration** رد شدند. بنابراین **cold
build جدید شروع نشده و اجرای واقعی قرارداد جدید روی ویندوز تأیید نشده است**.

trigger صریح `workflow_dispatch` برای CI، preflight و source workflow اضافه شد
تا پس از اصلاح مجوز Actions اتصال GitHub، همین شاخه اجرا شود. این تنظیم به‌تنهایی
مجوز API اتصال را تغییر نمی‌دهد. هیچ رمز، token یا کد ورود نباید در گفتگو ارسال شود.
نتیجهٔ محلی ۱۰۵۹ تست همچنان معتبر است، ولی جای آزمون ویندوز را نمی‌گیرد؛ فاز ۳
فعال و ناقص باقی می‌ماند. جزئیات در `phase3-version-contract-blocked-checkpoint.json` است.


### ادامهٔ خودکار و شکست واقعی ویندوز

workflowهای push با تأخیر ظاهر شدند؛ checkpoint قبلی نبود run، وضعیت تاریخی است،
نه مانع کامل فعلی. source workflow برابر 39608813235 و CI جدید برابر 39609353418
فعال‌اند. dispatch دستی همچنان 403 است، ولی فعلاً نیازی به reconnect از طرف کاربر
نیست. شکست preflight ویندوز 39608813001 در job119251942209 حفظ شده است: چاپ مسیر
فارسی روی stdout با cp1252 باعث UnicodeEncodeError شد. CLI اصلی به UTF8 اصلاح شد؛
مسیر فارسی و guard بومی ACP حفظ شدند. ۸۱ کنترل متمرکز محلی، Ruff و Mypy موفق‌اند.
شکست یا تستی skip نشده و برای نسخهٔ اصلاحی باید ویندوز دوباره اجرا شود. حتی موفقیت
نصب Source21، به‌تنهایی اثبات delta/rollback واقعی و تکمیل فاز ۳ نیست.


### checkpoint قطع احراز هویت پس از push اصلاح

اصلاح `4669c5e` به راه دور رسید؛ کل suite محلی ۱۰۵۹ تست در ۸۷٫۷۲ ثانیه بدون
شکست/خطا/skip موفق شد. Ruff، Mypy۹۰، Bandit سطح CI و audit موفق‌اند. پس از آن،
خواندن وضعیت run نسخهٔ اصلاحی، source jobs و CI jobs هر سه HTTP401 دادند. وضعیت
اجرای دوردست در این نقطه نامعلوم است؛ workflowهای خودکار ممکن است ادامه داشته
باشند اما نتیجه قابل خواندن نیست. برای ادامه، اتصال GitHub در Arena دوباره برقرار
شود؛ هیچ رمز یا token در گفتگو ارسال نشود. این گزارش و رسید قطع دسترسی محلی
ذخیره شدند و با اتصالِ معلوم‌خراب، push دیگری امتحان نشد.


### ادامه پس از برقراری اتصال — قفل نوشتن تا نتیجهٔ قطعی

- CI کامل 39610014300 هر پنج job موفق؛ preflight ویندوز 39610014273 نیز موفق.
  خطای چاپ مسیر فارسی واقعاً روی ویندوز رفع شده است، نه صرفاً در تست محلی.
- source workflow شمارهٔ 39610014494، job119259657791، در مرحلهٔ compile واقعی
  کتابخانه‌ها از preferred source و بدون binary cache دیده شد. این پیشرفت build
  است؛ نصب یا delta بومی موفق هنوز ادعا نمی‌شود.
- پنجرهٔ نوشتن پیش از commit بسته شد: قفل مشترک API/scheduler هنگام startup
  مقصد و rollback باقی می‌ماند. فقط child کنترلر با درخواست installed صریح و
  nonce مطابق قفل خصوصی می‌تواند برای health بالا بیاید. درخواست legacy یا
  marker محیطی به‌تنهایی قفل را دور نمی‌زند. API نوشتنی تا journal قطعی 503 می‌دهد.
- شکست ثبت نتیجهٔ commit، بازگردانی نسخه/DB قبلی را با قفل بسته انجام می‌دهد؛
  شکست سلامت یا journal بازگردانی، quarantine را حفظ می‌کند و موفقیت کاذب نمی‌دهد.
- ۱۲ کنترل جدید؛ suite کامل **۱۰۷۱ موفق در ۸۶٫۷۱ ثانیه، بدون شکست/خطا/skip**.
  Ruff، Mypy۹۰، Bandit سطح CI و audit موفق‌اند. تست ترتیب guard برای امضای
  توسعه‌یافته به‌روز شد؛ تست بازشدن قفل نیز 403 موجودِ CSRF را انتظار دارد، نه
  401 اشتباه. هیچ تستی کنار گذاشته نشد. بررسی ویندوز برای این follow-up باقی است.
- workflow جدید پشت cold build فعال صف می‌گیرد؛ build در حال انجام بابت push
  تکمیلی لغو نمی‌شود. معیارهای delta/rollback واقعی، حفظ همهٔ داده‌ها و recovery
  پس از crash/stale هنوز تکمیل نشده‌اند؛ انتشار یا فاز ۴ مجاز نشده است.


### تأیید Windows قفل نوشتن و رفع قفل خودِ EXE

commit a7c6fc8: preflight ویندوز 39612185288 و CI 39612185530 در هر پنج job
موفق‌اند. این نتیجه، transaction واقعی Source21 نیست؛ cold source 39610014494
هنوز compile می‌کند و اجرای جدید 39612186978 پشت آن صف گرفته است.

مانع دیگری برای update EXE رفع شد: اجرای helper نصب‌شده از داخل {app} فایل
خودش را روی ویندوز قفل می‌کند. اکنون helper **قدیمی** با hash/size مستقل تأیید،
در TEMP تازه و جدا از نصب/profile کپی و fsync، سپس دوباره تطبیق داده می‌شود.
فقط همین کپی همسان اجرا می‌شود و InstallDir صریح، نصب اصلیِ anchored است؛ helper
دانلودشده هرگز برای همان transaction اجرا نمی‌شود. فایل EXE نصب‌شده برای تعویض
آزاد می‌ماند. این تغییر نصب کامل یا دانلود setup را وارد مسیر عادی نمی‌کند.

سه تست منفی جدید؛ suite محلی **۱۰۷۴ موفق در ۸۸٫۹۶ ثانیه، بدون شکست/خطا/skip**؛
Ruff، Mypy۹۰، Bandit سطح CI و audit موفق‌اند. نتیجهٔ ویندوزِ این follow-up باید
جدا جمع‌آوری شود. delta/rollback بومی واقعی، خطاهای terminal helper و recovery
پس از crash/stale هنوز معیارهای باز همین فاز هستند. نصب و دادهٔ واقعی دست‌نخورده‌اند.


### تأیید نهایی CI همین checkpoint (نه تحویل فاز ۳)

کد `0f55e9c`: CI شمارهٔ 39614143087 هر پنج job موفق؛ preflight ویندوز شمارهٔ
39614143678/job119270527662 نیز موفق است. تست helper-copy و قفل نوشتن دیگر صرفاً
نتیجهٔ محلی نیستند، ولی همچنان تست مصنوعی/محدودند و جای Native Source21 را نمی‌گیرند.
رسید metadata در `docs/dependencies/phase3-helper-clone-windows-ci-proof.json` ثبت شد.

Source39610014494 هنوز در cold compile واقعی است و اجرای source39612186978 برای
نسخهٔ a7c6fc8 پشت آن صف دارد؛ هیچ‌یک در این checkpoint شاهد تکمیل نصب یا transaction
بومیِ نسخهٔ 0f55e9c نیست. هیچ tag/release انجام نشده و هر شش گیت توزیع بازند.


## ۲۰۲۶-۱۰-۲۵ — شاهد نصب واقعی دریافت شد؛ نه تحویل delta/rollback

اجرای source39612186978 روی a7c6fc8 واقعاً موفق شد. آرشیو نصب12359170810 با
SHA-256 `7950a3add7cfab2b2bc0c2986b12f430bac46cd62676f17e009ea570ed7a15d0`
بیرون این sandbox قابل دریافت مستقیم نبود؛ workflow بازیابی40182013261 هر دو
آرشیو اصلی را در runner احراز کرد، binder اصلی همان producer را دوباره بررسی
کرد و شاهد کامل را بدون اجرای دوبارهٔ app انتقال داد. هیچ فیلدی حذف نشد:
`phase3-installed-source21-evidence.json`،۹۴۹۱۰bytes با SHA-256
`6be7d5384c81511d30e009b412808c185c472dcd4903d292913f853a01db3ef3`.

دو پردازش مستقل4016/6596 و هشت PDF واقعی تک/چهارصفحه‌ای، باینری‌های Source21
از مسیر انتخابی فارسی/فاصله/!&، migration/seed/factory/renderer واقعی و حفظ
ID/session/secret شاهد دارند. این شاهد، runtime a7c6fc8 را پوشش می‌دهد، نه ادعای
transaction نسخه‌های بعدی یا پذیرش دادهٔ نصب واقعی کاربر.

هدف بومی بعدی از ساخت سرد مستقل، worktree جدا و cache خاموش تهیه خواهد شد؛
همان۲۰درخت source احرازشده با /Od /Ob0 /DNDEBUG، نه دستکاری DLL یا marker نسخه.
تفاوت واقعی بخش اجرایی PE.text، audit مستقل۲۱DLL، دستورهای کامل Ninja و اجرای
تابع واقعی Pango الزام است. کد این کنترل اضافه شد؛ نتیجهٔ Windows هنوز ثبت
نشده و حتی موفقیت آن به‌تنهایی اثبات delta/rollback نخواهد بود.

ممیزی امروز۹ advisory تازهٔ Python در brotli/filelock/pypdf یافت. نسخه‌های
اصلاح‌شده1.2.1/4.2.1/6.21.2 با hashهای lock ثبت شدند، بدون ignore. برای سازگاری
با filelock4، resolver نسخهٔ اختیاری LiteLLM را1.103.9 انتخاب کرد چون1.105.1
filelock<4 می‌خواهد؛ boto3/botocore حداقل سازگار1.43.117 شدند. این تغییرها در
checkpoint ثبت شده‌اند؛ ادعای پاک‌بودن همهٔ DLLهای native/CRT نیست.

پس از تغییر lock:۱۱۱۸PASS در104.15s، صفرfail/error/skip؛ Ruff/Mypy90/BanditCI
موفق و pip-audit بدون آسیب‌پذیری شناخته‌شدهٔ وابستگی‌های خارجی. مورد app محلی
در PyPI موجود نیست و skip ممیزی آن، waiver وابستگی ثالث نیست.

مسیر بعدی همین فاز: نتیجهٔ ساخت هدف بومی، transaction واقعی از API با رضایت،
rollback و حفظ حسابداری/شناسه/session/secret/receipt، faultهای helper و
crash/stale-lock. همهٔ۶گیت باز؛ نسخهٔ عمومی1.0.10 و نصب/دادهٔ کاربر تغییر نکرده‌اند.


### اصلاح تکمیلی رسید terminal و cleanup (هنوز transaction بومی نیست)

API خصوصی حتی رسید committed/rolled_back با PID و attempt صحیح را تا باقی‌ماندن
هر کدام از سه guard مربوط به channel/native/write، نتیجهٔ نهایی نمی‌داند:
applying/unverified حفظ می‌شود. helper علاوه بر role، schema و hash آرشیو و
anchorهای قدیم/هدف، تطابق exit-code/state و anchor جاری را کنترل می‌کند و
مالکیت channel را قبل از انتشار نتیجه و دوباره قبل از حذف قفل بررسی می‌کند.
صرف journal پایدار دیگر کافی نیست؛ guardهای stale خودکار حذف نمی‌شوند.

۹ کنترل مصنوعی جدید؛ کل suite۱۱۲۷PASS در123.87s بدونfail/error/skip.۱۴ fault
مصنوعی نیز خود بلوک AST همان helper را در runner ویندوز اجرا خواهند کرد؛ نتیجهٔ
جدید ویندوز هنوز مشاهده نشده است. این‌ها fault واقعی compiled-helper/native
transaction یا اثبات crash recovery نیستند. Source40183092030 روی55e65f5 هنوز
cold compile است؛ preflight محدود همان commit شمارهٔ40183092159 موفق شد، نه
تأیید بومی این اصلاح بعدی. هیچ گیت انتشار/حقوقی بسته نشده است.


### نتیجهٔ ویندوزِ اصلاح رسید — موفق، با دامنهٔ محدود

کد a14e7f0 در preflight40183597690/job121139605976 موفق شد؛ هر۱۴ fault مصنوعیِ
بلوک AST واقعی helper، کنترل‌های byte/anchor و مکانیک Inno محدود موفق‌اند.
CI کامل40183597682 نیز هر۵ job موفق است. این نتیجه، actual compiled-helper
native transaction را ثابت نمی‌کند. رسید دقیق در
`docs/dependencies/phase3-helper-terminal-cleanup-checkpoint.json` ثبت شد.

اجرای source/codegen40183092030 روی55e65f5 هنوز در کامپایل سردِ sourceهای پایه
است؛ نتیجهٔ هدف native متفاوت و transaction واقعی و crash recovery هنوز نداریم.
فاز۳ ناقص است؛ نصب/دادهٔ کاربر، نسخهٔ عمومی1.0.10 و مجوز انتشار تغییر نکرده‌اند.


## اتصال آزمون transaction واقعی به API (اجرا هنوز در انتظار)

`phase3_native_transaction.py` کلاینت بیرونی TCP است؛ app را import نمی‌کند و
هیچ factory/renderer/seed/migration یا مرز process را mock نمی‌کند. پس از نصب
Inno همان برنامه، feed موقت با امضای واقعی Ed25519 عرضه می‌شود؛ تأیید دقیق
نسخه/SHA با cookie مالک، CSRF و sudo از همان API انجام می‌شود. مجوز اشتباه
باید رد شود. دریافت full setup به endpoint خطا می‌خورد و هر فایل payload
دست‌نخورده در delta رد می‌شود. DLL Pango با codegen واقعاً متفاوت و helper
واقعاً کامپایل‌شدهٔ متفاوت باید جایگزین شوند؛ helper اجرایی همان clone قدیمیِ
احرازشده است، نه helper دانلودی.

مسیر موفق99.30.0/A→99.30.1/B؛ سپس بستهٔ جدید99.30.2/A با اجازهٔ API و شکست
صریح AFTER_APPLY (پیش از startup هدف) برای اثبات بازگشت به99.30.1/B. این شکست،
crash یا migration خرابِ هدف را شبیه‌سازی نمی‌کند و آن‌ها هنوز آزمون جدا لازم دارند.
Selector این fault تنها در scope خصوصی CI با schema2/مالکیت نصب و mode دقیق
فعال است؛ environment به‌تنهایی مسیر عمومی را تغییر نمی‌دهد.

سند حسابداری واقعی posted با مقادیر scaled و receipt واقعیِ ساختگی از API
ساخته می‌شوند. کل dump منطقی DB (نه فقط جمع یا چند جدول)، IDها/ردیف‌های امنیتی،
session.secret و cookie قبلی بدون login تازه، بایت receipt، مجموعهٔ دقیق فایل‌ها،
manifest/anchor و PDFهای واقعی و originهای۲۱DLL مقایسه خواهند شد. مشاهدهٔ HTTP503
فقط اگر واقعاً رخ دهد ثبت می‌شود؛ unit test جای شاهد timing بومی نیست. cleanup
فقط graceful و متعلق به همین profile؛ قفل recovery خودکار پاک نمی‌شود.

محلی:۱۱۳۷PASS در101.62s، صفرfail/error/skip؛ Ruff/Mypy90/BanditCI/pip-audit
موفق.۱۰کنترل تازه صرفاً پروتکل/selector مصنوعی‌اند. اجرای جدید در صف ساخت سرد
پشت40183092030 خواهد بود؛ کد جدید را به اجرای قدیمی55e65f5 نسبت نمی‌دهیم.
Native delta/rollback و crash/stale-lock هنوز اثبات نشده، همهٔ۶گیت بازند.


### تأیید CI کلاینت، نه اثبات بومی

کد dcc60bf در CI40185685126 هر۵ job موفق و در preflight ویندوز40185685167/
job121145863648 موفق است؛ کنترل‌های پروتکل/selector و parse کامل PowerShell نیز
موفق‌اند. Source40183092030 روی55e65f5 اکنون compile/audit پایه را گذرانده و
به HTTP متعلق به app رسیده، نه هدف codegen و نه transaction جدید.

بودجهٔ job جدید۱۸۰دقیقه شد چون شامل دو ساخت سرد مستقل است؛ اجرای تاریخی تک‌ساخت
۶۴دقیقه زمان برده بود. پس از مقایسهٔ کامل حفظ داده/secret/session، sudo از همان
API با password واقعی تمدید می‌شود تا expiry عادی۵دقیقه‌ای با خرابی به‌روزرسانی
اشتباه نشود؛ هیچ TTL یا auth bypass یا login مجددی اضافه نشده است. پس از این
اصلاح، suite دوباره۱۱۳۷PASS در98.26s بدونfail/error/skip؛ ویندوز و native این
follow-up هنوز مشاهده نشده‌اند. فاز۳ ناقص و هر۶گیت باز است.


## بررسی کامل Python کپی‌شدهٔ قدیمی پیش از اجرا

CI اصلاح36a99fd با40186562664 هر۵job موفق و preflight40186562661 موفق شد.
اجرای40183092030 روی55e65f5 اکنون از نصب/HTTP عبور کرده و از11:06:58Z به ساخت
سرد مستقل NativeB رسیده؛ audit و نتیجهٔ NativeB هنوز جمع نشده است. اجرای جدید
تراکنش واقعی پشت آن در صف است؛ push بعدی ممکن است طبق concurrency گیت‌هاب
pending قبلی را جایگزین کند، نه اجرای سردِ فعال را.

خلأ مشاهده‌شده: helper پیش از Copy-Item همهٔ Python قدیمی را بررسی می‌کرد، اما
کپی را دوباره hash نمی‌کرد. اکنون تابع واقعی Assert-PrivatePythonClone پیش از
هر اجرای Python خارجی، کل مجموعهٔ فایل‌ها، اندازه و SHA را با manifest مستقل
قدیمی مقایسه می‌کند و فایل اضافه/گم‌شده/خراب و reparse/junction در root یا
اجداد یا زیرشاخه و path مبهم را رد می‌کند. python.exe هم باید anchored باشد.

۱۲کنترل تازه از AST همان تابع واقعی با بایت‌های opaque اضافه شد: صحیح، ناقص،
خرابی هم‌اندازه، missing، extra مخفی، case تکراری، فرار مسیر، نبود executable،
junction دایرکتوری/root، خرابی nested و تغییر مبدأ پس از کپی. هیچ exe یا DLL
ساختگی اجرا نمی‌شود؛ این‌ها نه native proof و نه crash recovery هستند. نتیجهٔ
Windows این تغییر هنوز مشاهده نشده است. suite کامل محلی۱۱۳۷PASS در82.54s،
صفرfail/error/skip و Ruff/Mypy90/Bandit/pip-audit موفق؛ پروژهٔ محلی روی PyPI نیست.
هر۶گیت باز، فاز۳ ناقص و نصب/دادهٔ واقعی کاربر و مجوز انتشار بدون تغییر است.


### شاهد شکست را با کنترل‌های موفق مخلوط نمی‌کنیم

در40183092030 مرحلهٔ ساخت هدف مستقل NativeB شکست خورد؛ artifact12597309662 با
۲۷۱۱۱بایت موجود است. علت هنوز جمع نشده، چون دانلود artifact و لاگ از sandbox
EOF است. workflow جدیدِ فقط‌خواندنی metadata اجرای دقیق و digest بستهٔ اصلی را
احراز و tail محدود build.log/step اصلی را در annotations منتقل می‌کند؛ نه rebuild
می‌کند و نه فایل شاهد را تغییر می‌دهد. CI و۱۲کنترل clone موفق جای این شکست نیستند.
همان۱۲کنترل برای Windows PowerShell5.1 میزبان ps2exe هم اضافه شد؛ نتیجه هنوز نداریم.
اجرای جدید40189290222 روی7bb72e0 فعلاً stock preflight است، نه transaction جدید.
محلی با all-extras frozen دوباره۱۱۳۷PASS در76.26s و audit بدون آسیب‌پذیری شناخته‌شده؛
پروژهٔ محلی در PyPI نیست. crash/stale-lock و دلتا/rollback واقعی هنوز اثبات نشده‌اند.
