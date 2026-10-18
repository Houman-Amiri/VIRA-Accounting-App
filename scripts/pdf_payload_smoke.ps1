# Private technical proof only: native DLL licenses/sources are not approved.
# Never upload this candidate directory or pass it to the release workflow.
$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true") { throw "isolated GitHub Actions runner required" }
$root = Join-Path $env:RUNNER_TEMP ("vira-bundled-pdf-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $root | Out-Null
$staged = Join-Path $root "initial-stage"
& ./scripts/stage_app_payload.ps1 -Version "0.0.0-private-pdf-proof" -OutDir $staged
# Relocation must not retain the interpreter's original build/venv prefix.
$app = Join-Path $root "VIRA چاپ بومی"
Move-Item $staged $app
$native = Join-Path $app "native/pdf"
if ($env:VIRA_PDF_SOURCE_CANDIDATE) {
    $sourceInventory = Get-Content (Join-Path $env:VIRA_PDF_SOURCE_CANDIDATE "runtime-inventory.json") -Raw | ConvertFrom-Json
    if ($sourceInventory.origin -ne "LOCAL_PINNED_VCPKG_SOURCE_BUILD" -or $sourceInventory.distribution_status -ne "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW") { throw "invalid private source candidate" }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $native) | Out-Null
    Copy-Item -Recurse $env:VIRA_PDF_SOURCE_CANDIDATE $native
} else {
    uv run python scripts/pdf_runtime_inventory.py --archive "$env:VIRA_PDF_UPSTREAM_ARCHIVE" --out-dir $native
    if ($LASTEXITCODE -ne 0) { throw "native closure inventory failed" }
}

$contexts = Join-Path $root "contexts.json"
$code = @'
import json, runpy
fixture = runpy.run_path('scripts/pdf_native_smoke.py')['fixture_context']
print(json.dumps({'single-page': fixture(1), 'multi-page': fixture(100)}))
'@
$out = $code | uv run python -
if ($LASTEXITCODE -ne 0) { throw "synthetic contexts failed" }
$out | Set-Content -Encoding utf8 $contexts
$empty = Join-Path $root "empty-fonts"
$cache = Join-Path $root "font-cache"
New-Item -ItemType Directory -Path $empty, $cache | Out-Null
$escapedEmpty = [System.Security.SecurityElement]::Escape($empty.Replace('\', '/'))
$escapedCache = [System.Security.SecurityElement]::Escape($cache.Replace('\', '/'))
"<fontconfig><dir>$escapedEmpty</dir><cachedir>$escapedCache</cachedir></fontconfig>" | Set-Content -Encoding utf8 (Join-Path $root "fonts.conf")
$reports = Join-Path (Get-Location) "reports/bundled-pdf"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
Copy-Item (Join-Path $native "runtime-inventory.json") (Join-Path $reports "runtime-inventory.json")
$probeArgs = @()
if ($env:VIRA_PDF_EXPECT_PANGO_VERSION) { $probeArgs += @("--expected-pango-version", $env:VIRA_PDF_EXPECT_PANGO_VERSION) }
& (Join-Path $app "python/python.exe") -I (Join-Path $app "scripts/pdf_payload_probe.py") --app-root $app --contexts $contexts --fontconfig-file (Join-Path $root "fonts.conf") --out-dir $reports @probeArgs
if ($LASTEXITCODE -ne 0) { throw "bundled production interpreter PDF render failed" }
# PDF inspection lives in dev, not in the staged interpreter/site-packages.
uv run python scripts/pdf_payload_verify.py --app-root $app --reports $reports
if ($LASTEXITCODE -ne 0) { throw "bundled PDF embedding/isolation/manifest proof failed" }
Write-Host "PASS: private relocated production CPython payload + curated native closure, NOT distribution approval"
