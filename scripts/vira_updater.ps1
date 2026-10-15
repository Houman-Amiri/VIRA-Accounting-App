# vira_updater.ps1 — transactional update helper (Phase 8 §6/§7)
#
# Compiled to vira-updater.exe in CI (ps2exe). The main app launches it after
# the user confirms the update. It:
#   1. takes a named mutex + lock file (single instance; app refuses to start mid-update)
#   2. gracefully stops FastAPI + scheduler (stop_vira semantics)
#   3. snapshots every file scheduled to change into {app}\rollback\prev\
#      (+ copies install_manifest.json / version.json)
#   4. applies file operations: copies from files/, bsdiff patches via tools\bspatch.exe,
#      deletes from delete.json
#   5. rewrites install_manifest.json + version.json
#   6. relaunches the app
# On ANY failure: restore the snapshot + manifests, relaunch the previous version,
# and surface «خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.» with this log path.
#
# The rollback snapshot is kept until the new version reports healthy
# (/api/v1/health/ready + accounting-invariant check) — the app deletes
# {app}\rollback only after that.

param(
    [Parameter(Mandatory = $true)][string]$Stage,   # staging dir: %LOCALAPPDATA%\VIRA\updates\<version>\
    [Parameter(Mandatory = $true)][string]$Log,     # update.log path
    [string]$InstallDir = "",                       # recorded InstallDir (registry fallback)
    [switch]$ForceFailure                           # CI forced-failure rollback test
)

$ErrorActionPreference = "Stop"
$logPath = if ($Log) { $Log } else { Join-Path $Stage "update.log" }

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logPath -Value $line -Encoding utf8
    Write-Output $line
}

function Invoke-Rollback {
    try {
        $rollback = Join-Path $InstallDir "rollback\prev"
        if (Test-Path $rollback) {
            Get-ChildItem $rollback -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($rollback.Length + 1)
                $dst = Join-Path $InstallDir $rel
                New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
                Copy-Item $_.FullName $dst -Force
            }
            Write-Log "restored snapshot from $rollback"
        }
        $launcher = Join-Path $InstallDir "start_vira.cmd"
        if (Test-Path $launcher) { Start-Process -FilePath $launcher -WorkingDirectory $InstallDir }
    }
    catch {
        Write-Log "rollback error: $($_.Exception.Message)"
    }
}

function Fail([string]$reason) {
    Write-Log "FAILED: $reason"
    Invoke-Rollback
    Write-Log "ROLLED BACK — previous version restored"
    Write-Output "خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد."
    Write-Output "جزئیات: $logPath"
    throw "vira-updater failed: $reason (previous version restored)"
}

# ---------------------------------------------------------------- mutex ----
$mutex = New-Object System.Threading.Mutex($false, "Global\VIRA-Updater")
if (-not $mutex.WaitOne(0)) {
    Write-Output "به‌روزرسانی دیگری در حال اجرا است."
    throw "another update is already running"
}
$lockFile = Join-Path $env:LOCALAPPDATA "VIRA\updates\.update.lock"
New-Item -ItemType Directory -Force -Path (Split-Path $lockFile) | Out-Null
Set-Content -Path $lockFile -Value $PID -Encoding ascii

try {
    # ------------------------------------------------------ locate install ----
    if (-not $InstallDir) {
        $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue
        if (-not $reg) { $reg = Get-ItemProperty -Path "HKCU:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue }
        if ($reg) { $InstallDir = $reg.InstallDir }
    }
    if (-not $InstallDir -or -not (Test-Path $InstallDir)) { Fail "InstallDir یافت نشد" }
    Write-Log "InstallDir=$InstallDir Stage=$Stage"

    $updateJson = Get-Content (Join-Path $Stage "update.json") -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $updateJson) { Fail "update.json نامعتبر است" }

    # --------------------------------------- stop app + scheduler (stop_vira) ----
    Get-Process -Name "python","uvicorn","node" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$InstallDir*" } | ForEach-Object {
            Write-Log "stopping $($_.ProcessName) pid=$($_.Id)"
            $_.CloseMainWindow() | Out-Null
        }
    Start-Sleep -Seconds 2
    schtasks /End /TN "VIRA\Backup" 2>$null | Out-Null

    # ------------------------------------------------ snapshot → rollback/prev ----
    $rollback = Join-Path $InstallDir "rollback\prev"
    New-Item -ItemType Directory -Force -Path $rollback | Out-Null
    Copy-Item (Join-Path $InstallDir "install_manifest.json") $rollback -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $InstallDir "version.json") $rollback -Force -ErrorAction SilentlyContinue
    foreach ($op in $updateJson.operations) {
        if ($op.op -eq "delete") { continue }
        $src = Join-Path $InstallDir ($op.path -replace "/", "\")
        if (Test-Path $src) {
            $dst = Join-Path $rollback ($op.path -replace "/", "\")
            New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
            Copy-Item $src $dst -Force
        }
    }
    Write-Log "snapshot complete -> $rollback"

    if ($ForceFailure) { Fail "forced failure (CI rollback test)" }

    # --------------------------------------------------------- apply ops ----
    $bspatch = Join-Path $InstallDir "tools\bspatch.exe"
    foreach ($op in $updateJson.operations) {
        $rel = $op.path -replace "/", "\"
        $target = Join-Path $InstallDir $rel
        switch ($op.op) {
            "delete" {
                if (Test-Path $target) { Remove-Item $target -Force }
                Write-Log "deleted $rel"
            }
            { $_ -in @("add", "replace") } {
                $member = Join-Path $Stage ("files\" + ($op.path -replace "/", "\"))
                if (-not (Test-Path $member)) { Fail "missing staged file $member" }
                $hash = (Get-FileHash -Algorithm SHA256 $member).Hash.ToLower()
                if ($op.sha256 -and $hash -ne $op.sha256.ToLower()) { Fail "SHA-256 mismatch: $rel" }
                New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
                Copy-Item $member $target -Force
                Write-Log "$($op.op) $rel"
            }
            "patch" {
                $patchFile = Join-Path $Stage ($op.patch -replace "/", "\")
                $applier = $null; $applierArgs = @()
                if (Test-Path $bspatch) {
                    $applier = $bspatch; $applierArgs = @($target, $tmp, $patchFile)
                } else {
                    # pure-Python fallback shipped with the payload (v1.0.3+)
                    $py = Join-Path $InstallDir "python\python.exe"
                    if (-not (Test-Path $py)) { $py = "python" }
                    $bspatchPy = Join-Path $InstallDir "scripts\bspatch.py"
                    if (-not (Test-Path $bspatchPy)) { Fail "no patch applier available (tools\bspatch.exe / scripts\bspatch.py)" }
                    $applier = $py; $applierArgs = @($bspatchPy, $target, $tmp, $patchFile)
                }
                $tmp = "$target.new"
                $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
                & $applier @applierArgs
                $code = $LASTEXITCODE
                $ErrorActionPreference = $prevEap
                if ($code -ne 0 -or -not (Test-Path $tmp)) { Fail "bspatch failed: $rel" }
                $hash = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLower()
                if ($op.sha256 -and $hash -ne $op.sha256.ToLower()) { Fail "patched SHA-256 mismatch: $rel" }
                Move-Item $tmp $target -Force
                Write-Log "patched $rel"
            }
        }
    }

    # ------------------------------------ rewrite manifests (§6 step 3) ----
    Copy-Item (Join-Path $Stage "install_manifest.json") (Join-Path $InstallDir "install_manifest.json") -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $Stage "version.json") (Join-Path $InstallDir "version.json") -Force -ErrorAction SilentlyContinue
    Write-Log "manifests rewritten"

    # -------------------------------------------------- relaunch the app ----
    $launcher = Join-Path $InstallDir "start_vira.cmd"
    if (Test-Path $launcher) { Start-Process -FilePath $launcher -WorkingDirectory $InstallDir }
    Write-Log "relaunched — awaiting health check (rollback kept at $rollback)"
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    exit 0
}
catch {
    Fail $_.Exception.Message
}
finally {
    $mutex.ReleaseMutex() | Out-Null
}
