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

# backend + locked site-packages (runtime extras only — no dev group)
uv export --frozen --no-dev --no-emit-project --output-file "$OutDir/requirements.lock.txt" | Out-Null
uv pip install --target "$OutDir/site-packages" -r "$OutDir/requirements.lock.txt"
Remove-Item "$OutDir/requirements.lock.txt"
Copy-Item -Recurse backend/app "$OutDir/app"

# compiled SPA (served from app/static)
if (Test-Path frontend/dist) {
    New-Item -ItemType Directory -Force -Path "$OutDir/static" | Out-Null
    Copy-Item -Recurse frontend/dist/* "$OutDir/static/"
}

# native scripts
Copy-Item -Recurse scripts "$OutDir/scripts"

# version stamp (single source of truth: backend/pyproject.toml → version_info())
@{
    version = $v
    built_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $OutDir "version.json")

# per-file manifest — the delta baseline (Phase 8 §1/§5)
uv run python scripts/build_manifest.py $OutDir
Write-Host "[stage_app_payload] staged $OutDir"
