# آماده‌سازی dispatch و عمر قلم PDF متعلق به برنامه — ۲۰۲۶-۱۰-۱۹

## نتیجه و حدّ دقیق این مرحله

مسیر صریحِ **متعلق به خود برنامه** برای انتخاب و بستن منابع قلم آماده شد. این یک
مرحلهٔ آماده‌سازی کد و قرارداد است؛ **اجرای native/HTTP این wiring جدید در Windows
هنوز اثبات نشده است**. شاهد موفق قبلیِ source21 مربوط به کد قبلی و تزریق QA است و
برای این مسیر جدید بازنام‌گذاری نمی‌شود. انتشار، نصب، default تولید یا گیت حقوقی
با این مرحله تأیید نمی‌شود.

## تغییرات واقعی کد

- `app.services.pdf_rendering` شامل `PdfRenderer` و policy تغییرناپذیر
  `PrivatePdfPolicy(cache_root)` است. ماژول صرفاً با stdlib، حتی زیر `-I -S -B`،
  import می‌شود؛ در import آن app PDF/WeasyPrint/CFFI/ctypes/Uvicorn یا script QA
  بارگذاری نمی‌شود.
- factory برنامه keyword-onlyِ `private_pdf_policy` می‌پذیرد و renderer همان app
  را در `app.state.pdf_renderer` نگه می‌دارد. ورودی فقط policy داده‌ایِ typed است،
  نه callback، configuration factory یا renderer دلخواه. نوع اشتباه پیش از
  خواندن settings/ساخت database رد می‌شود.
- route پیش‌فاکتور اکنون از rendererِ **همان app در Request** استفاده می‌کند؛
  state سراسریِ انتخاب mode، monkeypatch در اجرای برنامه یا import از script QA
  اضافه نشده است. factory و route واقعاً تغییر کرده‌اند؛ ادعای «کد app تغییر نکرد»
  برای این مرحله نداریم.
- بدون policy، `LEGACY_DEFAULT` دقیقاً همان `pdf.render_pdf(template, context)`
  را بدون keyword اضافه صدا می‌زند. `pdf.py` و `pdf_fontconfig.py` تغییر نکرده‌اند.
  انتخاب خصوصی نه setting/env جدید دارد، نه پارامتر HTTP یا گزینهٔ UI. هیچ
  launcher نصب‌شده‌ای policy خصوصی را انتخاب نمی‌کند.

مثال قراردادی برای caller خصوصیِ دارای bootstrap بررسی‌شده:

```python
from app.main import create_app
from app.services.pdf_rendering import PrivatePdfPolicy

app = create_app(settings, private_pdf_policy=PrivatePdfPolicy(absolute_cache_root))
```

این مثال، دستور نصب یا bootstrap کامل نیست. caller هنوز باید interpreter/native
origin و baseline، preload، UTF-8 و ACP 65001 را **پیش از import موتور** احراز کند.
policy مسیر DLL انتخاب/دانلود نمی‌کند و حق بازتوزیع نمی‌دهد. guard نسخهٔ
WeasyPrint 70.0 و guardهای Windows در adapter موجود باقی‌اند.

## مالکیت منابع و خطا

در حالت `PRIVATE_EXPLICIT_FONTCONFIG` هر سند cache child اختصاصی می‌گیرد؛ adapter
خود برنامه configuration بومیِ همان سند را می‌سازد و می‌بندد. return بایت‌ها فقط
**پس از موفقیت cleanup** انجام می‌شود. مسیر absolute بدون traversal لازم است؛
فایل به‌جای directory، symlink در root/ancestor و root فایل‌سیستم رد می‌شوند.
root انتخابی یا فایل‌های نامرتبط آن حذف نمی‌شوند؛ فقط child متعلق به سند حذف می‌شود.
این کنترل cooperative است، نه ACL یا دفاع در برابر مالکِ دارای race/junction.

خطای ورود context، render، cleanup، خروجی غیر bytes/HTML و interrupt هم cache را
می‌بندند؛ retry با FontConfiguration پیش‌فرض نداریم. route همان fallback قبلیِ
HTMLِ self-contained با CSP و دو قلم inline را حفظ می‌کند؛ **HTML به معنی PDF
موفق نیست**. template، زمینهٔ سفارش/قیمت، محاسبه، قفل DB و تقویم تغییر نکرده‌اند.

## آزمون‌ها و شواهد

**۲۲ آزمون جدید**: مسیر/نوع/immutability policy، default بدون allocation، cache
جدا برای هر سند، حفظ sentinel نامرتبط، خطاهای enter/render/cleanup/نوع خروجی،
symlink/ancestor/file، interrupt، هم‌زمانی syntheticِ منابع، جداسازی دو app، عدم
انتخاب mode توسط env، تساوی OpenAPI دو mode و import زیر no-site. route واقعی
در ASGI با login/رد بدون مجوز و دادهٔ ساخته‌شده از API، انتخاب service و fallback
را بررسی می‌کند. fake bytes همگی با عنوان **FAKE/NOT-NATIVE** مشخص‌اند.

**۷۴۵ تست بک‌اند، بدون skip/failure/error، در 90.13 ثانیه موفق**؛ Ruff، Mypy برای
۸۶ فایل، Bandit با گیت موجود و کنترل MIT/۱۴ فایل موفق‌اند. schema و math عوض
نشده‌اند. [شاهد محدود محلی](../dependencies/pdf-app-owned-preparation-evidence.json)
hash کد/آزمون‌ها، شمارش JUnit و حدود عدم اثبات را ثبت می‌کند. این فایل، attestation
یا شاهد تازهٔ DLL/PDF/SPA در Windows نیست. آزمون هم‌زمانی این service از DB و موتور
واقعی استفاده نمی‌کند؛ throughput یا دو render بومیِ هم‌زمان ادعا نمی‌شود.

## باقی‌مانده و عدم تغییر نصب

مرحلهٔ فنی بعدی باید همین policy را پس از bootstrap خصوصی در Windows به factory
واقعی بدهد، **بدون جایگزین‌کردن renderer با FontAudit QA**، و bytes/font/cleanup،
auth/CSRF/SQLite/restart را دوباره بررسی کند. SDK و source21 باید همچنان شاهدهای
جدا داشته باشند؛ شاهد قدیمیِ سورس، proof این wiring تازه نیست.

هر شش گیت بازند. progress آماده‌سازی در policy و snapshot review **هم‌زمان** ثبت
شد؛ هیچ گیت، انتخاب حقوقی یا متن notice ضعیف/حذف نشد. MIT همان ۱۴ فایل native
build است و این service/app/QA را پوشش نمی‌دهد. نصب `D:\3D PRINT\VIRA-Accounting`،
launcher/Inno/updater معمول، staging، دادهٔ واقعی، نسخه، tag و release دست‌نخورده‌اند.
پیش‌فرض قلم عوض نشده و از کاربر نصب یا دادهٔ تست درخواست نمی‌شود.
