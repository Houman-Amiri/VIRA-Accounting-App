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
    [string]$PrivateSourceTransaction = "",       # explicit private CI context, NEVER public auto-selection
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

# Compare the ENTIRE copied interpreter subtree to the already anchored OLD
# manifest, before invoking ANY executable from it. Copy-Item success alone is
# not integrity verification (missing/extra/corrupt/reparse entries fail closed).
function Assert-PrivatePythonClone([string]$Runtime, [object[]]$BaselineFiles) {
    $root = [IO.Path]::GetFullPath($Runtime).TrimEnd('\')
    $prefix = $root + '\'
    $ancestor = New-Object IO.DirectoryInfo -ArgumentList $root
    while ($ancestor) {
        if ($ancestor.Exists -and ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Private Python clone reparse path' }
        $ancestor = $ancestor.Parent
    }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'Private Python clone missing directory' }
    $expected = @{}
    foreach ($entry in $BaselineFiles) {
        $name = [string]$entry.path
        if (-not $name.StartsWith('python/', [StringComparison]::Ordinal)) { continue }
        $relative = $name.Substring(7)
        if (-not $relative -or $relative.Contains('\') -or $relative.Contains(':') -or
            ($relative.Split('/') -contains '..') -or ($relative.Split('/') -contains '.') -or
            ($relative.Split('/') -contains '') -or $expected.ContainsKey($relative)) { throw 'Private Python clone ambiguous path' }
        $full = [IO.Path]::GetFullPath((Join-Path $root $relative))
        if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Private Python clone escaped root' }
        $expected[$relative] = $entry
    }
    if (-not $expected.ContainsKey('python.exe')) { throw 'Private Python executable not anchored' }
    $seen = @{}
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($root)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($item in @(Get-ChildItem -LiteralPath $directory -Force)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Private Python clone reparse entry' }
            if ($item.PSIsContainer) { $pending.Push($item.FullName); continue }
            $relative = $item.FullName.Substring($prefix.Length).Replace('\','/')
            if (-not $expected.ContainsKey($relative) -or $seen.ContainsKey($relative)) { throw 'Private Python clone extra/duplicate file' }
            $entry = $expected[$relative]
            if ($item.Length -ne $entry.size -or (Get-Sha256 $item.FullName) -cne $entry.sha256) { throw 'Private Python clone differs from anchored bytes' }
            $seen[$relative] = $true
        }
    }
    if ($seen.Count -ne $expected.Count) { throw 'Private Python clone missing anchored file' }
}

# PowerShell 5.1 turns a native stderr line into an ErrorRecord. With Stop,
# the first traceback line used to interrupt this pipeline and hide the rest.
# Drain BOTH streams without treating stderr as the exit status; restore Stop
# even on a launch failure. The caller still validates exit/journal/guards.
function Invoke-PrivateController([string]$Executable, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = $null
        & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host ([string]$_) }
        $nativeCode = $global:LASTEXITCODE
        if ($null -eq $nativeCode) { throw 'Private controller exit code absent' }
        return [int]$nativeCode
    } finally {
        $ErrorActionPreference = $previous
    }
}

# Phase 3 private source branch. Public transaction below remains the default.
# Clone the verified OLD runtime outside {app} so Python/DLL replacement cannot
# lock the interpreter executing the transaction. No alternate QA factory exists.
if ($PrivateSourceTransaction) {
    if ($env:GITHUB_ACTIONS -ne "true") { throw "Private installed source Windows CI only" }
    $runnerPrefix = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\') + '\'
    $privateHome = Join-Path $env:LOCALAPPDATA "VIRA\private-native-installed"
    $installFull = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
    $stageFull = [IO.Path]::GetFullPath($Stage).TrimEnd('\')
    foreach ($path in @($installFull, $stageFull, $privateHome, (Join-Path $privateHome 'anchor.json'), (Join-Path $installFull 'install_manifest.json'), $PrivateSourceTransaction)) {
        $full = [IO.Path]::GetFullPath($path)
        if (-not $full.StartsWith($runnerPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Disposable private runner paths required" }
        $item = New-Object IO.FileInfo -ArgumentList $full
        while ($item) {
            if ((Test-Path -LiteralPath $item.FullName) -and ((Get-Item -LiteralPath $item.FullName -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Private reparse path rejected" }
            $item = if ($item -is [IO.FileInfo]) { $item.Directory } else { $item.Parent }
        }
    }
    if ($stageFull.StartsWith(($installFull + '\'), [StringComparison]::OrdinalIgnoreCase) -or
        $installFull.StartsWith(($stageFull + '\'), [StringComparison]::OrdinalIgnoreCase) -or
        $stageFull -eq $installFull) { throw "Private stage must be disjoint from payload" }
    $pin = Get-Content -LiteralPath (Join-Path $privateHome 'anchor.json') -Raw -Encoding utf8 | ConvertFrom-Json
    $manifestFile = Join-Path $installFull 'install_manifest.json'
    if ($pin.role -ne 'PRIVATE_SOURCE_INSTALLED_ANCHOR' -or (Get-Sha256 $manifestFile) -ne $pin.manifest_sha256) { throw "Independent old private anchor mismatch" }
    $baseline = Get-Content -LiteralPath $manifestFile -Raw -Encoding utf8 | ConvertFrom-Json
    # Verify EVERY old runtime byte before executing the external clone.
    $seenPrivate = @{}
    foreach ($file in $baseline.files) {
        $relative = [string]$file.path
        $full = [IO.Path]::GetFullPath((Join-Path $installFull $relative))
        if ($relative.Contains('\') -or $relative.Contains(':') -or ($relative.Split('/') -contains '..') -or
            -not $full.StartsWith(($installFull + '\'), [StringComparison]::OrdinalIgnoreCase) -or $seenPrivate.ContainsKey($relative)) { throw "Unsafe/duplicate private runtime path" }
        $seenPrivate[$relative] = $true
        $item = New-Object IO.FileInfo -ArgumentList $full
        while ($item) {
            if ((Test-Path -LiteralPath $item.FullName) -and ((Get-Item -LiteralPath $item.FullName -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Private runtime reparse path rejected" }
            $item = if ($item -is [IO.FileInfo]) { $item.Directory } else { $item.Parent }
        }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf) -or (Get-Item -LiteralPath $full).Length -ne $file.size -or (Get-Sha256 $full) -ne $file.sha256) { throw "Private old runtime differs from independent baseline" }
    }
    $entry = @($baseline.files | Where-Object { $_.path -ceq 'scripts/private_source_update.py' })
    $driver = Join-Path $installFull 'scripts/private_source_update.py'
    if ($entry.Count -ne 1 -or (Get-Sha256 $driver) -ne $entry[0].sha256) { throw "Old private controller not independently verified" }
    $context = Get-Content -LiteralPath $PrivateSourceTransaction -Raw -Encoding utf8 | ConvertFrom-Json
    if ($context.role -ne 'PRIVATE_SOURCE_TRANSACTION') { throw "Private transaction context required" }
    $privateOldAnchorHash = Get-Sha256 (Join-Path $privateHome 'anchor.json')
    $privateTargetAnchorHash = Get-Sha256 ([string]$context.target_anchor)
    $privateMutex = New-Object System.Threading.Mutex($false, 'Global\VIRA-Updater')
    if (-not $privateMutex.WaitOne(0)) { throw "another update is already running" }
    $channelLock = Join-Path $privateHome '.native-channel.lock'
    $privateAttempt = [IO.Path]::GetFileName([string]$context.attempt)
    if (-not $ResultPath) { $ResultPath = Join-Path $privateHome 'state\data\updates\last-result.json' }
    $expectedResult = [IO.Path]::GetFullPath((Join-Path $privateHome 'state\data\updates\last-result.json'))
    if ([IO.Path]::GetFullPath($ResultPath) -ne $expectedResult) {
        $privateMutex.ReleaseMutex() | Out-Null
        $privateMutex.Dispose()
        throw 'Foreign private result path'
    }
    $channelOwned = $false
    $privateCode = 1
    try {
        $stream = [IO.File]::Open($channelLock,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try {
            $channelBytes = [Text.Encoding]::UTF8.GetBytes((@{pid=$PID;attempt_id=$privateAttempt} | ConvertTo-Json -Compress))
            $stream.Write($channelBytes,0,$channelBytes.Length)
            $stream.Flush($true)
            $channelOwned = $true
        } finally { $stream.Dispose() }
        $external = Join-Path $env:RUNNER_TEMP ('VIRA controller خصوصی ! & ' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $external | Out-Null
        Copy-Item -LiteralPath $driver -Destination (Join-Path $external 'private_source_update.py')
        if ((Get-Sha256 (Join-Path $external 'private_source_update.py')) -ne $entry[0].sha256) { throw "Private controller copy mismatch" }
        Copy-Item -LiteralPath (Join-Path $installFull 'python') -Destination (Join-Path $external 'python') -Recurse
        Assert-PrivatePythonClone (Join-Path $external 'python') $baseline.files
        $privateArgs = @('-I','-S','-B','-X','utf8',(Join-Path $external 'private_source_update.py'),
            '--install-root',$installFull,'--archive',[string]$context.archive,'--archive-sha256',[string]$context.archive_sha256,
            '--target-anchor',[string]$context.target_anchor,'--attempt',[string]$context.attempt)
        if ($ForceFailure) { $privateArgs += '--force-failure-after-apply' }
        Start-Sleep -Seconds 2 # let the authenticated apply HTTP response complete
        $privateCode = Invoke-PrivateController (Join-Path $external 'python\python.exe') $privateArgs
    } finally {
        try {
            if ($channelOwned) {
                # Check ownership BEFORE publishing any result. Backend also
                # refuses terminal receipts until all private guards are gone.
                $owner = Get-Content -LiteralPath $channelLock -Raw -Encoding utf8 | ConvertFrom-Json
                if ($owner.pid -ne $PID -or $owner.attempt_id -ne $privateAttempt) { throw 'Private channel lock ownership changed' }
                $terminal = 'failed'
                $journalPath = Join-Path ([string]$context.attempt) 'result.json'
                if (Test-Path -LiteralPath $journalPath) {
                    $journal = Get-Content -LiteralPath $journalPath -Raw -Encoding utf8 | ConvertFrom-Json
                    $guardsReleased = -not (Test-Path -LiteralPath (Join-Path $privateHome '.native-update.lock')) -and
                        -not (Test-Path -LiteralPath (Join-Path $privateHome 'state/data/updates/.update.lock'))
                    $journalBound = $journal.schema -eq 1 -and $journal.role -eq 'PRIVATE_NATIVE_TRANSACTION_JOURNAL' -and
                        $journal.old_anchor_sha256 -ceq $privateOldAnchorHash -and
                        $journal.target_anchor_sha256 -ceq $privateTargetAnchorHash -and
                        $journal.archive_sha256 -ceq ([string]$context.archive_sha256)
                    $currentAnchorHash = Get-Sha256 (Join-Path $privateHome 'anchor.json')
                    if ($guardsReleased -and $journalBound) {
                        if ($privateCode -eq 0 -and $journal.state -eq 'committed' -and $currentAnchorHash -ceq $privateTargetAnchorHash) { $terminal = 'committed' }
                        elseif ($privateCode -ne 0 -and $journal.state -eq 'rolled_back' -and $currentAnchorHash -ceq $privateOldAnchorHash) { $terminal = 'rolled_back' }
                    }
                }
                $stamp = Get-Content -LiteralPath (Join-Path $Stage 'version.json') -Raw -Encoding utf8 | ConvertFrom-Json
                $reason = if ($terminal -eq 'rolled_back') { 'به‌روزرسانی ناموفق بود؛ نسخه و دادهٔ قبلی بازگردانده و سلامت آن تأیید شد.' } elseif ($terminal -eq 'failed') { 'به‌روزرسانی خصوصی تأیید نشد؛ گزارش و قفل‌های بازیابی را بررسی کنید.' } else { '' }
                $result = @{state=$terminal;target_version=$stamp.version;log_path=$logPath;error_fa=$reason;verified=($terminal -eq 'committed');machine_state=$terminal;helper_pid=$PID;attempt_id=$privateAttempt}
                $temp = $ResultPath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
                [IO.File]::WriteAllText($temp,($result | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
                Move-Item -LiteralPath $temp -Destination $ResultPath -Force
                $owner = Get-Content -LiteralPath $channelLock -Raw -Encoding utf8 | ConvertFrom-Json
                if ($owner.pid -ne $PID -or $owner.attempt_id -ne $privateAttempt) { throw 'Private channel lock ownership changed' }
                Remove-Item -LiteralPath $channelLock
            }
        } finally {
            try { $privateMutex.ReleaseMutex() | Out-Null } finally { $privateMutex.Dispose() }
        }
    }
    exit $privateCode
}

# A journal for THIS attempt only: deleted files need snapshots too, and new
# files must be removed on rollback. Never infer success from a process spawn.
$script:snapshotComplete = $false
$script:databaseSnapshotComplete = $false
$script:appStopped = $false
$script:saved = @{}
$script:added = @()
$script:launcherPid = 0
$script:targetVersion = ""
$script:attemptId = [guid]::NewGuid().ToString("N")
if (-not $Port) { $Port = if ($env:VIRA_PORT) { [int]$env:VIRA_PORT } else { 8787 } }

# Published 1.0.9 launches the staged helper without -ResultPath. Recover only
# its known updates/<semver>/<uuid>/payload layout, not an arbitrary ancestor.
# The new backend can then observe the terminal result after this first hop.
if (-not $ResultPath) {
    $payloadDir = New-Object IO.DirectoryInfo -ArgumentList ([IO.Path]::GetFullPath($Stage))
    $attemptDir = $payloadDir.Parent
    $versionDir = if ($attemptDir) { $attemptDir.Parent } else { $null }
    $updatesDir = if ($versionDir) { $versionDir.Parent } else { $null }
    if ($payloadDir.Name -eq "payload" -and $attemptDir.Name -match '^[0-9a-f]{32}$' -and
        $versionDir.Name -match '^\d+\.\d+\.\d+$' -and $updatesDir.Name -eq "updates") {
        $ResultPath = Join-Path $updatesDir.FullName "last-result.json"
    }
}


function Write-Result([string]$State, [string]$Reason = "") {
    if (-not $ResultPath) { return }
    $result = @{ state = $State; target_version = $script:targetVersion; log_path = $logPath;
        error_fa = $Reason; verified = ($State -eq "committed"); machine_state = $State;
        helper_pid = $PID; attempt_id = $script:attemptId }
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

# The new helper carries a hash-verified stdlib DB tool outside {app}.
# Resolve Settings with the OLD runtime for legacy clients, never a guessed DB.
function Invoke-DatabaseTool([string]$Action) {
    $tool = Join-Path $Stage "update_database.py"
    $expected = [string]$updateJson.hashes.'update_database.py'
    if (-not $expected -or -not (Test-Path -LiteralPath $tool) -or (Get-Sha256 $tool) -ne $expected) { throw "database rollback tool missing or unverified" }
    $py = Join-Path $InstallDir "python\python.exe"
    if (-not (Test-Path -LiteralPath $py)) { $py = "python" } # native source fixture
    $argsForTool = @($tool, $Action, "--bundle", (Join-Path $Stage "database-rollback"), "--install-dir", $InstallDir)
    $oldPreference = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $output = (& $py @argsForTool 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($code -ne 0) { throw "database $Action failed: $output" }
    Write-Log "database $Action verified: $($output.Trim())"
}

function Stop-App {
    if ($script:launcherPid) {
        # A failed new server may already have exited its cmd parent. Native
        # stderr in Windows PowerShell must not abort rollback before restore.
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & taskkill.exe /PID $script:launcherPid /T /F 2>&1 | Out-Null
        $ErrorActionPreference = $oldPreference
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
@{ pid = $PID; attempt_id = $script:attemptId } | ConvertTo-Json -Compress |
    Set-Content -Path $lockFile -Encoding ascii

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
    @{ saved = $script:saved; added = $script:added; old_version = $oldStamp; new_version = $newStamp } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $rollback "rollback-journal.json") -Encoding utf8
    $script:snapshotComplete = $true
    Write-Log "snapshot complete -> $rollback"
    Invoke-DatabaseTool "snapshot"
    $script:databaseSnapshotComplete = $true

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
    Remove-Item -LiteralPath $rollback -Recurse -Force -ErrorAction SilentlyContinue
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
            if ($script:databaseSnapshotComplete) { Invoke-DatabaseTool "restore" }
            Start-App
            Wait-Healthy $oldStamp
            Write-Result "rolled_back" "به‌روزرسانی ناموفق بود؛ فایل‌ها و پایگاه‌دادهٔ قبلی بازگردانده و سلامت نسخهٔ قبلی تأیید شد."
            Write-Log "ROLLED BACK — previous files, database and health verified"
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
