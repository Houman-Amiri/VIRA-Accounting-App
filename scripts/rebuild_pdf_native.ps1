# SPDX-License-Identifier: MIT
# Copyright (c) 2026 VIRA contributors
# Native-only derivative of the scoped MIT source_pdf_build.ps1 recipe.
# No app checkout, Node, uv, staging, installer or database is used.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [string]$OverlayPorts = "",
    [switch]$PlanOnly
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (-not $IsWindows -or $PSVersionTable.PSVersion.Major -lt 7) { throw "Windows x64 and PowerShell 7 required" }
if (-not [Environment]::Is64BitProcess) { throw "x64 PowerShell required" }
$sourceRoot = Split-Path -Parent $PSScriptRoot
$profile = Join-Path $sourceRoot "native/pdf-source"
$manifest = Get-Content (Join-Path $profile "vcpkg.json") -Raw -Encoding utf8 | ConvertFrom-Json
$pin = $manifest.'builtin-baseline'
if ($pin -ne "a5f736224e85b32e25a8ffc52562333180396642") { throw "unexpected vcpkg baseline; explicit recipe review required" }
foreach ($name in @("x64-vira-pdf.cmake", "x64-vira-pdf-host.cmake")) {
    if (-not (Test-Path -LiteralPath (Join-Path $profile "triplets/$name") -PathType Leaf)) { throw "missing triplet: $name" }
}
if (-not [IO.Path]::IsPathFullyQualified($WorkDir)) { throw "absolute, NEW work directory required" }
$work = [IO.Path]::GetFullPath($WorkDir)
if (Test-Path -LiteralPath $work) { throw "refusing to overwrite any existing work directory" }
if ($OverlayPorts -and -not (Test-Path -LiteralPath $OverlayPorts -PathType Container)) { throw "overlay ports directory not found" }
$plan = [ordered]@{
    schema = 1; vcpkg_commit = $pin; target_triplet = "x64-vira-pdf"; host_triplet = "x64-vira-pdf-host"
    binary_cache = "DISABLED"; application_required = $false; distribution_status = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
    work_directory = $work; overlay_ports = $OverlayPorts; plan_only = [bool]$PlanOnly
}
if ($PlanOnly) { $plan | ConvertTo-Json -Depth 5; return }
Get-Command git -ErrorAction Stop | Out-Null
# mkdir without -Force fails if another process creates this directory first.
New-Item -ItemType Directory -Path $work | Out-Null
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText((Join-Path $work "DO_NOT_DISTRIBUTE.txt"), $plan.distribution_status + "`n", $utf8)
[IO.File]::WriteAllText((Join-Path $work "rebuild-plan.json"), ($plan | ConvertTo-Json -Depth 5) + "`n", $utf8)
$vcpkg = Join-Path $work "vcpkg"
& git clone --no-checkout https://github.com/microsoft/vcpkg.git $vcpkg
if ($LASTEXITCODE -ne 0) { throw "vcpkg clone failed" }
& git -C $vcpkg checkout --detach $pin
if ($LASTEXITCODE -ne 0) { throw "vcpkg checkout failed" }
$actualPin = & git -C $vcpkg rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualPin -ne $pin) { throw "vcpkg pin mismatch" }
& (Join-Path $vcpkg "bootstrap-vcpkg.bat") -disableMetrics
if ($LASTEXITCODE -ne 0) { throw "vcpkg bootstrap failed" }
$env:VCPKG_ROOT = $vcpkg
$env:VCPKG_BINARY_SOURCES = "clear"
$env:VCPKG_MAX_CONCURRENCY = "4"
$installed = Join-Path $work "installed"
$arguments = @("install", "--triplet", "x64-vira-pdf", "--host-triplet", "x64-vira-pdf-host",
    "--x-manifest-root=$profile", "--x-install-root=$installed", "--overlay-triplets=$profile/triplets",
    "--binarysource=clear", "--no-print-usage")
if ($OverlayPorts) { $arguments += "--overlay-ports=$([IO.Path]::GetFullPath($OverlayPorts))" }
& (Join-Path $vcpkg "vcpkg.exe") @arguments 2>&1 | Tee-Object (Join-Path $work "build.log")
if ($LASTEXITCODE -ne 0) { throw "native source build failed; see build.log" }
$dlls = @(Get-ChildItem -LiteralPath (Join-Path $installed "x64-vira-pdf/bin") -Filter *.dll -File)
if ($dlls.Count -eq 0) { throw "no native DLLs produced" }
$result = [ordered]@{
    schema = 1; vcpkg_commit = $pin; target_triplet = "x64-vira-pdf"; host_triplet = "x64-vira-pdf-host"
    application_required = $false; binary_cache = "DISABLED"; dll_count_before_closure_selection = $dlls.Count
    distribution_status = $plan.distribution_status
    dlls = @($dlls | Sort-Object Name | ForEach-Object { @{ name = $_.Name; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() } })
}
[IO.File]::WriteAllText((Join-Path $work "rebuild-result.json"), ($result | ConvertTo-Json -Depth 8) + "`n", $utf8)
Write-Host "PASS: native-only source compilation. No application installation or distribution approval."
