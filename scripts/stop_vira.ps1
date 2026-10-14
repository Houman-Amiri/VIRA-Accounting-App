# VIRA Accounting — stop backend/dev processes started by start_vira.ps1.
$ErrorActionPreference = "Continue"
foreach ($port in @(8787, 5173)) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "[VIRA] Stopping PID $($c.OwningProcess) on port $port"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "[VIRA] Stopped."
