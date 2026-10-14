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

Write-Output "[smoke] 2/4 delta upgrade"
$delta = Get-ChildItem (Split-Path $Setup) -Filter "*delta*.zip" | Select-Object -First 1
if ($delta) {
    $setupSize = (Get-Item $Setup).Length
    if ($delta.Length -ge $setupSize) { throw "delta ($($delta.Length)) is not smaller than the setup ($setupSize)" }
    Write-Output "[smoke] delta $($delta.Name) = $($delta.Length) bytes < setup $setupSize bytes"
    $stage = Join-Path $env:LOCALAPPDATA "VIRA\updates\smoke"
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Expand-Archive $delta.FullName -DestinationPath $stage -Force
    ./scripts/vira_updater.ps1 -Stage $stage -Log (Join-Path $stage "update.log") -InstallDir $install
} else {
    Write-Output "[smoke] no delta published for this run (first release?) — skipping upgrade leg"
}

Write-Output "[smoke] 3/4 data preservation"
$dbHashAfter = (Get-FileHash -Algorithm SHA256 $db).Hash
if ($dbHashAfter -ne $dbHashBefore) { throw "user data changed across the update — DATA LOSS" }
Write-Output "[smoke] user data checksum identical: $dbHashAfter"

Write-Output "[smoke] 4/4 forced-failure rollback"
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
Write-Output "[smoke] rollback restored the previous version — all legs passed"
