# راه‌انداز خصوصیِ PDF پیش از import — ۲۰۲۶-۱۰-۱۹

> **راه‌انداز خصوصی با SDK پین‌شده در ویندوز تأیید شد.** این شاهد به معنی startup
> کامل HTTP، مصرف ۲۱ DLL سورس‌ساخته‌شده توسط entry جدید یا مجوز نصب/انتشار نیست.

## دامنهٔ این گام

پس از اثبات Unicode در worker مرحلهٔ قبل، ورود به آن worker از یک entry point
خصوصی و قابل‌ممیزی آزموده می‌شود: بررسی payload و pin کردن libffi **پیش از import
کد PDF برنامه، ctypes و WeasyPrint**، با CPython جداشده و site غیرفعال.

این گام فقط از **SDK پین‌شدهٔ upstream و ۲۷ DLL** استفاده می‌کند. نه ساخت تازهٔ
۲۱ DLL از سورس است، نه قبولی ترکیبِ launcher جدید با باینری‌های سورس‌ساخته‌شده.
[شاهد قبلیِ ۲۰ درخت/۲۱ DLL](../dependencies/pdf-unicode-bootstrap-proof.json)
تاریخی و دست‌نخورده می‌ماند؛ به launcher جدید نسبت داده نمی‌شود.

راه‌انداز نصب‌شدهٔ `start_vira.cmd`، staging عادی، Inno، updater، DB/schema،
محاسبات و شمارهٔ نسخه تغییر نکرده‌اند. این entry فقط روی Windows CI، زیر
RUNNER_TEMP، با version خصوصیِ دقیق کار می‌کند. سرور HTTP/uvicorn یا مسیر واقعیِ
ورود مالی برنامه هنوز از این entry راه‌اندازی نشده است؛ آن قبولی جداگانه می‌خواهد.

## طراحی و قرارداد اجرایی

- `scripts/pdf_private_launcher.py` تا پایان اعتبارسنجی payload فقط stdlib را
  import می‌کند. اجرای خصوصی باید صریحاً **`-I -S -B -X utf8`** داشته باشد:
  محیط Python و user-site کنار گذاشته می‌شوند؛ global-site، `.pth` و
  sitecustomize خودکار هم با `-S` اجرا نمی‌شوند. راه‌انداز invocation نادرست را
  رد می‌کند؛ ادعا ندارد اثرِ کدی را که قبلاً اجرا شده، خنثی می‌کند.
- حضور قبلیِ app، ctypes، cffi، WeasyPrint، uvicorn و sitecustomize/usercustomize
  قبل از ادامه رد می‌شود. بعد از pin، غیبت app/WeasyPrint/uvicorn دوباره ثبت می‌شود.
- هش مستقل inventory و هش فایل baseline از harness بیرونی دریافت می‌شوند؛ launcher
  آن‌ها را از payload دست‌کاری‌شده به‌عنوان مرجع تازه محاسبه و جایگزین نمی‌کند.
  همهٔ فایل‌های baseline از نظر مسیر امن، اندازه و SHA256 بررسی می‌شوند؛ entryهای
  تکراری/case-aliased، JSON با کلید تکراری، traversal، drive/ADS ویندوز و symlink
  خارج از root رد می‌شوند. فایل‌های کلیدی از جمله entry، worker، EXE، cffi و دو
  helper PDF باید در baseline حاضر باشند. DLLها باید هم در baseline و هم inventory
  منطبق باشند. این کنترلِ پیوستگی QA است، **نه امضای انتشار یا دفاع مستقل در برابر
  مهاجمی که خود launcher و harness را کنترل می‌کند**.
- SDK با SHA256
  `ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53`
  و وضعیت BLOCKED محدود است؛ origin سورس‌ساخته‌شده یا مجوزسازیِ صوری پذیرفته نیست.
- نسخهٔ private EXE با PE manifest تغییرکرده، همان قرارداد مرحلهٔ قبل را دارد؛
  هر دو هش EXE و private status بررسی می‌شوند. CPython upstream دست‌نخورده ادعا
  نمی‌شود و minimum-OS/notices/امضای تولید همچنان موضوع بازبینی‌اند.
- TEMP آغازین هم زیر پروفایل فارسی است. مسیر DLL صریح می‌شود، سپس نخستین import
  ثالث، cffi است؛ libffi با **مسیر کاملِ بررسی‌شده** preload و بعد ctypes وارد
  می‌شود. مقدار واقعی ACP باید **۶۵۰۰۱** و مبدأ DLL دقیقاً private/native/pdf/bin باشد.
- فقط worker ثابتِ موجود، پس از کنترل baseline، با `runpy` اجرا می‌شود؛ target
  دلخواه یا shell evaluation وجود ندارد. worker همچنان configuration حافظه‌ای
  سند، صفر قلم سیستم، UTF-8، callbackها، DLLهای واقعی، TTFهای TEMP و پاک‌سازی را
  مستقل کنترل می‌کند. در پایان handle، argv، sys.path و محیط تغییرکرده restore می‌شوند.
- دو اجرای تازه با PIDهای متفاوت از همان app/profile/state و CWD نامرتبطِ فارسی/
  فاصله‌دار انجام می‌شوند. baseline و inventory باید در هر دو یکسان بمانند.

## شکست آماده‌سازی و اصلاح workflow

اجرای نخست **39181465353 / fac5219** در مرحلهٔ setup شکست خورد؛ خود launcher و
رندر در آن اجرا نشدند. signed log از sandbox قابل دریافت نبود؛ متن اصلیِ stderr
**نامعلوم** است و برای آن قبولی رندر یا علت قطعیِ استنباطی ثبت نشده است.

بازبینی workflow یک عیب قطعی یافت: fixture مقدار `VIRA_PDF_UPSTREAM_ARCHIVE` را
در GITHUB_ENV می‌نویسد و این مقدار فقط در **step بعدی** قابل استفاده است؛ نسخهٔ
اول در همان step آن را مصرف می‌کرد. consumer به step مستقل منتقل شد. transcript
آماده‌سازی و annotation محدودِ failure هم اضافه شد تا خطاهای دیگر قابل تشخیص باشند.
فرمان‌ها، assertions، SHAها، exit status و شرط موفقیت کاهش نیافته‌اند.
[رکورد احرازشده](../dependencies/pdf-private-launcher-setup-failure.json).

## کنترل‌ها و نتیجه

- **۴۲ کنترل رفتاری/workflow تازه و دو کنترل دائمیِ شاهد** برای payload، دو digest مستقل، تغییر EXE/worker/cffi/DLL،
  path escape در دو OS، symlink، case alias، JSON تکراری، رد source origin، وضعیت
  حقوقی صوری، سیاست preload، تک‌تک flagها و import زودهنگام؛ یک subprocess واقعیِ
  `-I -S` نیز stdlib-only بودن خود ماژول entry را می‌سنجد.
- اجرای کامل محلی: **۶۷۰ بک‌اند موفق**؛ این‌ها جای شاهد بومی Windows نیستند.
- مجموعهٔ متمرکز PDF: **۳۱۲ تست موفق**؛ شاهد بومی مستقل همچنان همان run ویندوز است.
- Ruff، Mypy برای ۸۵ فایل، gate موجود Bandit متوسط/شدید و MIT محدودِ ۱۴ فایل موفق‌اند.

### شاهد واقعی launcher

**[39182480848 / 8118098](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39182480848)
موفق**؛ job **117837988270**. دو PID مستقل **۱۵۲۸ و ۳۱۱۲**، با همان inventory و
baseline؛ `no_site=isolated=utf8_mode=1`، ACP **۶۵۰۰۱**، app/WeasyPrint/uvicorn
قبل از entry غایب و libffi از مسیر دقیقِ private/native/pdf/bin بار شد.

هر دو worker هر ۲۷ DLL SDK را واقعاً از app فارسی بار کردند؛ PDF یک/چهارصفحه‌ای
A4، وزیرمتن ۴۰۰/۷۰۰ و هر ۳۰ رقم کنترل شد. TTFهای TEMP با هش asset برابر و پس از
هر سند حذف شدند؛ صفر قلم سیستم در configuration فعال، callbackها و نبود dependency
توسعه هم تأیید شدند. TEMP آغازین launcher خالی باقی ماند و restoreِ محیط در finally
انجام شد. این restore جای آزمون launcher بلندعمر/HTTP را نمی‌گیرد.

سه کنترل منفی واقعی در ویندوز هم موفق بودند: حذف `-S`، import زودهنگام ctypes
و digest نادرست inventory هر سه exit غیرصفر با خطای مورد انتظار داشتند و proof
موفق تولید نکردند. دو اجرای مثبت پس از آن واقعاً کامل شدند؛ هیچ failure به قبولی
تبدیل یا تستی skip نشد.

- [proof](../dependencies/pdf-private-launcher-proof.json) و
  [شاهد کامل](../dependencies/pdf-private-launcher-evidence.json): **۳۷۳۰۶ بایت**،
  **۳ قطعهٔ annotation احرازشده**؛ SHA256:
  `12e65fb720f6096495d43822504b3e605d74eba1af6842256ef9ca95ac216d79`.
- artifact **12156887183** با نام
  `private-pre-import-launcher-pdf-evidence-no-dlls-not-source-proof`؛ private و
  ۹۰روزه است، نه تحویل عمومی و پایدار سورس. باینری app/Python/DLL آپلود نشده است.
- Pango اجراشده **1.58.2** SDK است، نه Pango نشانه‌گذاری‌شدهٔ سورس‌ساخته‌شده.

### failureهای زیرساخت و محدودیت اتصال

اجرای **39181776992 / 7bf27da** در `prepare_pdf_native_fixture.ps1:11` با timeout
واقعی `Invoke-WebRequest` متوقف شد؛ سرویس CreateArtifact هم پس از پنج تلاش خود
هم timeout داد. launcher در آن اجرا نشد. transcript و annotations علت این بار
را ثبت کردند؛ علت دقیق failure نخست همچنان نامعلوم است و بازنویسی نشده است.

بازاجرای مستقیم همان run از API با **403 / Resource not accessible by integration**
رد شد؛ rerun انجام نشد. برای این قابلیت، دسترسی Actions اتصال GitHub در Arena
نیاز به بازبینی/بازوصل دارد؛ هیچ رمز یا token درخواست یا ذخیره نشد. Git fetch/push
کار می‌کرد؛ checkpoint بعدی یک regression واقعی برای ترتیب stepهای GITHUB_ENV
افزود و workflow عادیِ push آن مستقلاً موفق شد. SHA SDK، کنترل‌های منفی و شرط
موفقیت تغییر نکردند و retry یا قبولیِ فرضی به run شکست‌خورده نسبت داده نشد.

### CI عمومی

**[39182480838 / 8118098](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39182480838)**
با هر پنج job موفق بسته شد؛ در این snapshot تعداد بک‌اند **۶۶۸** است. دو کنترل
آفلاینِ شاهد پس از دریافت نتیجهٔ واقعی اضافه شدند و اجرای کامل محلی بعد از آن
**۶۷۰** مورد موفق دارد. تست‌های Windows، frontend، مرورگر و قرارداد API نیز
موفق‌اند؛ rollbackهای موجود، اثبات native update/rollback جدید تلقی نشده‌اند.

CI پس از اضافه‌شدن دو کنترل شاهد نیز کامل شد:
**[39183163132 / f0fc401](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39183163132)**،
هر **پنج job موفق**؛ مجموعهٔ محلی ۶۷۰ تست بدون failure یا skip است. سه workflow
وابسته هم مستقل موفق‌اند: آماده‌سازی مواد مجوز **39183163134**، مونتاژ/بازبینی kit
**39183163147** و kit کامل سورس اصلاح‌شده **39183163195**. این workflowها مونتاژ/
بازبینی‌اند، نه ساخت تازهٔ ۲۱ DLL یا مجوز انتشار.

[رکورد دائمیِ CI](../dependencies/pdf-private-launcher-final-ci.json) دقیقاً به
**f0fc401** بسته است؛ commit پس از آن فقط ثبت همین نتیجه و گزارش است. فایل‌های
runtime/worker/workflow با producer ویندوز **8118098** مقایسه شدند و تغییر نکرده‌اند؛
نتیجهٔ بومی به commit صرفاً مستندسازی نسبت داده نشده است.

## مرز تکمیل و ادامه

تمام شش گیت قبلی باز می‌مانند. مرحلهٔ امروز نباید به‌عنوان تکمیل startup واقعی
HTTP، اجرای launcher با ۲۱ DLL تازه از سورس، امضای EXE، بسته‌بندی Inno، native
update/rollback، تعویض LGPL DLL در نصب، حق CRT، تحویل عمومی پایدار سورس یا پذیرش
کاربر نصب‌شده معرفی شود. read-only بودن فایل TTF، ACL نصب را اثبات نمی‌کند؛ reuse
state هم cache hit دیسکی نیست. هیچ tag/release، تغییر نصب یا دادهٔ کاربر انجام نشده است.
