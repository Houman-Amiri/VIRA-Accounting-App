# External Phase3 driver: actual selected-path Inno + actual app; no QA hooks.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Candidate,
      [Parameter(Mandatory=$true)][string]$SourceAudit,
      [string]$TransactionTarget = '', [string]$TransactionAudit = '',
      [ValidateSet('phase3-installed','phase3-native-transaction')][string]$ReportsName = 'phase3-installed')
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Private disposable Windows CI only' }
$reports = Join-Path $PWD ('reports/' + $ReportsName)
if ([bool]$TransactionTarget -ne [bool]$TransactionAudit) { throw 'Both independent native transaction inputs required' }
New-Item -ItemType Directory -Force $reports | Out-Null
$work = Join-Path $env:RUNNER_TEMP ('phase3-installed-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $work | Out-Null
$payload = Join-Path $work 'VIRA payload فارسی ! &'
$profile = Join-Path $work 'کاربر خصوصی ! & Local AppData'
$selected = Join-Path $work 'مسیر انتخابی نصب ! & VIRA'
New-Item -ItemType Directory $profile | Out-Null
& ./scripts/stage_app_payload.ps1 -Version '0.0.0-private-unicode-proof' -OutDir $payload
if ($LASTEXITCODE -ne 0) { throw 'Private locked app staging failed' }
New-Item -ItemType Directory -Force (Join-Path $payload 'native') | Out-Null
Copy-Item -LiteralPath $Candidate -Destination (Join-Path $payload 'native/pdf') -Recurse
Copy-Item -LiteralPath $SourceAudit -Destination (Join-Path $payload 'native/pdf/source-audit.json')
& ./scripts/pdf_unicode_process_manifest.ps1 -AppRoot $payload
if ($LASTEXITCODE -ne 0) { throw 'Private ACP manifest failed' }
Install-Module ps2exe -Force -Scope CurrentUser -ErrorAction Stop
Import-Module ps2exe -ErrorAction Stop
Invoke-ps2exe -inputFile scripts/vira_updater.ps1 -outputFile (Join-Path $payload 'vira-updater.exe') -noConsole:$false
if (-not (Test-Path -LiteralPath (Join-Path $payload 'vira-updater.exe'))) { throw 'Actual compiled helper missing' }
$targetHelper = ''
if ($TransactionTarget) {
    $targetHelper = Join-Path $work 'independently-compiled-target-updater.exe'
    Invoke-ps2exe -inputFile scripts/vira_updater.ps1 -outputFile $targetHelper -noConsole:$false
    if (-not (Test-Path -LiteralPath $targetHelper) -or (Get-FileHash -LiteralPath $targetHelper).Hash -eq (Get-FileHash -LiteralPath (Join-Path $payload 'vira-updater.exe')).Hash) { throw 'Distinct actual target helper required; no fake PE edits' }
}

$stampPath = Join-Path $payload 'version.json'
$stamp = Get-Content -LiteralPath $stampPath -Raw -Encoding utf8 | ConvertFrom-Json
$stamp.version = '99.30.0'
[IO.File]::WriteAllText($stampPath,($stamp | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
uv run python scripts/build_manifest.py $payload
if ($LASTEXITCODE -ne 0) { throw 'Final private manifest failed' }
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$anchor = Join-Path $work 'independent-anchor.json'
$pin = @{schema=2;role='PRIVATE_SOURCE_INSTALLED_ANCHOR';version='99.30.0';port=$port;no_browser=$true;
    manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $payload 'install_manifest.json')).Hash.ToLowerInvariant();
    inventory_sha256=(Get-FileHash -LiteralPath (Join-Path $payload 'native/pdf/runtime-inventory.json')).Hash.ToLowerInvariant();
    source_audit_sha256=(Get-FileHash -LiteralPath $SourceAudit).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText($anchor,($pin | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc)) { throw 'Actual Inno compiler required' }
$compile = (& $iscc '/DPrivateSourceCI' "/DPrivateSourceAnchor=$anchor" "/DPrivateSourceProfile=$profile" '/DAppVersion=99.30.0' "/DAppSource=$payload" "/O$work/setup" installer/vira.iss 2>&1 | Out-String)
$code = $LASTEXITCODE
[IO.File]::WriteAllText((Join-Path $reports 'inno-compile.log'),$compile)
Write-Host $compile
if ($code -ne 0) { throw 'Real versioned private Inno compilation failed' }
$ordinary = Join-Path $profile 'VIRA/data/ordinary-sentinel.txt'
New-Item -ItemType Directory -Force (Split-Path $ordinary) | Out-Null
[IO.File]::WriteAllText($ordinary,'OWNED SYNTHETIC SENTINEL; NEVER BUSINESS DATA')
$before = (Get-FileHash -LiteralPath $ordinary).Hash
$previous = $env:LOCALAPPDATA
try {
    $env:LOCALAPPDATA = $profile
    $setup = Join-Path $work 'setup/VIRA-Setup-99.30.0.exe'
    $process = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/TASKS=""',('/DIR="'+$selected+'"')) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw 'Actual Source21 Inno install failed' }
    $installedPin = Join-Path $profile 'VIRA/private-native-installed/anchor.json'
    if ((Get-FileHash -LiteralPath $installedPin).Hash -ne (Get-FileHash -LiteralPath $anchor).Hash) { throw 'Independent anchor changed at install' }
    $inputFiles = @(Get-ChildItem -LiteralPath $payload -Recurse -File)
    if (@(Get-ChildItem -LiteralPath $selected -Recurse -File).Count -ne $inputFiles.Count) { throw 'Actual installed payload file set differs' }
    foreach ($file in $inputFiles) {
        $name = [IO.Path]::GetRelativePath($payload,$file.FullName)
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $selected $name)).Hash) { throw 'Installed Source21 bytes differ' }
    }
    $probeArgs = @('--app-root',$selected,'--profile',$profile,'--reports',$reports,'--audit',$SourceAudit)
    if ($TransactionTarget) { $probeArgs += @('--transaction-target',$TransactionTarget,'--transaction-audit',$TransactionAudit,'--transaction-helper',$targetHelper) }
    uv run python scripts/phase3_installed_probe.py @probeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Actual installed Source21 app proof failed' }
    if ((Get-FileHash -LiteralPath $ordinary).Hash -ne $before) { throw 'Ordinary sentinel changed' }
} finally { $env:LOCALAPPDATA = $previous }
