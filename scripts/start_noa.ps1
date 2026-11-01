# NOA Accounting — start backend (native Windows process, no containers).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $py)) { throw "[NOA] Run scripts/setup_windows.ps1 first." }
if (-not $env:SQLITE_DATABASE_PATH) {
    $env:SQLITE_DATABASE_PATH = Join-Path $env:LOCALAPPDATA "NOA/data/noa.sqlite3"
}
$env:PYTHONPATH = Join-Path $root "backend"
Write-Host "[NOA] Starting backend on http://127.0.0.1:8787 (logs: $($env:LOCALAPPDATA)\NOA\logs)"
New-Item -ItemType Directory -Force -Path (Join-Path $env:LOCALAPPDATA "NOA/logs") | Out-Null
$logFile = Join-Path $env:LOCALAPPDATA "NOA/logs/noa-stdout.log"
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8787" `
    -WorkingDirectory $root -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $env:LOCALAPPDATA "NOA/logs/noa-stderr.log") -WindowStyle Hidden
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8787/api/docs"
Write-Host "[NOA] Started. Use scripts\stop_noa.ps1 to stop."
