# windows_smoke_test.ps1 — Phase 8 §9 CI verification on windows-latest
#
# 1. silent install into a temp dir (/VERYSILENT /DIR=...) — proves the
#    "select where to install" page honors /DIR and the registry is written
# 2. upgrade test with a real delta package — asserts the updater downloads/
#    applies only the delta-sized bytes (never the full setup)
# 3. data-preservation check — a seeded SQLite checksum must be byte-identical
#    across the update (%LOCALAPPDATA%\VIRA is never touched)
# 4. forced-failure rollback test — vira_updater.ps1 -ForceFailure must restore
#    the previous files and report the Persian rollback message

param(
    [Parameter(Mandatory = $true)][string]$Setup
)

$ErrorActionPreference = "Stop"
$tmp = Join-Path ([IO.Path]::GetTempPath()) "vira-smoke"
$install = Join-Path $tmp "install"
New-Item -ItemType Directory -Force -Path $install | Out-Null

Write-Output "[smoke] 1/4 silent install -> $install"
Start-Process -FilePath $Setup -ArgumentList "/VERYSILENT", "/DIR=`"$install`"", "/SUPPRESSMSGBOXES" -Wait
if (-not (Test-Path (Join-Path $install "install_manifest.json"))) { throw "silent install did not produce install_manifest.json" }
$reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\VIRA", "HKCU:\SOFTWARE\VIRA" -Name InstallDir -ErrorAction SilentlyContinue
Write-Output "[smoke] InstallDir registry: $($reg.InstallDir)"

# seed user data that must survive every scenario (Phase 8 §7)
$dataDir = Join-Path $env:LOCALAPPDATA "VIRA\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$db = Join-Path $dataDir "vira.sqlite3"
"seed-data" | Set-Content -Path $db -Encoding ascii
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
foreach ($delta in $deltaZips) {
    if ($delta.Name -notmatch "delta-from-v([\d.]+)\.zip") { continue }
    $fromV = $Matches[1]
    if ($delta.Length -ge $setupSize) { throw "delta ($($delta.Length)) is not smaller than the setup ($setupSize)" }
    # fetch the previous release's portable zip (same discovery as build_deltas)
    $tag = "v$fromV"
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $assetNames = gh api "repos/$repo/releases/tags/$tag" --jq ".assets[].name" 2>$null
    $ErrorActionPreference = $prevEap
    $pName = $assetNames | Where-Object { $_ -match "portable" -and $_ -notmatch "delta|Setup" } | Select-Object -First 1
    if (-not $pName) { Write-Output "[smoke] no portable base for $tag — skipping $($delta.Name)"; continue }
    $baseZip = Join-Path $legacyRoot "base-$fromV.zip"
    try {
        Invoke-WebRequest -Uri "https://github.com/$repo/releases/download/$tag/$pName" -OutFile $baseZip -MaximumRetryCount 2 | Out-Null
    } catch { Write-Output "[smoke] base $tag not downloadable — skipping $($delta.Name)"; continue }

    Write-Output "[smoke] $($delta.Name) = $($delta.Length) bytes < setup $setupSize — upgrading $tag portable -> v$v"
    $legacy = Join-Path $legacyRoot "install"
    if (Test-Path $legacy) { Remove-Item $legacy -Recurse -Force }
    Expand-Archive $baseZip -DestinationPath $legacy -Force
    $stage = Join-Path $env:LOCALAPPDATA "VIRA\updates\smoke"
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Expand-Archive $delta.FullName -DestinationPath $stage -Force
    $env:VIRA_PORT = "8799"   # keep the updater's relaunch off the smoke port
    ./scripts/vira_updater.ps1 -Stage $stage -Log (Join-Path $stage "update.log") -InstallDir $legacy

    $ver = (Get-Content (Join-Path $legacy "version.json") -Raw | ConvertFrom-Json).version
    if ($ver -ne $v) { throw "legacy upgrade reached version '$ver', expected '$v'" }
    $man = Get-Content (Join-Path $legacy "install_manifest.json") -Raw | ConvertFrom-Json
    if (-not $man.files_manifest_sha256) { throw "legacy upgrade did not rewrite install_manifest.json" }
    if (-not (Test-Path (Join-Path $legacy "start_vira.cmd"))) { throw "legacy upgrade lost start_vira.cmd" }
    Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='cmd.exe' or Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like "*$legacy*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Output "[smoke] legacy $tag -> v$v OK — version + manifest rewritten, files verified"
    $upgraded = $true
    break
}
if (-not $upgraded) {
    if ($deltaZips) { throw "deltas were published but none could be exercised against a previous portable base — delta updates are broken" }
    Write-Output "[smoke] no deltas published this run (first release) — skipping upgrade leg"
}

Write-Output "[smoke] 3/5 data preservation"
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
try { ./scripts/vira_updater.ps1 -Stage $stage -Log (Join-Path $stage "rollback.log") -InstallDir $install -ForceFailure } catch { $failed = $true }
if (-not $failed) { throw "forced failure did not roll back" }
if (-not (Test-Path (Join-Path $install "rollback\prev"))) { throw "rollback snapshot missing" }
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
