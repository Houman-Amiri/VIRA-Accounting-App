# به‌روزرسانی به ۱.۰.۹ فقط با بستهٔ تفاضلی

برای ارتقای نصب موجود نیازی به Setup کامل، حذف نصب یا حذف داده‌ها نیست.
مسیر نصب اعلام‌شدهٔ کاربر `D:\3D PRINT\VIRA-Accounting` است؛ آن را تغییر ندهید.

## انتخاب بسته

ابتدا نسخهٔ نصب‌شده را در «سیستم و عملیات» یا فایل `version.json` پوشهٔ نصب بخوانید.
از [انتشار رسمی ۱.۰.۹](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/tag/v1.0.9)
فقط **یکی** از بسته‌های زیر، مطابق نسخهٔ نصب‌شده، به‌همراه
[SHA256SUMS.txt](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.9/SHA256SUMS.txt)
دریافت شود:

| نسخهٔ نصب‌شده | بستهٔ مستقیم به ۱.۰.۹ |
| --- | --- |
| ۱.۰.۶ | [VIRA-v1.0.9-delta-from-v1.0.6.zip](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.9/VIRA-v1.0.9-delta-from-v1.0.6.zip) |
| ۱.۰.۷ | [VIRA-v1.0.9-delta-from-v1.0.7.zip](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.9/VIRA-v1.0.9-delta-from-v1.0.7.zip) |
| ۱.۰.۸ | [VIRA-v1.0.9-delta-from-v1.0.8.zip](https://github.com/Houman-Amiri/VIRA-Accounting-App/releases/download/v1.0.9/VIRA-v1.0.9-delta-from-v1.0.8.zip) |

در ۱.۰.۸ می‌توان مسیر «سیستم و عملیات ← بررسی به‌روزرسانی» را با تأیید کاربر
استفاده کرد. مسیر دستی زیر برای بوت‌استرپ updater قدیمی یا رفع مانع دانلود است؛
اثبات کامل ارتقای داخل برنامه روی دستگاه کاربر محسوب نمی‌شود.

## اعمال دستی با پشتیبان

ZIP را مستقیم روی پوشهٔ نصب استخراج نکنید؛ بسته شامل دستور اعمال وصله و حذف است.
برنامه و پنجرهٔ اجرای آن را کامل ببندید. فایل ZIP مناسب و `SHA256SUMS.txt` همان
انتشار را در Downloads بگذارید. سپس فرمان زیر را در PowerShell اجرا کنید.
فرمان نسخهٔ پایه را از نصب می‌خواند و فقط همان ZIP را می‌پذیرد.

اگر `SQLITE_DATABASE_PATH` سفارشی دارید، این فرمان را اجرا نکنید؛ ابتدا مسیر
پایگاه‌دادهٔ واقعی و پشتیبان آن باید بررسی شود. پشتیبان را تا تأیید نتیجه نگه دارید.

```powershell
$ErrorActionPreference = 'Stop'
if ($env:SQLITE_DATABASE_PATH) { throw 'Custom database path: stop and verify its backup path first.' }
$downloadDir = Join-Path $env:USERPROFILE 'Downloads'
$install = 'D:\3D PRINT\VIRA-Accounting'
$current = (Get-Content -LiteralPath (Join-Path $install 'version.json') -Raw | ConvertFrom-Json).version
if ($current -notin @('1.0.6', '1.0.7', '1.0.8')) { throw "Unsupported baseline: $current. Stop; do not select another delta." }
$name = "VIRA-v1.0.9-delta-from-v$current.zip"
$zip = Join-Path $downloadDir $name
$sums = Join-Path $downloadDir 'SHA256SUMS.txt'
$pattern = '^[a-fA-F0-9]{64}\s+\*?' + [regex]::Escape($name) + '$'
$lines = @(Get-Content -LiteralPath $sums | Where-Object { $_ -match $pattern })
if ($lines.Count -ne 1) { throw 'Checksum entry missing or ambiguous; use SHA256SUMS.txt from v1.0.9.' }
$expected = ($lines[0] -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'SHA-256 mismatch. Stop; do not extract or apply this ZIP.' }
$prefix = $install.TrimEnd('\') + '\'
$running = @(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
if ($running.Count) { throw 'VIRA is still running. Close its console and retry.' }

$data = Join-Path $env:LOCALAPPDATA 'VIRA\data'
if (-not (Test-Path -LiteralPath (Join-Path $data 'vira.sqlite3'))) { throw 'Expected SQLite database missing. Stop and verify its actual path.' }
$id = [Guid]::NewGuid().ToString('N')
$backup = Join-Path $env:LOCALAPPDATA ("VIRA\backups\before-1.0.9-" + $id)
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $data -Destination (Join-Path $backup 'data') -Recurse
Write-Host "Data backup: $backup"

$stage = Join-Path $env:LOCALAPPDATA ("VIRA\updates\manual-1.0.9-" + $id)
Expand-Archive -LiteralPath $zip -DestinationPath $stage
$log = Join-Path $stage 'update.log'
& (Join-Path $stage 'vira-updater.exe') -Stage $stage -Log $log -InstallDir $install
if ($LASTEXITCODE -ne 0) { throw "Updater failed. Keep the backup and send this log: $log" }
$after = (Get-Content -LiteralPath (Join-Path $install 'version.json') -Raw | ConvertFrom-Json).version
if ($after -ne '1.0.9') { throw "Expected 1.0.9, got $after. Keep the backup and send this log: $log" }
Write-Host "Installed version: $after; log: $log"
```

بعد از اعمال، launcher جدید migration افزایشی تنظیمات را همراه پشتیبان‌گیری اجرا
می‌کند. اگر برنامه باز نشد، پشتیبان را حفظ کنید و گزارش launcher و `update.log` را
بفرستید؛ صرف تغییر `version.json` به معنی موفقیت کامل راه‌اندازی نیست.

## تأیید نتیجه

- در «سیستم و عملیات» نسخهٔ **۱.۰.۹** و هم‌خوانی شناسهٔ ساخت نصب و مرورگر را بررسی کنید.
- بخش «تنظیمات ← ثابت‌های قیمت‌گذاری» باید هفت ثابت را نمایش دهد. پس از ذخیره،
  تازه‌سازی صفحه نباید مقدار را از بین ببرد.
- در گزارش قیمت‌گذاری، جمع تولید سبز، قیمت هر عدد آبی و قیمت نهایی قرمز است.
- با ثابت‌های اولیه و ورودی **۲۴۰ گرم، ۱۰ ساعت**: تعداد ۱، ساده **۲٬۷۶۰٬۷۴۸٫۵**
  و زنجیردار **۲٬۷۸۰٬۷۴۸٫۵** تومان؛ تعداد ۱۰، ساده **۲۹۱٬۱۹۴٫۸۵** و زنجیردار
  **۳۱۱٬۱۹۴٫۸۵** تومان. اگر ثابت‌ها را تغییر داده‌اید، این اعداد معیار آن تنظیمات
  نیستند؛ برای آزمون، مقادیر دلخواهتان را بدون ثبت و یادداشت قبلی بازنشانی نکنید.
- تصویر نسخه و نتیجهٔ تعداد ۱ و ۱۰ را برای تأیید فاز ۴ بفرستید.

در صورت خطا، بستهٔ پایهٔ دیگر را امتحان نکنید و داده‌ها، نصب یا پشتیبان را حذف نکنید.
