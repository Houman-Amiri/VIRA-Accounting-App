# stage_app_payload.ps1 — assemble the app payload the Inno installer wraps (Phase 8 §1)
#
# Contents: backend bundle (uv-locked site-packages + FastAPI app), compiled
# React SPA static assets (served by FastAPI), native PowerShell scripts,
# vira-updater.exe, version.json, install_manifest.json.

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$OutDir
)

$ErrorActionPreference = "Stop"
$v = $Version.TrimStart("v")
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# bundled CPython 3.11 (python-build-standalone via uv) — the installed app
# must run on machines without a system Python (v1.0.3 fix)
uv python install 3.11 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "managed CPython install failed" }
$pyExe = (uv python find --system --managed-python 3.11).Trim()
if ($LASTEXITCODE -ne 0) { throw "managed CPython discovery failed" }
if (-not (Test-Path $pyExe)) { throw "uv python find 3.11 returned nothing" }
$pyDir = Split-Path -Parent $pyExe
Copy-Item -Recurse $pyDir "$OutDir/python"
Write-Host "[stage_app_payload] bundled CPython from $pyDir"

# backend + locked site-packages FOR the bundled interpreter (cp311) —
# without --python, uv targets the runner default and .pyd ABI tags mismatch
uv export --frozen --no-dev --no-emit-project --output-file "$OutDir/requirements.lock.txt" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "production lock export failed" }
uv pip install --python "$pyExe" --target "$OutDir/site-packages" -r "$OutDir/requirements.lock.txt"
if ($LASTEXITCODE -ne 0) { throw "production dependency staging failed" }
Remove-Item "$OutDir/requirements.lock.txt"
Copy-Item -Recurse backend/app "$OutDir/app"

# alembic bits — migrate_vira.py resolves {app}\backend\alembic(.ini)
New-Item -ItemType Directory -Force -Path "$OutDir/backend" | Out-Null
Copy-Item backend/alembic.ini "$OutDir/backend/alembic.ini"
Copy-Item -Recurse backend/alembic "$OutDir/backend/alembic"

# compiled SPA (served from app/static)
if (Test-Path frontend/dist) {
    New-Item -ItemType Directory -Force -Path "$OutDir/static" | Out-Null
    Copy-Item -Recurse frontend/dist/* "$OutDir/static/"
}

# native scripts + root launcher (shortcuts target {app}\start_vira.cmd)
Copy-Item -Recurse scripts "$OutDir/scripts"
Copy-Item scripts/start_vira.cmd "$OutDir/start_vira.cmd"

# version stamp (single source of truth: backend/pyproject.toml → version_info());
# the commit is what the System & Operations page shows as «کامیت» (v1.0.5 fix)
$commit = ""
if ($env:GITHUB_SHA) { $commit = $env:GITHUB_SHA.Substring(0, [Math]::Min(7, $env:GITHUB_SHA.Length)) }
if (-not $commit) {
    try { $commit = (git rev-parse --short HEAD 2>$null).Trim() } catch { $commit = "" }
}
if (-not $commit) { $commit = "unknown" }
# build id of the SPA we just staged — «سیستم و عملیات» compares it with the id
# the browser loaded, so a stale cached UI is visible instead of silent (v1.0.5)
$spaBuild = ""
$indexHtml = Join-Path $OutDir "static/index.html"
if (Test-Path $indexHtml) {
    $match = [regex]::Match((Get-Content $indexHtml -Raw), 'name="vira-build"\s+content="([^"]+)"')
    if ($match.Success) { $spaBuild = $match.Groups[1].Value }
}
if (-not $spaBuild) {
    Write-Warning "[stage_app_payload] static/index.html has no vira-build marker — falling back to the commit"
    $spaBuild = $commit
}
@{
    version = $v
    commit = $commit
    built_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    spa_build = $spaBuild
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $OutDir "version.json")
Write-Host "[stage_app_payload] version.json: version=$v commit=$commit spa_build=$spaBuild"

# update verification key — a packaged client must reject an unsigned latest.json
# and must accept the release signature. Absent key keeps the previous behaviour.
if ($env:VIRA_UPDATE_PUBLIC_KEY_FILE -and (Test-Path -LiteralPath $env:VIRA_UPDATE_PUBLIC_KEY_FILE)) {
    Copy-Item -LiteralPath $env:VIRA_UPDATE_PUBLIC_KEY_FILE -Destination (Join-Path $OutDir "update-public-key.pem")
    Write-Host "[stage_app_payload] baked the update verification key"
}

# per-file manifest — the delta baseline (Phase 8 §1/§5)
uv run python scripts/build_manifest.py $OutDir
if ($LASTEXITCODE -ne 0) { throw "payload manifest generation failed" }
Write-Host "[stage_app_payload] staged $OutDir"
