# Private application QA only, outside the native-build MIT grant. No installer/release.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Candidate)
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true") { throw "Isolated Windows CI only" }
$repo = (Get-Location).Path
$root = Join-Path $env:RUNNER_TEMP ("vira-unicode-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $root | Out-Null
$staged = Join-Path $root "initial-stage"
& ./scripts/stage_app_payload.ps1 -Version "0.0.0-private-unicode-proof" -OutDir $staged
$app = Join-Path $root "VIRA چاپ & مسیر با فاصله"
Move-Item $staged $app
$native = Join-Path $app "native/pdf"
$inventory = Get-Content (Join-Path $Candidate "runtime-inventory.json") -Raw | ConvertFrom-Json
if ($inventory.origin -ne "LOCAL_PINNED_VCPKG_SOURCE_BUILD" -or $inventory.private_consumption_only -ne $true -or $inventory.modified_build_is_distribution_candidate -ne $false) { throw "fresh private source candidate required" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $native) | Out-Null
Copy-Item -Recurse $Candidate $native
$contexts = Join-Path $root "contexts.json"
@'
import json,runpy
f=runpy.run_path('scripts/pdf_native_smoke.py')['fixture_context']
print(json.dumps({'single-page':f(1),'multi-page':f(100)}))
'@ | uv run python - | Set-Content -Encoding utf8 $contexts
if ($LASTEXITCODE -ne 0) { throw "synthetic contexts failed" }
# Fonts are read-only files. This is NOT a Windows ACL/read-only installation proof.
Get-ChildItem (Join-Path $app "app/assets/fonts") -File -Filter *.ttf | ForEach-Object { $_.IsReadOnly = $true }
$profile = Join-Path $root "کاربر فارسی & Local AppData"
$state = Join-Path $profile "VIRA/تنظیم قلم"
$cwd = Join-Path $profile "محل اجرای جدا"
New-Item -ItemType Directory -Force -Path $cwd | Out-Null
$previous = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $profile
    foreach ($case in @("first-process", "restarted-process")) {
        $reports = Join-Path $repo "reports/unicode-pdf/$case"
        New-Item -ItemType Directory -Force -Path $reports | Out-Null
        Copy-Item (Join-Path $native "runtime-inventory.json") (Join-Path $reports "runtime-inventory.json")
        $probeArgs = @()
        if ($case -eq "restarted-process") { $probeArgs += "--reuse-state" }
        Push-Location -LiteralPath $cwd
        try {
            & (Join-Path $app "python/python.exe") -I -B (Join-Path $app "scripts/pdf_unicode_probe.py") --app-root $app --contexts $contexts --state-root $state --out-dir $reports --expected-pango-version "1.58.0-vira-local-source" @probeArgs
            if ($LASTEXITCODE -ne 0) { throw "Unicode worker failed: $case" }
        } finally { Pop-Location }
        uv run python scripts/pdf_payload_verify.py --app-root $app --reports $reports
        if ($LASTEXITCODE -ne 0) { throw "real Unicode PDF/manifest verification failed: $case" }
    }
} finally { $env:LOCALAPPDATA = $previous }
Write-Host "PASS: private Unicode memory Fontconfig, TEMP, app/profile, restart and real PDFs; NOT installed/production/legal acceptance"
