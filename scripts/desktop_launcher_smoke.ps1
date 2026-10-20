# Private Phase 2: external process/HTTP client; SAME actual installed CMD entry.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Candidate,
      [string]$SourceAudit, [switch]$PreflightOnly)
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true") { throw "Private Windows CI only" }
if (-not $SourceAudit -and -not $PreflightOnly) { throw "Independent source audit required" }
$repo = (Get-Location).Path
$root = Join-Path $env:RUNNER_TEMP ("vira-desktop-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $root | Out-Null
if ($PreflightOnly) {
    $SourceAudit = Join-Path $root "dummy-preflight-only-not-source-audit.json"
    [IO.File]::WriteAllBytes($SourceAudit, [Text.Encoding]::UTF8.GetBytes("{}"))
}
$staged = Join-Path $root "initial-stage"
& ./scripts/stage_app_payload.ps1 -Version "0.0.0-private-unicode-proof" -OutDir $staged
$app = Join-Path $root "VIRA راه‌انداز ! & مسیر با فاصله"
Move-Item $staged $app
$native = Join-Path $app "native/pdf"
New-Item -ItemType Directory -Force (Split-Path -Parent $native) | Out-Null
$inventoryHash = (Get-FileHash -Algorithm SHA256 (Join-Path $Candidate "runtime-inventory.json")).Hash.ToLowerInvariant()
Copy-Item -Recurse $Candidate $native
Copy-Item $SourceAudit (Join-Path $native "source-audit.json")
& ./scripts/pdf_unicode_process_manifest.ps1 -AppRoot $app
$baselineHash = (Get-FileHash -Algorithm SHA256 (Join-Path $app "install_manifest.json")).Hash.ToLowerInvariant()
$profile = Join-Path $root "کاربر فارسی ! & Local AppData"
$state = Join-Path $profile "VIRA/داده خصوصی راه‌انداز"
$cwd = Join-Path $profile "محل اجرای جدا"
New-Item -ItemType Directory -Force $cwd | Out-Null
Get-ChildItem (Join-Path $app "app/assets/fonts") -Filter *.ttf -File | ForEach-Object { $_.IsReadOnly = $true }
$previous = $env:LOCALAPPDATA
$reports = Join-Path $repo $(if ($PreflightOnly) { "reports/desktop-path-preflight" } else { "reports/desktop-source" })
$mode = @()
if ($PreflightOnly) { $mode += "--preflight-only" }
New-Item -ItemType Directory -Force $reports | Out-Null
try {
    $env:LOCALAPPDATA = $profile
    Push-Location -LiteralPath $cwd
    try {
        & uv run --project $repo python (Join-Path $repo "scripts/desktop_launcher_probe.py") --app-root $app --state-root $state --reports $reports --audit $SourceAudit --manifest-sha256 $baselineHash --inventory-sha256 $inventoryHash @mode
        if ($LASTEXITCODE -ne 0) { throw "Real start_vira.cmd source candidate failed" }
    } finally { Pop-Location }
} finally { $env:LOCALAPPDATA = $previous }
if ($PreflightOnly) { Write-Host "PASS: real CMD path/early rejection ONLY; NOT native activation" }
else { Write-Host "PASS: REAL CMD private source candidate; NOT ordinary-default/installed-user/release acceptance" }
