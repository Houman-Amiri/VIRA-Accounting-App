# اتصال خصوصیِ bootstrap متعلق به برنامه، SDK/Windows — ۲۰۲۶-۱۰-۱۹

> **اتصال واقعی خصوصی موفق است؛ فقط SDK۲۷.** این نتیجه startup عادی نصب‌شده،
> source21، مجوز توزیع یا پذیرش کاربر نیست. نصب و رفتار پیش‌فرض تغییر نکردند.

## چه چیزی به خود برنامه منتقل شد؟

`activate_private_sdk(plan)` در `app/private_pdf_bootstrap.py` افزوده شد. APIهای
قدیمی `verify_private_plan` و `prepare_private_plan` همچنان فقط‌خواندنی‌اند؛ استفادهٔ
صریح از context جدید است که محیط خصوصی را فعال می‌کند. ورودی همان plan داده‌ای است،
نه snapshot قدیمی، renderer callback، configuration factory یا hook اجرایی QA.

context، preflight کامل و guardهای Windows/CI/3.11/isolated/no-site/UTF-8 و مبدأ
کد/interpreter/profile را اجرا می‌کند؛ در مرز فعال‌سازی دوباره payload را تأیید
می‌کند. سپس TEMP خصوصی، native DLL directory و sys.path را کنترل می‌کند، **CFFI را
پیش از ctypes/app/WeasyPrint وارد و libffi SDK را با مسیر کامل pin می‌کند**؛ ACP
واقعی 65001 و مبدأ preload و هر DLL متعلق به inventory که از قبل mapped باشد را
بررسی می‌کند. native object یا handle از API خارج نمی‌شود؛ فقط diagnostics immutable.

preload و DLL-directory handle در تمام طول body زنده می‌مانند. پس از خروج، handle
بسته و env/path/TEMP بازگردانده می‌شوند. فقط temporary directory متعلق به همین
scope و leaf تازه‌ساخته‌شده پاک می‌شوند؛ حذف recursive از state کاربر نداریم.
این کار **DLLهای OS یا moduleهای importشده را unload/rollback نمی‌کند**؛ ورود دوباره
به activation به process تازه نیاز دارد و guard import زودهنگام آن را تحمیل می‌کند.

workspace bootstrap در هر process تازه و جدا از state پایدار HTTP است؛ بنابراین
قرارداد fresh/empty قبلی ضعیف نشده و DB در restart نیز ثابت می‌ماند. `cache_root`
snapshot قبلی به معنای تغییر cache route نیست؛ cache/config هر PDF هنوز در service
خود برنامه و با همان `PrivatePdfPolicy` مدیریت می‌شود.

## نقش محدود caller خصوصی

entry جدید `scripts/pdf_bootstrap_http_entry.py` فقط فایل ثابتِ app را اجرا می‌کند؛
پیش از اجرای آن، digest خارجی manifest و hash/size خود module را کنترل می‌کند.
اعتبارسنجی کامل و native setup در app است، نه در entry. پس از activation، worker
ثابت HTTP قبلی با mode app-owned اجرا می‌شود؛ migrator/factory/Uvicorn/lifespan،
fixtureسازی و آزمون HTTP همچنان توسط QA خصوصی هدایت می‌شوند. این را با راه‌انداز
تولید یا حذف همهٔ مسئولیت‌های QA اشتباه نمی‌گیریم.

driver و workflow جدید مستقل‌اند؛ launcherهای تاریخی و مسیر گرانِ cold-source
تغییر نکردند. renderer و configuration factory جایگزین نشده‌اند؛ snapshotهای
تاریخیِ preparation/SDK/source تغییر نکرده و اثبات این اتصال تازه نام نگرفته‌اند.

## شاهد واقعی Windows

[اجرای 39286484245](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39286484245)،
commit `d5e5f57c55d38bbb24f6df04634c846c901e54a9` و job `118174226710` موفق‌اند.
[شاهد مستقل](../dependencies/pdf-bootstrap-sdk-http-evidence.json) **45583 بایت**،
SHA256 `ac0aa31d6854c541bbaba6be52e3865da9d1a4d77f25b84cab2a77a97857813d` است؛
دو بخش annotation کامل با digest مستقل از همان check/job/head بازیابی و احراز شد.
[provenance](../dependencies/pdf-bootstrap-sdk-http-proof.json) به artifact metadata
شمارهٔ `12204790607` وصل است؛ **ZIP در sandbox مستقلاً دانلود یا hash نشده است**.
Hashهای کد در provenance مربوط به bytes canonical مخزن‌اند، نه ادعای bytes فایل
PS1 با CRLF در payload ویندوز؛ baseline خصوصی bytes واقعی payload را جداگانه می‌بندد.

- PIDهای تازهٔ **2352 و 9096**، workspaceهای bootstrap جدا، همان SQLite و IDها؛
  ۴ PDF در هر process، مجموع **۸ PDF جدید واقعی** از route عادی؛ ۱/۴ صفحهٔ A4.
- TCP واقعی، login/CSRF، رد دسترسی بدون مجوز و login غلط، SPA ساخته‌شده، OpenAPI،
  migrator، lifespan و graceful shutdown کنترل شدند.
- وزیرمتن ۴۰۰/۷۰۰، ۳۰ رقم Regularِ ASCII/فارسی/عربی و ۱۰ فارسی Bold، hash دو TTF،
  صفر قلم سیستم، font/cache مستقل و پاک‌سازی هر ۸ سند با inspector بیرون app تأیید شد.
- ۲۷ DLL از candidate خصوصی، Pango 1.58.2؛ ACP 65001، no-site/isolated/UTF-8،
  هویت callableهای app و عدم QA renderer/configuration-factory replacement تأیید شد.
- بعد از body، بازگردانی env/path/TEMP و حذف پوشهٔ TEMP bootstrap کنترل شد؛ baseline
  payload در هر دو process سالم ماند.
- چهار negative واقعی: بدون no-site، ctypes زودهنگام، inventory digest غلط و فایل
  Python خارج از manifest؛ همگی fail-closed و بدون receipt موفقیت رد شدند.
- دو client موازی، اما peak چرخهٔ سند در هر دو process **۱** بود. `BEGIN IMMEDIATE`
  تغییر نکرد؛ throughput یا دو native renderer هم‌زمان ادعا نمی‌شود.

## آزمون‌های خودکار و CI

۲۰ تست تازهٔ **ساختگی** برای lifetime، revalidation، عدم قبول snapshot به‌عنوان
مجوز activation، ترتیب pin، بازگردانی success/error/KeyboardInterrupt، ACP غلط،
foreign/missing native، leak و close failure، و binding/عدم اجرای module تغییرکرده.
یک تست دیگر integrity شاهد واقعیِ ضبط‌شده را کنترل می‌کند؛ pytest خودش native
Windows تازه تولید نمی‌کند. ۹۴ کنترل preparation قبلی نیز برقرارند.

**۸۸۱ تست کامل، 92.58 ثانیه؛ صفر failure/error/skip**. Ruff، Mypy برای ۸۷ فایل،
گیت فعلی Bandit و کنترل MIT۱۴ موفق‌اند. CI عادی کد اجرایی `39286501715 / d5e5f57`
هر پنج job موفق است. commit نهاییِ witness/docs نیز جداگانه تا نتیجهٔ CI پیگیری می‌شود.

## مرزها و کار انجام‌نشده

Source21 همچنان از این plan/activator پذیرفته نمی‌شود؛ binding source audit، native
origin و اثبات مستقل لازم دارد. شواهد source قبلی تنها font dispatch قبلی را
ثابت می‌کنند، نه activation جدید. cold build جدید در این گام اجرا نشده است.

hash امضا نیست؛ بررسی cooperative است، نه ACL/hardlink/TOCTOU sandbox. receiptِ
modified PE مجوز تغییر/توزیع interpreter نیست؛ actual ACP فقط همین processهای
خصوصی ثابت شده است. حداقل Windows، امضا، CRT/EULA، تعویض DLL در نصب، native
Inno/delta/rollback و تحویل source عمومی پایدار هنوز تأیید نشده‌اند.

main/factory/route/settings، launcher نصب‌شده و stage script، version/tag/release،
schema، داده و محاسبات قیمت تغییر نکردند. فایل‌های جدید مانند source عادی app/scripts
ممکن است توسط stager موجود copy شوند، ولی هیچ startup نصب‌شده آن‌ها را انتخاب نمی‌کند.
هر **شش گیت باز** و MIT فقط همان **۱۴ فایل native-build** است، نه کد app/QA جدید.
از کاربر نصب، حذف برنامه یا دادهٔ تست درخواست نمی‌شود.
