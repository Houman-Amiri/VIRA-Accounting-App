# دریافت اصلاح updater و قیمت‌گذاری: از ۱.۰.۶ به ۱.۰.۸، فقط با بستهٔ تفاضلی

این راهنما برای نصب تأییدشدهٔ **۱.۰.۶** در مسیر زیر است:

```text
D:\3D PRINT\VIRA-Accounting
```

این **مسیر دستیِ اعمال بستهٔ تفاضلی** است، نه تأیید عملکرد دکمهٔ به‌روزرسانی داخل
برنامه. تأیید کامل آن دکمه موضوع فاز ۸ است. برای این روش نیازی به دانلود Setup نیست.

## ۱) دریافت دو فایل کوچک‌تر از نصب کامل

فقط از [انتشار رسمی ۱.۰.۸](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/tag/v1.0.8):

- [بستهٔ تفاضلی از ۱.۰.۶](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.8/VIRA-v1.0.8-delta-from-v1.0.6.zip)
- [SHA256SUMS.txt](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.8/SHA256SUMS.txt)

بستهٔ تفاضلی منتشرشده **۴٬۴۸۱٬۹۲۷ بایت** است (حدود ۴٫۴۸ مگابایت).
SHA-256 نهایی:

```text
7a75ba8cb9b3688e040bb040434ab0dc4d341a1daeafa53b13cf0bb33698c307
```

این هش مربوط به ۱.۰.۸ از پایهٔ ۱.۰.۶ است، نه بستهٔ ۱.۰.۷ یا delta پایهٔ دیگر.

هر دو فایل را با همین نام‌ها در یک پوشه ذخیره کنید. از checksum نسخهٔ ۱.۰.۶ یا
بستهٔ تفاضلیِ مربوط به پایهٔ دیگری استفاده نکنید. فایل ZIP را مستقیم روی پوشهٔ
نصب استخراج نکنید؛ داخل ZIP هم فایلِ کامل و هم وصله و دستور حذف وجود دارد.

## ۲) بستن برنامه و اجرای فرمان

۱. پنجرهٔ اجرای برنامه (کنسول/پنجرهٔ سیاه)، مرورگر و تمام نمونه‌های VIRA را ببندید.
۲. PowerShell را باز کنید. فرمان زیر به‌صورت پیش‌فرض فایل‌ها را در پوشهٔ Downloads
   کاربر جست‌وجو می‌کند؛ اگر جای دیگری ذخیره کرده‌اید، فقط `$downloadDir` را عوض کنید.
۳. فرمان ابتدا هش فایل ZIP و نسخهٔ پایه را بررسی می‌کند؛ سپس از **کل پوشهٔ داده**
   یک کپی می‌گیرد، بسته را در پوشه‌ای جدا استخراج و ابزار کمکی همان بسته را اجرا می‌کند.
   اگر مسیر نصب واقعی شما فرق دارد، پیش از اجرا `$install` را اصلاح کنید.

```powershell
$ErrorActionPreference = 'Stop'
$downloadDir = Join-Path $env:USERPROFILE 'Downloads'
$install = 'D:\3D PRINT\VIRA-Accounting'
$name = 'VIRA-v1.0.8-delta-from-v1.0.6.zip'
$zip = Join-Path $downloadDir $name
$sums = Join-Path $downloadDir 'SHA256SUMS.txt'

# Verify the downloaded package BEFORE executing or extracting anything.
$pattern = '^[a-fA-F0-9]{64}\s+\*?' + [regex]::Escape($name) + '$'
$lines = @(Get-Content -LiteralPath $sums | Where-Object { $_ -match $pattern })
if ($lines.Count -ne 1) { throw 'Checksum entry missing or ambiguous; use SHA256SUMS.txt from v1.0.8.' }
$expected = ($lines[0] -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'SHA-256 mismatch. Stop; do not apply this ZIP.' }

$current = (Get-Content -LiteralPath (Join-Path $install 'version.json') -Raw | ConvertFrom-Json).version
if ($current -ne '1.0.6') { throw "This delta requires 1.0.6; installed version is $current." }
$prefix = $install.TrimEnd('\') + '\'
$running = @(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
if ($running.Count) { throw 'VIRA is still running. Close its console and retry before applying.' }

# Keep an independent data backup outside the installation.
$data = Join-Path $env:LOCALAPPDATA 'VIRA\data'
if (-not (Test-Path -LiteralPath $data)) { throw 'Expected data directory not found. Stop and check SQLITE_DATABASE_PATH.' }
$id = [Guid]::NewGuid().ToString('N')
$backup = Join-Path $env:LOCALAPPDATA ("VIRA\backups\before-1.0.8-" + $id)
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $data -Destination (Join-Path $backup 'data') -Recurse
Write-Host "Data backup: $backup"

$stage = Join-Path $env:LOCALAPPDATA ("VIRA\updates\manual-1.0.8-" + $id)
Expand-Archive -LiteralPath $zip -DestinationPath $stage
$log = Join-Path $stage 'update.log'
& (Join-Path $stage 'vira-updater.exe') -Stage $stage -Log $log -InstallDir $install
if ($LASTEXITCODE -ne 0) { throw "Updater failed. Keep the backup and send this log: $log" }
$after = (Get-Content -LiteralPath (Join-Path $install 'version.json') -Raw | ConvertFrom-Json).version
if ($after -ne '1.0.8') { throw "Version did not reach 1.0.8. Keep the backup and send this log: $log" }
Write-Host "Installed version: $after; log: $log"
```

اگر از `SQLITE_DATABASE_PATH` سفارشی استفاده می‌کنید، این فرمان را بدون اصلاح مسیر
پشتیبان اجرا نکنید؛ ابتدا از پایگاه‌دادهٔ واقعی در حالت بسته‌بودن برنامه پشتیبان بگیرید.
اگر دسترسی پوشهٔ نصب رد شد، عملیات را متوقف کنید و متن خطا را بفرستید؛ مسیر نصب را
عوض نکنید و پوشه‌های داده/پشتیبان را پاک نکنید.

## ۳) تأیید فاز ۴

پس از بازشدن برنامه، پنجرهٔ قدیمی مرورگر را ببندید و صفحه را تازه کنید:

- «سیستم و عملیات» باید نسخهٔ **۱.۰.۸** ، کامیت با ابتدای `76eadf2` و شناسه‌های ساخت نصب و مرورگر
  هم‌خوان `76eadf2` را نشان دهد.
- در قیمت‌گذاری، دکمهٔ **«مقادیر نمونهٔ اکسل»** را بزنید.
- تعداد ۱: ساده **۲٬۷۶۰٬۷۴۸٫۵** و زنجیردار **۲٬۷۸۰٬۷۴۸٫۵** تومان.
- فقط تعداد را ۱۰ کنید: ساده **۲۹۱٬۱۹۴٫۸۵** و زنجیردار **۳۱۱٬۱۹۴٫۸۵** تومان.
- نتیجه یا تصویر جدول را در گفتگو بفرستید؛ تا این تأیید فاز ۴ باز است.

**در صورت خطا:** دوباره و با بستهٔ پایهٔ دیگر تلاش نکنید. فایل `update.log` و متن
خطا را بفرستید (اطلاعات شخصی را در صورت وجود بپوشانید). نسخهٔ پشتیبان را نگه دارید.
