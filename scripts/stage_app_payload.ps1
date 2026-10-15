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
$pyExe = (uv python find 3.11).Trim()
if (-not (Test-Path $pyExe)) { throw "uv python find 3.11 returned nothing" }
$pyDir = Split-Path -Parent $pyExe
Copy-Item -Recurse $pyDir "$OutDir/python"
Write-Host "[stage_app_payload] bundled CPython from $pyDir"

# backend + locked site-packages FOR the bundled interpreter (cp311) —
# without --python, uv targets the runner default and .pyd ABI tags mismatch
uv export --frozen --no-dev --no-emit-project --output-file "$OutDir/requirements.lock.txt" | Out-Null
uv pip install --python "$pyExe" --target "$OutDir/site-packages" -r "$OutDir/requirements.lock.txt"
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

# version stamp (single source of truth: backend/pyproject.toml → version_info())
@{
    version = $v
    built_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $OutDir "version.json")

# per-file manifest — the delta baseline (Phase 8 §1/§5)
uv run python scripts/build_manifest.py $OutDir
Write-Host "[stage_app_payload] staged $OutDir"
