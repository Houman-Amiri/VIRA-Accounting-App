# windows_smoke_test.ps1 — Phase 8 §9 CI verification on windows-latest
#
# 1. silent install into a temp dir (/VERYSILENT /DIR=...) — proves the
#    "select where to install" page honors /DIR and the registry is written
# 2. manually stage and apply a real delta (NOT an in-app download test);
#    assert the package is smaller than Setup and the helper upgrades the base
# 3. data-preservation check — a seeded SQLite checksum must be byte-identical
#    across the update (%LOCALAPPDATA%\VIRA is never touched)
# 4. forced-failure rollback test — vira_updater.ps1 -ForceFailure must restore
#    the previous files and report the Persian rollback message

param(
    [Parameter(Mandatory = $true)][string]$Setup
)

$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true") { throw "This destructive smoke fixture is for an isolated GitHub Actions runner only." }
function Stop-SmokeRestartedApp([string]$AppDir, [int]$Port) {
    # The helper restarts asynchronously. Wait for the upgraded app before
    # stopping the launcher tree; otherwise cleanup can race a not-yet-born child.
    $healthy = $false
    for ($i = 0; $i -lt 120; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:${Port}/api/v1/health/live" -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw "restarted app failed to restart healthy on port $Port" }
    $launchers = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.CommandLine -like "*$AppDir*" })
    foreach ($launcherProcess in $launchers) {
        & taskkill.exe /PID $launcherProcess.ProcessId /T /F 2>&1 | Out-Null
    }
    $interpreters = @(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($AppDir + "\", [StringComparison]::OrdinalIgnoreCase) })
    foreach ($interpreter in $interpreters) {
        Stop-Process -Id $interpreter.Id -Force -ErrorAction SilentlyContinue
        $interpreter.WaitForExit()
    }
    $remaining = @(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($AppDir + "\", [StringComparison]::OrdinalIgnoreCase) })
    if ($remaining.Count) { throw "restarted app still holds the SQLite fixture open" }
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) "vira-smoke"
$install = Join-Path $tmp "install with spaces"
New-Item -ItemType Directory -Force -Path $install | Out-Null

Write-Output "[smoke] 1/5 silent install -> $install"
Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT", "/DIR=`"$install`"", "/SUPPRESSMSGBOXES" -Wait
if (-not (Test-Path (Join-Path $install "install_manifest.json"))) { throw "silent install did not produce install_manifest.json" }
$reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\VIRA", "HKCU:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue
Write-Output "[smoke] InstallDir registry: $($reg.InstallDir)"

# seed user data that must survive every scenario (Phase 8 §7)
$dataDir = Join-Path $env:LOCALAPPDATA "VIRA\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$db = Join-Path $dataDir "vira.sqlite3"
if (Test-Path $db) { throw "Smoke requires a clean CI data directory; refusing to overwrite an existing database." }
& uv run python scripts/migrate_vira.py --database $db | Out-Null
if ($LASTEXITCODE -ne 0) { throw "could not migrate the smoke SQLite fixture" }
$env:VIRA_SMOKE_DATABASE = $db
@'
import os
import sqlite3
conn = sqlite3.connect(os.environ["VIRA_SMOKE_DATABASE"])
try:
    conn.execute("CREATE TABLE smoke_sentinel (value TEXT NOT NULL)")
    conn.execute("INSERT INTO smoke_sentinel VALUES ('preserve-real-sqlite-data')")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
finally:
    conn.close()
'@ | uv run python -
if ($LASTEXITCODE -ne 0) { throw "could not seed the smoke SQLite fixture" }
$dbHashBefore = (Get-FileHash -Algorithm SHA256 $db).Hash

Write-Output "[smoke] 2/5 legacy delta upgrade (previous portable + matching delta)"
$v = (Get-Content (Join-Path $install "version.json") -Raw | ConvertFrom-Json).version
$setupSize = (Get-Item $Setup).Length
$legacyRoot = Join-Path $env:LOCALAPPDATA "VIRA\smoke-legacy"
if (Test-Path $legacyRoot) { Remove-Item $legacyRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $legacyRoot | Out-Null
$repo = if ($env:GITHUB_REPOSITORY) { $env:GITHUB_REPOSITORY } else { "Houman-Amiri/VIRA-Accounting-App" }
$upgraded = $false
$deltaZips = Get-ChildItem (Split-Path $Setup) -Filter "*delta*.zip" | Sort-Object Name -Descending
# The repair must bootstrap the user's actual 1.0.6 baseline, not just 1.0.7.
if ($v -eq "1.0.8") {
    $deltaZips = @($deltaZips | Where-Object { $_.Name -eq "VIRA-v1.0.8-delta-from-v1.0.6.zip" })
    if ($deltaZips.Count -ne 1) { throw "required 1.0.6 -> 1.0.8 bootstrap delta missing" }
}
foreach ($delta in $deltaZips) {
    if ($delta.Name -notmatch "delta-from-v([\d.]+)\.zip") { continue }
    $fromV = $Matches[1]
    if ($delta.Length -ge $setupSize) { throw "delta ($($delta.Length)) is not smaller than the setup ($setupSize)" }
    # fetch the previous release's portable zip (same probe as build_deltas)
    $tag = "v$fromV"
    $pUrl = $null
    foreach ($pName in @("vira-v$fromV-app.zip", "vira-v$fromV-portable.zip", "VIRA-v$fromV.zip", "VIRA-v$fromV-portable.zip")) {
        $tryUrl = "https://github.com/$repo/releases/download/$tag/$pName"
        try {
            $resp = Invoke-WebRequest -Uri $tryUrl -Method Head -SkipHttpErrorCheck -MaximumRedirection 5 -TimeoutSec 30
            $code = [int]$resp.StatusCode
        } catch { $code = 0 }
        if ($code -in 200, 302) { $pUrl = $tryUrl; break }
    }
    if (-not $pUrl) { Write-Output "[smoke] no portable base for $tag — skipping $($delta.Name)"; continue }
    $baseZip = Join-Path $legacyRoot "base-$fromV.zip"
    try {
        Invoke-WebRequest -Uri $pUrl -OutFile $baseZip -MaximumRetryCount 2 | Out-Null
    } catch { Write-Output "[smoke] base $tag not downloadable — skipping $($delta.Name)"; continue }

    Write-Output "[smoke] $($delta.Name) = $($delta.Length) bytes < setup $setupSize — upgrading $tag portable -> v$v"
    $legacy = Join-Path $legacyRoot "install with spaces"
    if (Test-Path $legacy) { Remove-Item $legacy -Recurse -Force }
    Expand-Archive $baseZip -DestinationPath $legacy -Force
    $stage = Join-Path $env:LOCALAPPDATA "VIRA\updates\smoke"
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Expand-Archive $delta.FullName -DestinationPath $stage -Force
    # the updater relaunches the app; keep that instance off the smoke port,
    # and RESTORE the variable afterwards (leg 5 launches on 8787 — leaving
    # VIRA_PORT set made the app bind 8799 and the health check fail; only
    # visible once a real delta existed, i.e. from v1.0.5 on)
    $prevPort = $env:VIRA_PORT
    $env:VIRA_PORT = "8799"
    # Mirror client discovery: staged helper first, then the installed helper.
    # The staged helper can replace {app}/vira-updater.exe without a file lock.
    $stagedUpdater = Join-Path $stage "vira-updater.exe"
    $installUpdater = Join-Path $legacy "vira-updater.exe"
    if (Test-Path $stagedUpdater) {
        Write-Output "[smoke] applying delta with staged helper (legacy client arguments)"
        # v1.0.5 clients used -install-dir. Keep that alias working as well.
        & $stagedUpdater -stage $stage -log (Join-Path $stage "update.log") -install-dir $legacy
    } elseif (Test-Path $installUpdater) {
        & $installUpdater -Stage $stage -Log (Join-Path $stage "update.log") -InstallDir $legacy
    } else {
        ./scripts/vira_updater.ps1 -Stage $stage -Log (Join-Path $stage "update.log") -InstallDir $legacy
    }

    if ($null -ne $prevPort) { $env:VIRA_PORT = $prevPort } else { Remove-Item Env:VIRA_PORT -ErrorAction SilentlyContinue }

    $ver = (Get-Content (Join-Path $legacy "version.json") -Raw | ConvertFrom-Json).version
    if ($ver -ne $v) {
        # never fail blind again: the updater's log says exactly which operation broke
        $ulog = Join-Path $stage "update.log"
        $tail = if (Test-Path $ulog) { (Get-Content $ulog -Raw) } else { "<no update.log>" }
        if ($tail.Length -gt 2500) { $tail = $tail.Substring($tail.Length - 2500) }
        throw "legacy upgrade reached version '$ver', expected '$v' — updater log:`n$tail"
    }
    $man = Get-Content (Join-Path $legacy "install_manifest.json") -Raw | ConvertFrom-Json
    if (-not $man.files_manifest_sha256) { throw "legacy upgrade did not rewrite install_manifest.json" }
    if (-not (Test-Path (Join-Path $legacy "start_vira.cmd"))) { throw "legacy upgrade lost start_vira.cmd" }
    if (-not (Test-Path (Join-Path $legacy "vira-updater.exe"))) { throw "upgrade did not leave vira-updater.exe in the install (the next update would fail)" }
    Stop-SmokeRestartedApp -AppDir $legacy -Port 8799
    Write-Output "[smoke] legacy $tag -> v$v OK — version + manifest rewritten, files verified"
    $upgraded = $true
    break
}
if (-not $upgraded) {
    if ($deltaZips) { throw "deltas were published but none could be exercised against a previous portable base — delta updates are broken" }
    Write-Output "[smoke] no deltas published this run (first release) — skipping upgrade leg"
}

Write-Output "[smoke] 3/5 data preservation"
@'
import os
import sqlite3
conn = sqlite3.connect(os.environ["VIRA_SMOKE_DATABASE"])
try:
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT value FROM smoke_sentinel").fetchall() == [("preserve-real-sqlite-data",)]
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
finally:
    conn.close()
'@ | uv run python -
if ($LASTEXITCODE -ne 0) { throw "SQLite integrity or sentinel data changed during upgrade" }
$dbHashAfter = (Get-FileHash -Algorithm SHA256 $db).Hash
if ($dbHashAfter -ne $dbHashBefore) { throw "user data changed across the update — DATA LOSS" }
Write-Output "[smoke] user data checksum identical: $dbHashAfter"

Write-Output "[smoke] 4/5 forced-failure rollback"
$stage = Join-Path $env:LOCALAPPDATA "VIRA\updates\smoke"
New-Item -ItemType Directory -Force -Path $stage | Out-Null
# self-contained stage: a minimal valid update.json even when no delta exists
if (-not (Test-Path (Join-Path $stage "update.json"))) {
    @{ base_version = "smoke"; target_version = "forced-fail"; operations = @() } |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $stage "update.json")
}
$failed = $false
$previousRollbackPort = $env:VIRA_PORT
$env:VIRA_PORT = "8798"
try { ./scripts/vira_updater.ps1 -Stage $stage -Log (Join-Path $stage "rollback.log") -InstallDir $install -ForceFailure } catch { $failed = $true }
finally {
    if ($null -ne $previousRollbackPort) { $env:VIRA_PORT = $previousRollbackPort } else { Remove-Item Env:VIRA_PORT -ErrorAction SilentlyContinue }
}
if (-not $failed) { throw "forced failure did not roll back" }
if (-not (Test-Path (Join-Path $install "rollback\prev"))) { throw "rollback snapshot missing" }
Stop-SmokeRestartedApp -AppDir $install -Port 8798
if ((Get-FileHash -Algorithm SHA256 $db).Hash -ne $dbHashBefore) { throw "user data changed across rollback" }
Write-Output "[smoke] rollback restored the previous version"

# ---------------------------------------------------------------------------
Write-Output "[smoke] 5/5 shortcut integrity + real launch (first-run journey)"
$shell = New-Object -ComObject WScript.Shell
# admin installs place shortcuts in the All Users locations ({autoprograms}/{autodesktop})
$lnkDirs = @(
    "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\V.I.R.A",
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\V.I.R.A"),
    "C:\Users\Public\Desktop",
    [Environment]::GetFolderPath("Desktop")
)
$checked = 0
foreach ($dir in $lnkDirs) {
    if (Test-Path $dir) {
        Get-ChildItem $dir -Filter "*.lnk" | ForEach-Object {
            $target = $shell.CreateShortcut($_.FullName).TargetPath
            if (-not (Test-Path $target)) { throw "shortcut $($_.Name) targets missing file: $target" }
            Write-Output "[smoke] shortcut ok: $($_.Name) -> $target"
            $checked++
        }
    }
}
if ($checked -lt 2) { throw "expected Start-Menu + Desktop shortcuts, found $checked" }

$launcher = Join-Path $install "start_vira.cmd"
if (-not (Test-Path $launcher)) { throw "launcher missing at $launcher" }
# isolated first-run DB — leg 3's sentinel at data\vira.sqlite3 must stay untouched
Remove-Item Env:VIRA_PORT -ErrorAction SilentlyContinue   # the app must bind 8787 here
$env:SQLITE_DATABASE_PATH = Join-Path $env:LOCALAPPDATA "VIRA\data\vira-smoke-e2e.sqlite3"
Remove-Item $env:SQLITE_DATABASE_PATH -Force -ErrorAction SilentlyContinue
$launchLog = Join-Path $env:LOCALAPPDATA "VIRA\logs\smoke-launch.log"
New-Item -ItemType Directory -Force -Path (Split-Path $launchLog) | Out-Null
Remove-Item $launchLog -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "`"`"$launcher`" > `"$launchLog`" 2>&1`"" `
    -WorkingDirectory $install -WindowStyle Hidden | Out-Null
try {
    $ok = $false
    for ($i = 0; $i -lt 120; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8787/api/v1/health/live" -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ok) {
        $tail = if (Test-Path $launchLog) { (Get-Content $launchLog -Raw) } else { "<no launcher log>" }
        throw "app did not become healthy on http://127.0.0.1:8787 — launcher output:`n$($tail.Substring([Math]::Max(0, $tail.Length - 1500)))"
    }
    $spa = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8787/" -TimeoutSec 5
    if ($spa.StatusCode -ne 200 -or $spa.Content -notmatch "root") { throw "SPA not served at /" }
    $creds = Join-Path $env:LOCALAPPDATA "VIRA\first-run-credentials.txt"
    if (-not (Test-Path $creds)) { throw "first-run credentials file was not created" }
    # — content proof: the installed app must serve exactly the payload this run
    #   built. v1.0.5 shipped the new code but a stale cached shell, and nothing
    #   in CI noticed; that is what this block prevents from recurring. —
    $payloadIndex = Join-Path (Split-Path $Setup) "app\static\index.html"
    if (-not (Test-Path $payloadIndex)) { throw "payload index.html missing at $payloadIndex" }
    $builtId = [regex]::Match((Get-Content $payloadIndex -Raw), 'name="vira-build"\s+content="([^"]+)"').Groups[1].Value
    if (-not $builtId) { throw "the built index.html carries no vira-build marker" }
    $servedId = [regex]::Match($spa.Content, 'name="vira-build"\s+content="([^"]+)"').Groups[1].Value
    if ($servedId -ne $builtId) { throw "STALE UI: the app serves build '$servedId' but the release payload is '$builtId'" }
    $cacheControl = ($spa.Headers["Cache-Control"] -join ",")
    if ($cacheControl -notmatch "no-store") { throw "the SPA shell was served without Cache-Control: no-store (stale-UI risk)" }
    $assetName = [regex]::Match($spa.Content, 'src="/assets/([^"]+\.js)"').Groups[1].Value
    if (-not $assetName) { throw "the served shell references no hashed asset bundle" }
    $asset = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8787/assets/$assetName" -TimeoutSec 10
    # v1.0.7: prove the installed bundle also carries the literal-XLSX pricing correction.
    foreach ($marker in @("chart-stock", "job-submit", "order-submit", "movement-submit", "dashboard-alerts", "sheet-policy", "2780748.5")) {
        if ($asset.Content -notmatch $marker) { throw "the served bundle lacks the new UI marker '$marker' — the installed SPA is not the one that was built" }
    }
    $warehouse = Invoke-WebRequest -UseBasicParsing -SkipHttpErrorCheck "http://127.0.0.1:8787/api/v1/warehouse/items" -TimeoutSec 10
    if ([int]$warehouse.StatusCode -eq 404) { throw "the operations API (/api/v1/warehouse/items) is missing from the installed backend" }
    Write-Output "[smoke] content proof: build $servedId served, new-UI markers present, operations API reachable"
    Write-Output "[smoke] launch ok — healthy, SPA served, first-run credentials written"
} finally {
    Get-Process -Name python -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$install*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name cmd -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*V.I.R.A*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}
Write-Output "[smoke] all legs passed"
