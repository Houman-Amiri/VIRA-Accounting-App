<#
.SYNOPSIS
  Package V.I.R.A release assets (Phase 6 §6; extended by Phase 8).

.DESCRIPTION
  Produces, into -OutDir:
    * vira-<version>-portable.zip  — backend source + built SPA + scripts + lockfiles
    * latest.json                  — version manifest for the in-app update check
    * SHA256SUMS.txt               — checksums of every asset
    * release-notes-fa.md          — Persian release notes (GitHub Release body)

  No Docker anywhere. Runs on Windows-native PowerShell (also pwsh on Linux CI).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,   # e.g. v0.2.0
    [string]$OutDir = "dist-release",
    [string]$Repo = "Houman-Amiri/VIRA-Accounting-App"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$OutDirPath = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $OutDirPath | Out-Null

# ---------------------------------------------------------------- staging ---
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("vira-stage-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    foreach ($dir in @("backend", "scripts")) {
        Copy-Item -Recurse -Force (Join-Path $root $dir) (Join-Path $stage $dir)
    }
    # Built SPA (frontend/dist) — required for the FastAPI static mount
    $dist = Join-Path $root "frontend/dist"
    if (-not (Test-Path $dist)) {
        throw "frontend/dist missing — run 'pnpm build' before packaging"
    }
    Copy-Item -Recurse -Force $dist (Join-Path $stage "frontend/dist")
    foreach ($file in @("pyproject.toml", "uv.lock", "README.md")) {
        Copy-Item -Force (Join-Path $root $file) (Join-Path $stage $file)
    }
    # Strip caches from the staging copy
    Get-ChildItem -Recurse -Directory $stage |
        Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules") } |
        Remove-Item -Recurse -Force

    $zipName = "vira-$Version-portable.zip"
    $zipPath = Join-Path $OutDirPath $zipName
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath
}
finally {
    Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
}

# ------------------------------------------------------ checksums + notes ---
$assets = Get-ChildItem $OutDirPath -File
$sums = foreach ($a in $assets) {
    $h = Get-FileHash -Algorithm SHA256 $a.FullName
    "{0}  {1}" -f $h.Hash.ToLower(), $a.Name
}
$sums | Set-Content -Encoding ascii (Join-Path $OutDirPath "SHA256SUMS.txt")

$publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$zipHash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()
@(
    "{",
    "  `"version`": `"$Version`",",
    "  `"published_at`": `"$publishedAt`",",
    "  `"channel`": `"stable`",",
    "  `"notes_fa`": `"نسخه $Version ویرا منتشر شد. برای جزئیات به صفحه انتشارات گیت‌هاب مراجعه کنید.`",",
    "  `"files`": [",
    "    { `"name`": `"$zipName`", `"sha256`": `"$zipHash`" }",
    "  ]",
    "}"
) | Set-Content -Encoding utf8 (Join-Path $OutDirPath "latest.json")

$notes = @"
## نسخه $Version

این نسخه به‌صورت خودکار از تگ annotated **$Version** ساخته شده است.

### فایل‌ها
- ``$zipName`` — بسته قابل حمل (بک‌اند + فرانت ساخته‌شده + اسکریپت‌ها)
- ``SHA256SUMS.txt`` — کد SHA256 فایل‌ها برای راستی‌آزمایی
- ``latest.json`` — manifest بررسی به‌روزرسانی درون برنامه

### به‌روزرسانی
از داخل برنامه، در بخش **«سیستم و عملیات»** (پس از احراز هویت مجدد) دکمه
**«بررسی به‌روزرسانی»** را بزنید. دانلود فقط بخش‌های تغییرکرده را دریافت می‌کند
و هیچ‌گاه داده‌های شما را از بین نمی‌برد.

### راستی‌آزمایی
``````
Get-FileHash -Algorithm SHA256 $zipName
``````
را با مقدار ثبت‌شده در ``SHA256SUMS.txt`` مقایسه کنید.
"@
$notes | Set-Content -Encoding utf8 (Join-Path $OutDirPath "release-notes-fa.md")

Write-Host "[vira-release] assets in $OutDirPath"
Get-ChildItem $OutDirPath | Format-Table Name, Length
