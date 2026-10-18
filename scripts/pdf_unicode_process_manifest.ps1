# Private Windows QA only; NOT part of the native-build MIT grant or normal staging.
# Preserve the CPython PE manifest and add Windows' process-level UTF-8 ACP.
# -X utf8 changes Python codecs, NOT Win32/CRT fopen's active code page.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$AppRoot)
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true") { throw "Private isolated Windows CI only" }
$app = [IO.Path]::GetFullPath($AppRoot)
$runner = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\') + '\'
if (-not $app.StartsWith($runner, [StringComparison]::OrdinalIgnoreCase)) { throw "Only a private runner TEMP payload may be changed" }
$version = Get-Content (Join-Path $app "version.json") -Raw | ConvertFrom-Json
if ($version.version -ne "0.0.0-private-unicode-proof") { throw "Not a private Unicode QA payload" }
$exe = Join-Path $app "python/python.exe"
$work = Join-Path (Split-Path -Parent $app) "process-utf8-manifest"
New-Item -ItemType Directory -Path $work | Out-Null
$tool = Get-ChildItem "${env:ProgramFiles(x86)}/Windows Kits/10/bin/*/x64/mt.exe" | Sort-Object FullName | Select-Object -Last 1
if (-not $tool) { throw "Windows SDK manifest tool not found; no ACP fallback allowed" }
$original = Join-Path $work "original.manifest"
$modified = Join-Path $work "utf8.manifest"
$verified = Join-Path $work "extracted-after.manifest"
$before = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLowerInvariant()
$originalSignature = (Get-AuthenticodeSignature $exe).Status.ToString()
& $tool.FullName -nologo "-inputresource:$exe;#1" "-out:$original"
if ($LASTEXITCODE -ne 0) { throw "Cannot extract original CPython manifest" }
[xml]$xml = Get-Content $original -Raw
$ns = "urn:schemas-microsoft-com:asm.v3"
$acpns = "http://schemas.microsoft.com/SMI/2019/WindowsSettings"
if ($xml.GetElementsByTagName("activeCodePage", $acpns).Count -ne 0) { throw "Unexpected existing activeCodePage; review instead of overriding it" }
$settings = @($xml.GetElementsByTagName("windowsSettings", $ns))
if ($settings.Count -gt 1) { throw "Ambiguous original Windows settings" }
if ($settings.Count -eq 0) {
    $application = $xml.CreateElement("application", $ns)
    $window = $xml.CreateElement("windowsSettings", $ns)
    [void]$application.AppendChild($window)
    [void]$xml.DocumentElement.AppendChild($application)
} else { $window = $settings[0] }
$codepage = $xml.CreateElement("activeCodePage", $acpns)
$codepage.InnerText = "UTF-8"
[void]$window.AppendChild($codepage)
$xml.Save($modified)
& $tool.FullName -nologo -manifest $modified "-outputresource:$exe;#1"
if ($LASTEXITCODE -ne 0) { throw "Cannot embed private UTF-8 process manifest" }
& $tool.FullName -nologo "-inputresource:$exe;#1" "-out:$verified"
if ($LASTEXITCODE -ne 0) { throw "Cannot re-extract modified process manifest" }
[xml]$actual = Get-Content $verified -Raw
$nodes = @($actual.GetElementsByTagName("activeCodePage", $acpns))
if ($nodes.Count -ne 1 -or $nodes[0].InnerText -ne "UTF-8") { throw "Embedded UTF-8 process setting missing" }
$after = (Get-FileHash -Algorithm SHA256 $exe).Hash.ToLowerInvariant()
if ($before -eq $after) { throw "Private process manifest must change the executable hash" }
@{
    schema = 1
    private_only = $true
    normal_payload_staging_changed = $false
    executable = "python/python.exe"
    executable_sha256_before = $before
    executable_sha256_after = $after
    original_signature_status = $originalSignature
    modified_signature_status = (Get-AuthenticodeSignature $exe).Status.ToString()
    tool = @{ name = "mt.exe"; version = $tool.VersionInfo.FileVersion; sha256 = (Get-FileHash -Algorithm SHA256 $tool.FullName).Hash.ToLowerInvariant() }
    original_manifest = [IO.File]::ReadAllText($original)
    embedded_manifest = [IO.File]::ReadAllText($verified)
    minimum_windows_for_active_code_page = "Windows 10 version 1903; actual worker must independently require GetACP() == 65001"
    python_executable_is_unmodified_upstream_binary = $false
    release_or_redistribution_approval = $false
} | ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 (Join-Path $app "private-utf8-process-manifest.json")
# Restamp this PRIVATE baseline only, then require both workers to leave it intact.
uv run python -X utf8 scripts/build_manifest.py $app
if ($LASTEXITCODE -ne 0) { throw "Private modified-payload manifest generation failed" }
Write-Host "Private CPython process manifest embedded; no installer or normal staging changes."
