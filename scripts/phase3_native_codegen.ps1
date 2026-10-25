# External QA orchestration only; does not extend the 14-file native MIT grant.
# Build TWO remains native-only: isolated copy of the authenticated recipe, fresh
# work tree, no binary caches, same twenty pinned preferred-source trees.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BaselineAudit)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Private disposable Windows CI only' }
$recipe = Join-Path $env:RUNNER_TEMP 'build-recipe'
$variant = Join-Path $env:RUNNER_TEMP 'phase3-codegen-recipe'
$work = Join-Path $env:RUNNER_TEMP 'phase3-codegen-native-work'
$overlay = Join-Path $env:RUNNER_TEMP 'local-overlay'
$reports = Join-Path $PWD 'reports/phase3-codegen'
if ((Test-Path -LiteralPath $variant) -or (Test-Path -LiteralPath $work)) { throw 'Fresh independent target required' }
New-Item -ItemType Directory -Force $reports | Out-Null
Copy-Item -LiteralPath $recipe -Destination $variant -Recurse
$triplet = Join-Path $variant 'native/pdf-source/triplets/x64-vira-pdf.cmake'
$before = (Get-FileHash -LiteralPath $triplet).Hash.ToLowerInvariant()
# Change real MSVC code generation, not source semantics or version markers.
# The original authenticated archive and its fourteen files remain untouched.
Add-Content -LiteralPath $triplet -Encoding utf8 -Value @'

# Private Phase3 compiler-codegen variant, NOT a published distribution recipe.
set(VCPKG_C_FLAGS_RELEASE "/Od /Ob0 /DNDEBUG")
set(VCPKG_CXX_FLAGS_RELEASE "/Od /Ob0 /DNDEBUG")
'@
Copy-Item -LiteralPath $triplet -Destination (Join-Path $reports 'target-triplet.cmake')
[IO.File]::WriteAllText((Join-Path $reports 'original-triplet-sha256.txt'),$before)
& pwsh -NoProfile -File (Join-Path $variant 'scripts/rebuild_pdf_native.ps1') -WorkDir $work -OverlayPorts $overlay
if ($LASTEXITCODE -ne 0) { throw 'Independent target cold native compilation failed' }
$python = Join-Path $env:RUNNER_TEMP 'native-inspector/Scripts/python.exe'
$fresh = Join-Path $reports 'fresh-native-audit.json'
& $python -B (Join-Path $variant 'scripts/audit_pdf_native_rebuild.py') --sidecar $variant --work $work --reference (Join-Path $overlay 'local-source-reference.json') --out $fresh
if ($LASTEXITCODE -ne 0) { throw 'Independent target twenty trees/PE closure/origins audit failed' }
& $python -I -S (Join-Path $recipe 'scripts/prepare_pdf_local_sources.py') --check-inputs (Join-Path $overlay 'local-source-preparation.json')
if ($LASTEXITCODE -ne 0) { throw 'Preferred input trees changed during independent target compilation' }
# Save complete generated compiler instructions, not a projection of flags.
$instructions = @(Get-ChildItem -LiteralPath (Join-Path $work 'vcpkg/buildtrees/pango') -Filter build.ninja -Recurse -File)
foreach ($file in $instructions) {
    $name = [IO.Path]::GetRelativePath($work,$file.FullName)
    $destination = Join-Path (Join-Path $reports 'compiler-instructions') $name
    New-Item -ItemType Directory -Force (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination
}
$out = Join-Path $reports 'verified-codegen-target.json'
uv run python scripts/phase3_native_codegen.py --baseline-audit $BaselineAudit --fresh-audit $fresh --work $work --recipe $triplet --out $out
if ($LASTEXITCODE -ne 0) { throw 'Target executable code/compiler instructions/executed Pango proof failed' }
uv run python scripts/prepare_pdf_consumer_candidate.py --work $work --reference (Join-Path $overlay 'local-source-reference.json') --native-proof $out --out (Join-Path $env:RUNNER_TEMP 'phase3-codegen-candidate')
if ($LASTEXITCODE -ne 0) { throw 'Independently audited target candidate assembly failed' }
# No installation, private update, rollback or corresponding-source publication
# acceptance is implied. Subsequent actual in-app transaction uses this candidate.
