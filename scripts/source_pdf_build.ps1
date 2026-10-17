# Source-built private candidate only. Never call from release/stage workflows.
$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true") { throw "isolated GitHub Actions runner required" }
$repo = (Get-Location).Path
$profile = Join-Path $repo "native/pdf-source"
$pin = (Get-Content (Join-Path $profile "vcpkg.json") -Raw | ConvertFrom-Json).'builtin-baseline'
if ($pin -notmatch '^[a-f0-9]{40}$') { throw "immutable vcpkg commit required" }
$work = Join-Path $env:RUNNER_TEMP "vira-native-source"
$vcpkg = Join-Path $work "vcpkg"
New-Item -ItemType Directory -Force -Path $work | Out-Null
& git clone --no-checkout https://github.com/microsoft/vcpkg.git $vcpkg
if ($LASTEXITCODE -ne 0) { throw "vcpkg clone failed" }
& git -C $vcpkg checkout --detach $pin
if ($LASTEXITCODE -ne 0) { throw "vcpkg immutable checkout failed" }
if ((& git -C $vcpkg rev-parse HEAD) -ne $pin) { throw "vcpkg pin mismatch" }
& (Join-Path $vcpkg "bootstrap-vcpkg.bat") -disableMetrics
if ($LASTEXITCODE -ne 0) { throw "vcpkg bootstrap failed" }
$env:VCPKG_BINARY_SOURCES = "clear"
$env:VCPKG_MAX_CONCURRENCY = "2"
$installed = Join-Path $work "installed"
$reports = Join-Path $repo "reports/source-pdf"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
& (Join-Path $vcpkg "vcpkg.exe") version | Set-Content (Join-Path $reports "vcpkg-version.txt")
& git -C $vcpkg status --porcelain | Set-Content (Join-Path $reports "vcpkg-status-before.txt")
# Clear every binary-cache source: target AND host ports must build here.
# Downloaded, hash-verified compiler/build tools are not claimed to be source-built.
& (Join-Path $vcpkg "vcpkg.exe") install --triplet x64-vira-pdf --host-triplet x64-windows "--x-manifest-root=$profile" "--x-install-root=$installed" "--overlay-triplets=$profile/triplets" --binarysource=clear --no-print-usage 2>&1 | Tee-Object (Join-Path $reports "build.log")
if ($LASTEXITCODE -ne 0) { throw "controlled native source build failed; see build.log" }
$candidate = Join-Path $work "candidate"
uv run python scripts/source_pdf_inventory.py --vcpkg-root $vcpkg --installed $installed --out-dir $candidate --reports $reports
if ($LASTEXITCODE -ne 0) { throw "source/copyright/PE provenance gate failed" }
$env:VIRA_PDF_SOURCE_CANDIDATE = $candidate
& ./scripts/pdf_payload_smoke.ps1
if ($LASTEXITCODE -ne 0) { throw "source-built native/staged Python proof failed" }
Write-Host "PASS: pinned-source private proof, NOT publication or legal approval"
