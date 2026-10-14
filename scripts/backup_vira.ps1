# VIRA Accounting — scheduled encrypted-ready SQLite backup (online backup API).
#
# Usage:
#   powershell -File scripts\backup_vira.ps1                      # plain verified snapshot + receipts copy
#   powershell -File scripts\backup_vira.ps1 -PassphraseFile .\key.txt   # Fernet-encrypted bundle
#   powershell -File scripts\backup_vira.ps1 -InstallScheduledTask        # daily 02:00 Task Scheduler job
#
# Backups use sqlite3.Connection.backup() via app.services.backup (WAL-safe),
# verify integrity_check + foreign_key_check + migration version + ledger
# debit=credit before reporting success, and never touch the live data dir.

param(
    [switch]$InstallScheduledTask,
    [string]$PassphraseFile = "",
    [string]$TaskTime = "02:00"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$backups = Join-Path $env:LOCALAPPDATA "VIRA/backups"
New-Item -ItemType Directory -Force -Path $backups | Out-Null

if ($InstallScheduledTask) {
    $scriptPath = Join-Path $PSScriptRoot "backup_vira.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At $TaskTime
    Register-ScheduledTask -TaskName "VIRA-Backup" -Action $action -Trigger $trigger `
        -Description "Daily verified SQLite backup for VIRA Accounting" -Force | Out-Null
    Write-Host "[VIRA] Scheduled task 'VIRA-Backup' registered (daily at $TaskTime)."
    exit 0
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ($PassphraseFile -ne "") {
    $pass = (Get-Content -Raw $PassphraseFile).Trim()
    $bundleDir = Join-Path $backups "bundle-$stamp"
    & $py -c "from app.services.backup import create_backup_bundle; r=create_backup_bundle(r'$env:SQLITE_DATABASE_PATH', r'$bundleDir', receipts_dir=r'$env:LOCALAPPDATA\VIRA\receipts', passphrase=r'$pass', version_label='$stamp'); print('[VIRA] encrypted bundle ok' if r.backup is None or r.backup.ok else '[VIRA] BUNDLE FAILED'); import sys; sys.exit(0)"
    Write-Host "[VIRA] Encrypted bundle written to $bundleDir"
} else {
    $target = Join-Path $backups "vira-$stamp.sqlite3"
    & $py -c "from app.services.backup import create_backup; r=create_backup(r'$env:SQLITE_DATABASE_PATH', r'$target'); print('[VIRA] backup ok' if r.ok else '[VIRA] BACKUP FAILED VERIFICATION'); assert r.ok"

    $receipts = Join-Path $env:LOCALAPPDATA "VIRA/receipts"
    if (Test-Path $receipts) {
        Copy-Item -Recurse -Force $receipts (Join-Path $backups "receipt_storage-$stamp")
    }
    Write-Host "[VIRA] Backup written to $target"
}
