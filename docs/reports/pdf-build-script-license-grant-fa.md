# اعمال تأیید مالک: MIT فقط برای فایل‌های ساخت PDF

تاریخ: ۲۰۲۶-۱۰-۱۸

پاسخ «بله» مالک به سؤال محدودِ مجوز اسکریپت‌ها و تنظیمات ساخت PDF اعمال شد.
**مجوز کل برنامهٔ حسابداری تغییر نکرده است؛ این پاسخ اجازهٔ انتشار نسخه یا
runtime بومی نیست.**

## دامنهٔ دقیق، بدون wildcard

[متن کامل MIT](../../LICENSES/VIRA-PDF-BUILD-MIT.txt)،
[راهنمای دامنه](../../LICENSES/README.md) و
[manifest نسخه‌ها/هش‌ها](../dependencies/pdf-build-script-license-scope.json)
ثبت شدند. Copyright برابر `Copyright (c) 2026 VIRA contributors` است.
فقط محتوای VIRA-authored این ۹ فایل مرجع و مشتقات مجازشان تحت MIT قرار دارند:

| فایل | نقش |
|---|---|
| `scripts/source_pdf_build.ps1` | ساخت نامزد بومی خصوصی از vcpkg پین‌شده |
| `scripts/source_pdf_inventory.py` | گردآوری سورس/recipe/مالکیت native |
| `scripts/pdf_runtime_inventory.py` | helper بررسی closure و PE موردنیاز inventory |
| `native/pdf-source/vcpkg.json` | تنظیمات منابع ساخت |
| `native/pdf-source/triplets/x64-vira-pdf.cmake` | تنظیمات target |
| `native/pdf-source/triplets/x64-vira-pdf-host.cmake` | تنظیمات host |
| `.github/workflows/pdf-source-proof.yml` | پیکربندی proof ساخت |
| `native/pdf-source/README.md` | دستورهای مرتبط با ساخت |
| `scripts/check_pdf_build_license.py` | checker و تهیهٔ سایدکار محدود همین مجوز |

این مجوز به backend، frontend، installer، کد مالی، فایل‌های نامشمولِ staging،
منابع upstream، DLLها، فونت‌ها یا CRT تعمیم داده نشده است. مجوزها و notices اشخاص
ثالث همچنان مستقل‌اند. فایل `LICENSE` سراسری برای مخزن ایجاد نشده است.
محدودیت BLOCKED بیانگر تصمیم آمادگی انتشار پروژه است، نه شرط اضافه بر حقوق MIT.

## آزمون‌پذیری و اتصال به سورس قبلی

- checker با کتابخانهٔ استاندارد Python، دامنهٔ دقیق ۹ فایل، متن MIT، هش‌های مرجع،
  محدودبودن رضایت و باقی‌ماندن وضعیت runtime را کنترل می‌کند.
- نرمال‌سازی فقط CRLF به LF است تا checkout ویندوز معتبر بماند؛ Unicode یا تغییر
  واقعی کد پنهان نمی‌شود. scope گسترده، wildcard، مجوز ناقص/عوض‌شده، محتوای
  متفاوت و symlink رد می‌شوند.
- ۷ فایلِ موجود در آرشیو قبلی با نسخهٔ commit ساخت
  `2ec79b82ccebc89d754dbe25c10aeef4c31d8738` پس از همین نرمال‌سازی برابرند؛ این
  مقایسه با Git انجام و مسیر هر عضو در manifest ثبت شد. آرشیو قبلی دست‌نخورده
  است؛ صرف اعطای مجوز، دلیل کامپایل مجدد کتابخانه‌ها یا عوض‌کردن هش سورس نیست.
- `--sidecar` فقط فایل‌های مشمول، متن MIT، scope و README را در یک مسیر **جدید**
  کپی می‌کند؛ مسیر موجود را بازنویسی نمی‌کند. هیچ DLL/EXE/DB یا فایل نامشمولِ
  برنامه افزوده نمی‌شود. helper قبلاً مفقودِ `pdf_runtime_inventory.py` اکنون
  در این ضمیمه وجود دارد؛ دو فایلِ خارج از ZIP قدیمی، همین helper و checker هستند.
- workflow ممیزی مجوز، این ضمیمه را کنار ZIP اصلی در artifact بررسی داخلی
  می‌گذارد؛ این هنوز نگهداری موقت است، نه تحویل پایدار سورس به دریافت‌کننده.

```bash
python scripts/check_pdf_build_license.py
python scripts/check_pdf_build_license.py --sidecar /path/to/new-licensed-build-files
```

[نتیجهٔ ماشین‌خوان](../dependencies/pdf-build-script-license-check.json).
متن MIT و اعلان copyright باید همراه نسخه‌ها/بخش‌های قابل‌توجهِ فایل‌های مجاز حفظ
شوند. سایدکار را نباید «کل workflow مستقل» یا «SDK آفلاین» معرفی کرد؛ workflow
قدیمی هنوز فایل‌های app/staging خارج از این دامنه را فراخوانی می‌کند.

## نتایج آزمون

- **۲۴ تست جدید** دامنه، مجوز، نسخه‌ها، UTF-8/CRLF، کپی محدود و عدم بازنویسی.
- **۵۷ تست متمرکز** شامل verifier و ابزار notices پیشین، همگی موفق.
- **۴۶۲ تست کامل بک‌اند** موفق، ۶۵٫۵۸ ثانیه؛ بدون skip جدید.
- Ruff، Mypy روی ۸۴ فایل app و Bandit با threshold رسمی app و بدون کاهش threshold
  برای checker جدید موفق‌اند.
- نتیجهٔ CI این تغییر پس از push به این گزارش متصل می‌شود؛ موفقیت اجرای قبلی
  به جای اجرای تغییر جدید جا زده نمی‌شود.

## وضعیت باقی‌مانده

زیرگام **اجازهٔ مالک برای فایل‌های مشخص ساخت** انجام شد. گیت ترکیبی
`BUILD_SCRIPT_PERMISSIONS_AND_COMPLETENESS` عمداً بسته نشد: کامل‌بودن دستور ساخت
مستقل هنوز جداست و اجازهٔ فایل‌های نامشمول از این پاسخ استنباط نشده است.
شرایط CRT/SDK، بررسی اجزای کتابخانه‌ها، تحویل واقعی سورس، جایگزینی سازگار LGPL،
bootstrap و native update/rollback همچنان بازند.

هیچ نسخه، تگ، Release، بستهٔ DLL یا نصب جدید منتشر نشد؛ موتور جدید به stage عادی
متصل نشد؛ داده و محاسبات دست نخورده‌اند. آزمون کسب‌وکار روی نصب کاربر نیز طبق
درخواست قبلی به بعد موکول است، نه تأیید‌شده فرض شده است.
