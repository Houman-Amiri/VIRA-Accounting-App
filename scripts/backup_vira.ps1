# VIRA Accounting — scheduled encrypted-ready SQLite backup (online backup API).
# Registers cleanly with Windows Task Scheduler:
#   powershell -File scripts\backup_vira.ps1
# Backs up the live database (WAL-consistent) + receipt storage, then verifies.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv/Scripts/python.exe"
if (-not $env:SQLITE_DATABASE_PATH) {
    $env:SQLITE_DATABASE_PATH = Join-Path $env:LOCALAPPDATA "VIRA/data/vira.sqlite3"
}
$backups = Join-Path $env:LOCALAPPDATA "VIRA/backups"
New-Item -ItemType Directory -Force -Path $backups | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$target = Join-Path $backups "vira-$stamp.sqlite3"

$env:PYTHONPATH = Join-Path $root "backend"
& $py -c "from app.services.backup import create_backup; r=create_backup(r'$env:SQLITE_DATABASE_PATH', r'$target'); print('[VIRA] backup ok' if r.ok else '[VIRA] BACKUP FAILED VERIFICATION'); assert r.ok"

# copy receipts alongside the snapshot
$receipts = Join-Path $env:LOCALAPPDATA "VIRA/receipt_storage"
if (Test-Path $receipts) {
    Copy-Item -Recurse -Force $receipts (Join-Path $backups "receipt_storage-$stamp")
}
Write-Host "[VIRA] Backup written to $target"
Write-Host "[VIRA] Optional: encrypt with age/restic before copying off-machine (see project brief.md)."
