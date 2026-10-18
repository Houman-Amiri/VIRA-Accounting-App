# گزارش مرحلهٔ آماده‌سازی مجوزها، notices و تحویل سورس PDF

تاریخ: ۲۰۲۶-۱۰-۱۸ — ادامهٔ مأموریت پس از اثبات ساخت از سورس.

**نتیجهٔ این مرحله: مواد و انتخاب‌های قابل‌بازبینی آماده شدند؛ گیت حقوقی/توزیع
بسته نشده و موتور جدید به نصب معمول یا نصب فعلی شما اضافه نشده است.**

## کار واقعی انجام‌شده

- برای تمام **۲۰ بسته / ۲۱ DLL** انتخاب مجوز و دلیل آن در
  [policy](../dependencies/pdf-runtime-license-policy.json) ثبت شد. inventory اصلی
  با fingerprint، پین vcpkg و هش/اندازهٔ سورس به این انتخاب‌ها متصل است. اضافه‌شدن
  بسته، تغییر declaration، bytes copyright یا مبدأ، خطاست؛ نه تأیید خودکار.
- متن اصلی notices تمام بسته‌ها، حتی بسته‌های بدون DLL منتخب که ممکن است
  header/static relevance داشته باشند، محافظه‌کارانه حفظ شد؛ `pthread` فقط با
  اثبات alias خالی بودن به `pthreads` واگذار می‌شود.
- ممیزی دوبارهٔ **خود آرشیو واقعی** بدون کامپایل مجدد انجام شد: ۲۰ بسته، ۲۵٬۵۰۵
  ورودی و ۲۱ symlink؛ هش درخت‌های پچ‌شده و copyright/SPDX دوباره کنترل شدند.
- **۱۱ فایل مکمل** از همین درخت‌های تأییدشده استخراج شد. تمام ۱۹ قطعهٔ metadata
  بدون truncation بازیابی شدند. برنامه سقف ۸ notice در هر step / مجموع ۶۴ قطعه
  دارد؛ بیش از سقف، شکست صریح است نه سکوت.
- اطلاعیهٔ انگلیسی همراه ساخته شد: **۵۱۸٬۸۹۵ بایت**، SHA256:
  `2236949291e0f88c6625646cd85464258b8677d7b3fcb6ead9eae0cc21083ca7`.
  این فایل متن‌های جایگزین اصلی و بعضی فایل‌های سورسِ حاوی notice را کامل حفظ
  می‌کند؛ وجود متن GPL جایگزین در آن، انتخاب GPL برای کل برنامه نیست.
  قاعدهٔ محدود `.gitattributes`، bytes این فایلِ دارای CRLF اصلی را هنگام add/
  checkout حفظ می‌کند؛ تبدیل پایان‌خط نباید هش اعلام‌شده را بی‌صدا عوض کند.
- یک کپی داخلیِ source ZIP و مواد review با نگهداری **۹۰روزه** ساخته شد. این گام
  ماندگاریِ بررسی داخلی را بهتر می‌کند، اما source delivery عمومی/دائمی نیست.

## نقص‌هایی که این مرحله آشکار کرد

### PCRE2: declaration به‌تنهایی کافی نبود

copyright ثبت‌شدهٔ vcpkg فقط **۹۷ بایت** و یک forwarding stub بود؛ متن مجوز در
آن وجود نداشت. از سورس واقعی PCRE2 10.49، `LICENCE.md` با **۴٬۰۱۱ بایت** و متن
جداگانهٔ SLJIT با **۱٬۴۴۴ بایت** استخراج و همراه notices ثبت شد.

انتخاب پیشنهادی اکنون `(BSD-3-Clause WITH PCRE2-exception) AND BSD-2-Clause`
است؛ declaration تاریخی `BSD-3-Clause` در inventory دستکاری نشده است. recipe
پین‌شدهٔ vcpkg از SLJIT commit
`45f910b78c6605ebf5b53d3ec7cb00f2312fe417` استفاده می‌کند، نه صرفاً submodule
اشاره‌شده در tag خود PCRE2. بنابراین متن‌ها از آرشیو build گرفته شدند، نه از
یک submodule دلخواه روی وب. به binary exception برای حذف notices اتکا نشده است.

### FreeType: صرف FTL کافی برای تمام notices جانبی نیست

گزینهٔ پیشنهادی **FTL** است، نه GPL. attribution زیر در مواد تولیدشده آمده است:

> Portions of this software are copyright © 1996-2026 The FreeType Project
> (https://freetype.org). All rights reserved.

۹ مکمل از BDF/PCF، دو فایل hash، zlib داخلی و چهار فایل برگرفته از HarfBuzz
ثبت شدند؛ copyright/شرایط MIT-like و Zlib این بخش‌ها هم حذف نشده‌اند. وجود zlib
داخلی FreeType با بستهٔ مستقل zlib یکی فرض نشده است.

### libiconv: null در SPDX مجوز نیست

declaration این port همچنان null است. متن اصلی copyright به‌صراحت کتابخانه‌ها و
headerهای libiconv/libcharset را زیر LGPL و CLI/docs را زیر GPL قرار می‌دهد.
انتخاب پیشنهادی در policy برای **کتابخانه‌ها** LGPL 2.1-or-later و مبنای اجرایی
بررسی، نسخهٔ ۲٫۱ است. این انتخاب به معنای مجوز دادن به CLI تحت LGPL یا GPL کردن
VIRA نیست؛ هر دو متن اصلی حفظ شده‌اند و بررسی محدودهٔ اجزا هنوز لازم است.

### Windows: خطای locale واقعاً گرفته و اصلاح شد

اجرای اول CI عادی `39102503373` چهار job موفق داشت، ولی تست بومی ویندوز در hash
copyright بستهٔ Fontconfig شکست خورد. علت واقعی استفاده از `read_text()` بدون
encoding بود: ویندوز با codepage قدیمی، `©` و نام مؤلف را خراب می‌خواند. چک hash
**تضعیف نشد**؛ تمام ورودی‌های JSON این ابزار UTF-8 صریح و خروجی JSON با LF ثابت
شدند. regression جدید همین قرارداد را حتی خارج از ویندوز نیز تحمیل می‌کند.

## انتخاب‌های مهم دیگر

| بسته | انتخاب پیشنهادی / دامنه |
|---|---|
| Cairo | LGPL-2.1-only به‌جای MPL-1.1؛ notices با وجود نداشتن DLL منتخب حفظ شده |
| GLib | شاخهٔ LGPL برای جزء LGPL/MPL؛ مبنای compliance برابر ۲٫۱ |
| Pango | استفاده از اجازهٔ or-later برای نسخهٔ LGPL 2.1 |
| FriBidi | LGPL و Unicode-3.0 با هم حفظ شده‌اند |
| HarfBuzz / Pixman / Expat | عبارات مرکب AND، نه انتخاب یکی و حذف دیگری |
| pthreads | Apache-2.0؛ alias خالی pthread فقط به همین بسته واگذار می‌شود |

policy کامل شامل هر ۲۰ بسته است. این انتخاب‌ها **پیشنهاد مهندسی قابل‌بازبینی**
هستند؛ نه نظر نهایی حقوقی، نه تغییر مجوز upstream و نه مجوز جدید برای کد VIRA.

## فایل‌ها و بازتولید

- [متن همراه کامل](../dependencies/pdf-runtime-THIRD-PARTY-NOTICES.txt)
- [مواد مکمل از سورس و هش هر فایل](../dependencies/pdf-runtime-license-materials.json)
- [انتخاب‌ها و گیت‌های اجباری](../dependencies/pdf-runtime-license-policy.json)
- [نتیجهٔ ماشین‌خوان](../dependencies/pdf-runtime-license-review.json)
- [جزئیات اجرای اثبات](../dependencies/pdf-runtime-license-proof-run.json)
- [قرارداد پیشنهادی تحویل سورس](../dependencies/pdf-runtime-source-delivery-plan-fa.md)
- ابزار `scripts/pdf_runtime_licenses.py` و workflow `pdf-license-proof.yml`.

بازتولید متن‌ها از مواد ثبت‌شده، فقط با کتابخانهٔ استاندارد Python:

```bash
python scripts/pdf_runtime_licenses.py
```

این دستور **replay** است، نه ممیزی مجدد آرشیو یا تأیید حقوقی. برای collection
جدید، `--archive <corresponding-source.zip>` لازم است؛ در این مسیر verifier اصلی
درخت‌ها و بایت‌ها را دوباره بررسی می‌کند. workflow فقط اجرای source موفقِ از پیش
پین‌شده را می‌پذیرد. SHA256 آرشیو اصلی بدون تغییر:
`259532d2cd8c5d3b176402acdcfb9daadb2cb897d5710010cc198eeabe5401de`.

## نتیجهٔ آزمون‌ها

- ۲۵ تست جدید برای انتخاب‌ها، coverage، bytes، stub ناقص، مبدأ مکمل، alias،
  حفظ گیت‌ها، fingerprint، UTF-8 در locale قدیمی، بازتولید و سقف metadata.
- همراه ۸ تست verifier پیشین: **۳۳ تست متمرکز موفق**.
- مجموعهٔ کامل بک‌اند پس از اصلاح: **۴۳۸ تست موفق (۶۲٫۴۴ ثانیه)**.
- Ruff و Mypy روی ۸۴ فایل app موفق؛ Bandit با threshold رسمی پروژه (`-ll`) روی
  app و بدون کاهش threshold روی ابزار جدید موفق است.
- CI عادی نهایی، شامل تست بومی ویندوز، فرانت‌اند، مرورگر و migration/rollback:
  **هر پنج job در [39102792071](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39102792071)
  روی `40addf7` موفق شدند**؛ شامل ۱۹۶ تست فرانت‌اند و شش سناریوی مرورگر، PDF
  واقعی/worker خصوصی و مهاجرت/rollback پایگاه‌داده از نسخهٔ عمومی ۱٫۰٫۱۰.
  شکست اولیه پنهان یا skip نشده است.
- ممیزی مواد سورس/مجوز در
  [39102792100](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39102792100)
  روی همان `40addf7` موفق شد؛ ۱۱ مکمل و تمام ۱۹ قطعه با اجرای پیشین یکسان بودند.
- [artifact بررسی داخلی](https://github.com/Houman-Amiri/VIRA-Accounting-App/actions/runs/39102792100/artifacts/12126649884):
  `private-native-license-review-and-source`، ۱۷۷٬۸۰۲٬۵۷۳ بایت، انقضا
  `2027-01-16T06:05:13Z`؛ digest و ارتباط با source-build اصلی در فایل proof ثبت است.
  این artifact شامل سورس/متن است، نه DLL/بستهٔ نصب جدید.

## مرز پایان این مرحله و گام بعد

وضعیت همچنان `BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW` است.
شش گیت اجباری در policy ثبت شده‌اند و ابزار اجازهٔ حذف آن‌ها یا اعلام APPROVED
نمی‌دهد: بازبینی حقوقی اجزا؛ شرایط compiler/CRT؛ حقوق/کامل‌بودن recipeهای VIRA؛
تحویل سورس قابل‌استفاده برای دریافت‌کننده؛ جایگزینی سازگار DLL و شرایط LGPL؛ و
bootstrap/update/rollback و پذیرش نصب‌شده.

در بررسی کامل‌بودن recipe نیز مشخص شد آرشیو فعلی برای اجرای مستقل **کل** wrapperها
کافی نیست: import فایل `pdf_runtime_inventory.py` و فراخوانی
`pdf_payload_smoke.ps1` در آن ثبت شده، اما خود این فایل‌ها در ضمیمهٔ wrapper آن
وجود ندارند. سورس کامل کتابخانه‌ها ثبت شده است؛ ادعای SDK آفلاین یا workflow
خودبسنده نمی‌کنیم. ضمیمهٔ قابل اجرا و اجازهٔ بازتوزیع/تغییر آن باید تکمیل شود.

**هیچ runtime بومی، نسخه، تگ یا Release تازه‌ای منتشر نشد؛ setup/delta عادی تغییر
نکرد؛ داده، محاسبات مالی و نصب فعلی کاربر دست نخورده‌اند.** آزمون دستی کسب‌وکار
طبق درخواست قبلی به بعد موکول است، نه اینکه تأیید‌شده فرض شود.


## پیگیری تأیید مالک برای اسکریپت‌های ساخت

پس از این گزارش، مالک MIT را **فقط برای ابزار/تنظیمات ساخت PDF** تأیید کرد.
[گزارش اعمال محدود و دامنهٔ دقیق](pdf-build-script-license-grant-fa.md) ثبت است؛
متن‌های «مجوز مالک هنوز تعیین نشده» در این گزارش مربوط به وضعیت پیش از همان
تأیید هستند. انتخاب‌های upstream و آرشیو سورس قبلی تغییر نکردند؛ اجازهٔ کل
برنامه یا انتشار runtime از این پاسخ استنباط نشده است. گیت کامل‌بودن recipe
همچنان باز است؛ تأیید حقوقِ فایل‌های مشخص با اثبات workflow خودبسنده یکی نیست.
