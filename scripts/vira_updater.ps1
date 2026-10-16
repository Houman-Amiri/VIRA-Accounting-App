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
    [Alias("install-dir")][string]$InstallDir = "",                       # recorded InstallDir (registry fallback)
    [int]$ParentPid = 0,
    [int]$Port = 0,
    [string]$ResultPath = "",
    [int]$HealthTimeoutSeconds = 90,
    [switch]$ForceFailure                           # CI forced-failure rollback test
)

$ErrorActionPreference = "Stop"
$logPath = if ($Log) { $Log } else { Join-Path $Stage "update.log" }

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logPath -Value $line -Encoding utf8
    Write-Output $line
}

# ps2exe hosts do not always expose Get-FileHash. Use .NET directly so
# verification also works in the compiled helper (Windows PowerShell 5.1).
function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

# A journal for THIS attempt only: deleted files need snapshots too, and new
# files must be removed on rollback. Never infer success from a process spawn.
$script:snapshotComplete = $false
$script:appStopped = $false
$script:saved = @{}
$script:added = @()
$script:launcherPid = 0
$script:targetVersion = ""
if (-not $Port) { $Port = if ($env:VIRA_PORT) { [int]$env:VIRA_PORT } else { 8787 } }

function Write-Result([string]$State, [string]$Reason = "") {
    if (-not $ResultPath) { return }
    $result = @{ state = $State; target_version = $script:targetVersion; log_path = $logPath;
        error_fa = $Reason; verified = ($State -eq "committed"); machine_state = $State }
    New-Item -ItemType Directory -Force -Path (Split-Path $ResultPath) | Out-Null
    [IO.File]::WriteAllText(($ResultPath + ".tmp"), ($result | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath ($ResultPath + ".tmp") -Destination $ResultPath -Force
}

function Safe-Target([string]$Relative) {
    if ($Relative -notmatch '^(app|backend|python|scripts|site-packages|static|tools)/|^(version.json|install_manifest.json|start_vira.cmd|vira-updater.exe)$') {
        throw "non-application target: $Relative"
    }
    if ($Relative.Contains("\") -or $Relative.Contains(":") -or ($Relative.Split("/") -contains "..")) { throw "unsafe path: $Relative" }
    $full = [IO.Path]::GetFullPath((Join-Path $InstallDir $Relative))
    if (-not $full.StartsWith(($InstallDir.TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw "path escape: $Relative" }
    return $full
}

function Stop-App {
    if ($script:launcherPid) {
        & taskkill.exe /PID $script:launcherPid /T /F 2>&1 | Out-Null
        $script:launcherPid = 0
    }
    $prefix = $InstallDir.TrimEnd('\') + '\'
    $processes = @(Get-Process -Name python,pythonw,uvicorn -ErrorAction SilentlyContinue | Where-Object {
        ($_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) -or $_.Id -eq $ParentPid
    })
    foreach ($process in $processes) {
        $process.CloseMainWindow() | Out-Null
        if (-not $process.WaitForExit(2000)) { Stop-Process -Id $process.Id -Force; $process.WaitForExit() }
    }
}

function Start-App {
    # Old launchers export their running version. Do NOT pass that stale stamp
    # to the new backend: the new version.json is authoritative after restart.
    Remove-Item Env:VIRA_VERSION,Env:VIRA_GIT_COMMIT,Env:VIRA_SPA_BUILD -ErrorAction SilentlyContinue
    $env:VIRA_UPDATE_RESTART = "1"
    $launcher = Join-Path $InstallDir "start_vira.cmd"
    if (-not (Test-Path -LiteralPath $launcher)) { throw "launcher missing" }
    $started = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"`"$launcher`"`"" -WorkingDirectory $InstallDir -PassThru
    $script:launcherPid = $started.Id
}

function Wait-Healthy($Stamp) {
    $deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
    do {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/health/ready" -TimeoutSec 2
            $spa = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/" -TimeoutSec 2
            $expected = [string]$Stamp.spa_build
            if (-not $expected -and $Stamp.commit) { $expected = ([string]$Stamp.commit).Substring(0, [Math]::Min(7, ([string]$Stamp.commit).Length)) }
            if ($health.status -eq "ready" -and $health.invariants.integrity_check -eq "ok" -and
                $health.invariants.foreign_key_violations -eq 0 -and $health.invariants.balanced -eq $true -and
                (-not $expected -or ([string]$spa.Headers['X-VIRA-SPA-Build']) -eq $expected)) { return }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "restarted application did not pass readiness/build validation"
}

# ---------------------------------------------------------------- mutex ----
$mutex = New-Object System.Threading.Mutex($false, "Global\VIRA-Updater")
if (-not $mutex.WaitOne(0)) {
    Write-Output "به‌روزرسانی دیگری در حال اجرا است."
    throw "another update is already running"
}
$lockFile = if ($ResultPath) { Join-Path (Split-Path $ResultPath) ".update.lock" } else { Join-Path $env:LOCALAPPDATA "VIRA\updates\.update.lock" }
New-Item -ItemType Directory -Force -Path (Split-Path $lockFile) | Out-Null
Set-Content -Path $lockFile -Value $PID -Encoding ascii

try {
    # ------------------------------------------------------ locate install ----
    if (-not $InstallDir) {
        $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue
        if (-not $reg) { $reg = Get-ItemProperty -Path "HKCU:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue }
        if ($reg) { $InstallDir = $reg.InstallDir }
    }
    if (-not $InstallDir -or -not (Test-Path $InstallDir)) { throw "InstallDir یافت نشد" }
    $InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    Write-Log "InstallDir=$InstallDir Stage=$Stage"

    $updateJson = Get-Content (Join-Path $Stage "update.json") -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $updateJson) { throw "update.json نامعتبر است" }

    $oldStamp = Get-Content (Join-Path $InstallDir "version.json") -Raw -Encoding utf8 | ConvertFrom-Json
    $newStamp = Get-Content (Join-Path $Stage "version.json") -Raw -Encoding utf8 | ConvertFrom-Json
    $script:targetVersion = [string]$newStamp.version
    if ($oldStamp.version -ne $updateJson.base_version -or $newStamp.version -ne $updateJson.target_version) { throw "base/target version mismatch" }
    foreach ($op in $updateJson.operations) {
        $null = Safe-Target $op.path
        if ($op.op -notin @("add", "replace", "patch", "delete")) { throw "unknown file operation" }
    }
    # Let the apply HTTP response finish before shutting down its process.
    Start-Sleep -Seconds 2
    Stop-App
    $script:appStopped = $true

    $rollback = Join-Path $InstallDir "rollback\prev"
    if (Test-Path $rollback) { Move-Item $rollback ($rollback + "-" + [guid]::NewGuid().ToString('N')) }
    New-Item -ItemType Directory -Force -Path $rollback | Out-Null
    $paths = @("version.json", "install_manifest.json") + @($updateJson.operations | ForEach-Object { $_.path })
    foreach ($relative in ($paths | Select-Object -Unique)) {
        $src = Safe-Target $relative
        if (Test-Path -LiteralPath $src) {
            $dst = Join-Path $rollback $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
            Copy-Item -LiteralPath $src -Destination $dst -Force
            $script:saved[$relative] = Get-Sha256 $src
        } else { $script:added += $relative }
    }
    $script:snapshotComplete = $true
    Write-Log "snapshot complete -> $rollback"

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
                if (-not (Test-Path $member)) { throw "missing staged file $member" }
                $hash = (Get-Sha256 $member)
                if ($op.sha256 -and $hash -ne $op.sha256.ToLower()) { throw "SHA-256 mismatch: $rel" }
                New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
                Copy-Item $member $target -Force
                Write-Log "$($op.op) $rel"
            }
            "patch" {
                $patchFile = Join-Path $Stage ($op.patch -replace "/", "\")
                # Initialize before building argv (otherwise the applier gets
                # an empty/stale output path).
                $tmp = $target + ".new"
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                $applier = $null
                $applierArgs = @()
                if (Test-Path $bspatch) {
                    $applier = $bspatch
                    $applierArgs = @($target, $tmp, $patchFile)
                } else {
                    # pure-Python fallback shipped with the payload (v1.0.3+)
                    $py = Join-Path $InstallDir "python\python.exe"
                    if (-not (Test-Path $py)) { $py = "python" }
                    $bspatchPy = Join-Path $InstallDir "scripts\bspatch.py"
                    if (-not (Test-Path $bspatchPy)) { throw "no patch applier available (tools\bspatch.exe / scripts\bspatch.py)" }
                    # the applier imports the engine (pydantic) — the bundled
                    # interpreter needs the payload's site-packages, which is
                    # NOT on the default path when the updater runs standalone
                    $env:PYTHONPATH = (Join-Path $InstallDir "site-packages") + ";" + $InstallDir
                    $applier = $py
                    $applierArgs = @($bspatchPy, $target, $tmp, $patchFile)
                }
                $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
                $applierOutput = (& $applier @applierArgs 2>&1 | Out-String)
                $code = $LASTEXITCODE
                $ErrorActionPreference = $prevEap
                if ($code -ne 0) {
                    Write-Log "applier said: $($applierOutput.Trim())"
                    throw "bspatch failed: $rel (exit $code)"
                }
                if (-not (Test-Path $tmp)) { throw "bspatch produced no output: $rel" }
                $hash = (Get-Sha256 $tmp)
                if ($op.sha256 -and $hash -ne $op.sha256.ToLower()) { throw "patched SHA-256 mismatch: $rel" }
                Move-Item $tmp $target -Force
                Write-Log "patched $rel"
            }
        }
    }

    if ($ForceFailure) { throw "forced failure AFTER file operations (CI rollback test)" }

    # ------------------------------------ rewrite manifests (§6 step 3) ----
    Copy-Item (Join-Path $Stage "install_manifest.json") (Join-Path $InstallDir "install_manifest.json") -Force
    Copy-Item (Join-Path $Stage "version.json") (Join-Path $InstallDir "version.json") -Force
    Write-Log "manifests rewritten"

    Start-App
    Wait-Healthy $newStamp
    Write-Result "committed"
    Write-Log "COMMITTED — readiness, accounting invariants and build validated"
    # Only a proven healthy version permits removing this attempt's rollback.
    Remove-Item -LiteralPath $rollback -Recurse -Force
}
catch {
    $failure = $_.Exception.Message
    Write-Log "FAILED: $failure"
    try {
        if ($script:appStopped) { Stop-App }
        if ($script:snapshotComplete) {
            foreach ($relative in $script:added) {
                $target = Safe-Target $relative
                if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
            }
            foreach ($relative in $script:saved.Keys) {
                $target = Safe-Target $relative
                Copy-Item -LiteralPath (Join-Path $rollback $relative) -Destination $target -Force
                if ((Get-Sha256 $target) -ne $script:saved[$relative]) { throw "rollback verification failed: $relative" }
            }
            Start-App
            Wait-Healthy $oldStamp
            Write-Result "rolled_back" "به‌روزرسانی ناموفق بود؛ فایل‌های قبلی بازگردانده و سلامت نسخهٔ قبلی تأیید شد."
            Write-Log "ROLLED BACK — previous files and health verified"
        } else {
            if ($script:appStopped) { Start-App; Wait-Healthy $oldStamp }
            Write-Result "failed" "به‌روزرسانی پیش از تکمیل پشتیبان فایل‌ها متوقف شد؛ گزارش را بررسی کنید."
        }
    } catch {
        Write-Log "ROLLBACK FAILED: $($_.Exception.Message)"
        Write-Result "failed" "بازگردانی کامل تأیید نشد؛ از اجرای نصب دوباره خودداری و گزارش را بررسی کنید."
    }
    throw "vira-updater failed: $failure (see $logPath)"
}
finally {
    Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex() | Out-Null
}
