# NOA Accounting — one-time Windows setup (no Docker).
# Installs: Python 3.12 venv + backend deps (uv or pip), frontend deps (pnpm),
# application-data directories, SQLite validation, Alembic migrations.
# Requires: Python 3.12+, Node.js 22+, pnpm 9+ (and optionally uv) on PATH.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[NOA] Repository root: $root"

# --- application data (kept OUTSIDE the repository) ---
$dataDir = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "NOA" } else { Join-Path $HOME ".local/share/NOA" }
$dirs = @(
    (Join-Path $dataDir "data"),
    (Join-Path $dataDir "receipt_storage"),
    (Join-Path $dataDir "backups"),
    (Join-Path $dataDir "logs")
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
if (-not $env:SQLITE_DATABASE_PATH) {
    $env:SQLITE_DATABASE_PATH = Join-Path $dataDir "data/noa.sqlite3"
}
Write-Host "[NOA] Data dir: $dataDir (DB: $env:SQLITE_DATABASE_PATH)"

# --- Python virtual environment ---
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = Join-Path $root ".venv/Scripts/python.exe"
& $py -m pip install --upgrade pip wheel
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv sync --dev
} else {
    & $py -m pip install -e ".[dev]"
}

# --- SQLite sanity check ---
& $py -c "import sqlite3; v=sqlite3.sqlite_version_info; assert v>=(3,37,0), f'SQLite too old: {v}'; print('[NOA] SQLite', sqlite3.sqlite_version, 'OK (STRICT tables supported)')"

# --- migrations (safe lifecycle: online backup + gate; Phase 6 §7) ---
& (Join-Path $PSScriptRoot "migrate_noa.ps1")

# --- frontend deps ---
if (Test-Path "frontend/package.json") {
    pnpm install --frozen-lockfile
    pnpm openapi-ts 2>$null
    pnpm build
} else {
    Write-Host "[NOA] frontend/ not present yet (Phase 3) — skipping."
}

Write-Host "[NOA] Setup complete. Start with scripts\start_noa.bat (or start_noa.ps1)."
