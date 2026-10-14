<#
.SYNOPSIS
  Safe SQLite migration lifecycle wrapper (Phase 6 §7).

.DESCRIPTION
  Creates a verified online backup, runs `alembic upgrade head` under a single-
  process lock, then gates on foreign_key_check + Alembic revision + debit/credit
  equality. On failure it prints the tested restore command.

.EXAMPLE
  .\migrate_vira.ps1
  .\migrate_vira.ps1 -Database "$env:LOCALAPPDATA\VIRA\data\vira.sqlite3" -Report migration-report.json
  .\migrate_vira.ps1 -Restore "$env:LOCALAPPDATA\VIRA\backups"
#>
[CmdletBinding()]
param(
    [string]$Database = "",
    [string]$Report = "",
    [string]$Restore = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Database -eq "") {
    $Database = $env:SQLITE_DATABASE_PATH
    if (-not $Database) {
        $Database = Join-Path $env:LOCALAPPDATA "VIRA\data\vira.sqlite3"
    }
}

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

$argsList = @((Join-Path $PSScriptRoot "migrate_vira.py"), "--database", $Database)
if ($Report -ne "") { $argsList += @("--report", $Report) }
if ($Restore -ne "") { $argsList += @("--restore", $Restore) }

& $py @argsList
exit $LASTEXITCODE
