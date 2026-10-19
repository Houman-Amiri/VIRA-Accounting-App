# Private stock-SDK or audit-bound source HTTP pre-import launcher QA; NOT ordinary startup or MIT build recipe.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Candidate, [switch]$HttpProof, [string]$SourceAudit, [switch]$AppOwnedFonts)
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true") { throw "Private Windows CI only" }
if ($AppOwnedFonts -and -not $HttpProof) { throw "App-owned mode requires HTTP proof" }
$repo = (Get-Location).Path
if ($SourceAudit -and -not $HttpProof) { throw "Source audit requires explicit HTTP QA" }
$sourceHash = if ($SourceAudit) { (Get-FileHash -Algorithm SHA256 $SourceAudit).Hash.ToLowerInvariant() } else { "" }
$root = Join-Path $env:RUNNER_TEMP ("vira-launcher-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $root | Out-Null
$staged = Join-Path $root "initial-stage"
& ./scripts/stage_app_payload.ps1 -Version "0.0.0-private-unicode-proof" -OutDir $staged
$app = Join-Path $root "VIRA راه‌انداز & مسیر با فاصله"
Move-Item $staged $app
$native = Join-Path $app "native/pdf"
New-Item -ItemType Directory -Force (Split-Path -Parent $native) | Out-Null
$inventoryHash = (Get-FileHash -Algorithm SHA256 (Join-Path $Candidate "runtime-inventory.json")).Hash.ToLowerInvariant()
Copy-Item -Recurse $Candidate $native
if ($SourceAudit) { Copy-Item $SourceAudit (Join-Path $native "source-audit.json") }
& ./scripts/pdf_unicode_process_manifest.ps1 -AppRoot $app
$baselineHash = (Get-FileHash -Algorithm SHA256 (Join-Path $app "install_manifest.json")).Hash.ToLowerInvariant()
$contexts = Join-Path $root "contexts.json"
@'
import json,runpy
f=runpy.run_path('scripts/pdf_native_smoke.py')['fixture_context']
print(json.dumps({'single-page':f(1),'multi-page':f(100)}))
'@ | uv run python - | Set-Content -Encoding utf8 $contexts
if ($LASTEXITCODE -ne 0) { throw "Synthetic contexts failed" }
$profile = Join-Path $root "کاربر فارسی & Local AppData"
$state = Join-Path $profile "VIRA/تنظیم قلم"
$cwd = Join-Path $profile "محل اجرای جدا"
New-Item -ItemType Directory -Force $cwd | Out-Null
Get-ChildItem (Join-Path $app "app/assets/fonts") -Filter *.ttf -File | ForEach-Object { $_.IsReadOnly = $true }
$python = Join-Path $app "python/python.exe"
$entry = Join-Path $app "scripts/pdf_private_launcher.py"
$previous = $env:LOCALAPPDATA
$previousPassword = $env:VIRA_PRIVATE_HTTP_PASSWORD
$reportName = if ($SourceAudit) { "source-http" } elseif ($HttpProof) { "private-http" } else { "private-launcher" }
if ($AppOwnedFonts) { $reportName = if ($SourceAudit) { "source-owned-http" } else { "app-owned-http" } }
$reports = Join-Path $repo "reports/$reportName"
New-Item -ItemType Directory -Force $reports | Out-Null
try {
    $env:LOCALAPPDATA = $profile
    if ($HttpProof) { $env:VIRA_PRIVATE_HTTP_PASSWORD = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N") }
    Push-Location -LiteralPath $cwd
    try {
        $common = @("--app-root", $app, "--contexts", $contexts, "--state-root", $state,
                    "--inventory-sha256", $inventoryHash, "--payload-manifest-sha256", $baselineHash)
        if ($HttpProof) { $common += "--http-proof" }
        if ($AppOwnedFonts) { $common += "--app-owned-fonts" }
        if ($SourceAudit) { $common += @("--source-audit-sha256", $sourceHash) }
        $negativeArgs = $common + @("--out-dir", (Join-Path $reports "rejected"))
        $negative = @{}
        foreach ($case in @("missing-no-site", "early-ctypes", "wrong-inventory-digest")) {
            if ($case -eq "missing-no-site") {
                $output = (& $python -I -B -X utf8 $entry @negativeArgs 2>&1 | Out-String)
                $expected = "requires -I -S -B -X utf8"
            } elseif ($case -eq "early-ctypes") {
                $output = (& $python -I -S -B -X utf8 -c "import ctypes,runpy,sys;entry=sys.argv.pop(1);runpy.run_path(entry,run_name='__main__')" $entry @negativeArgs 2>&1 | Out-String)
                $expected = "Sensitive module imported before private bootstrap"
            } else {
                $badArgs = $negativeArgs + @("--inventory-sha256", ('0' * 64))
                $output = (& $python -I -S -B -X utf8 $entry @badArgs 2>&1 | Out-String)
                $expected = "Independent digest mismatch"
            }
            $code = $LASTEXITCODE
            $output | Set-Content -Encoding utf8 (Join-Path $reports "$case.log")
            if ($code -eq 0 -or -not $output.Contains($expected)) { throw "Negative control did not fail as expected: $case" }
            if (Test-Path (Join-Path $reports "rejected/launcher-proof.json")) { throw "Rejected launch wrote success proof" }
            $negative[$case] = @{ exit_code = $code; expected_error = $expected; rejected = $true }
        }
        $negative | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $reports "negative-controls.json")
        foreach ($case in @("first-process", "restarted-process")) {
            $out = Join-Path $reports $case
            $probeArgs = $common + @("--out-dir", $out)
            if ($case -eq "restarted-process") { $probeArgs += "--reuse-state" }
            & $python -I -S -B -X utf8 $entry @probeArgs
            if ($LASTEXITCODE -ne 0) { throw "Private launcher failed: $case" }
            Copy-Item (Join-Path $native "runtime-inventory.json") (Join-Path $out "runtime-inventory.json")
            $verifier = if ($HttpProof) { "scripts/pdf_http_verify.py" } else { "scripts/pdf_payload_verify.py" }
            $verifyArgs = @()
            if ($AppOwnedFonts) { $verifyArgs += "--app-owned-fonts" }
            if ($SourceAudit) { $verifyArgs += @("--source-audit-sha256", $sourceHash) }
            & uv run --project $repo python (Join-Path $repo $verifier) --app-root $app --reports $out @verifyArgs
            if ($LASTEXITCODE -ne 0) { throw "PDF/font/baseline verification failed: $case" }
        }
    } finally { Pop-Location }
} finally { $env:LOCALAPPDATA = $previous; $env:VIRA_PRIVATE_HTTP_PASSWORD = $previousPassword }
Write-Host "PASS: private isolated/no-site launch and explicit HTTP QA; build provenance requires the separate audit binder; NOT installed/production/legal acceptance"
