# Actual updater function AST + real native child, on PowerShell7 AND Desktop5.1.
# This proves stream/exit handling only, NOT a native update or recovery.
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Disposable Windows CI only' }
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'scripts/vira_updater.ps1'),[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Actual updater failed parsing' }
$functions = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-PrivateController'},$true))
if ($functions.Count -ne 1) { throw 'Exactly one actual controller invocation function required' }
. ([scriptblock]::Create($functions[0].Extent.Text))
$work = Join-Path $env:RUNNER_TEMP ('controller-io فارسی ! & ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $work | Out-Null
foreach ($expected in @(0,7)) {
    $script = Join-Path $work ('child ' + $expected + ' ! &.ps1')
    $text = "[Console]::Out.WriteLine('NATIVE_STDOUT'); [Console]::Error.WriteLine('Traceback (most recent call last):'); [Console]::Error.WriteLine('FINAL_NATIVE_STDERR'); exit $expected"
    [IO.File]::WriteAllText($script,$text)
    $global:LASTEXITCODE = 99 # A stale unrelated native exit must not be reused.
    $records = @(& { Invoke-PrivateController 'powershell.exe' @('-NoLogo','-NoProfile','-NonInteractive','-File',$script) } 6>&1)
    $codes = @($records | Where-Object { $_ -is [int] })
    $messages = ($records | Where-Object { $_ -isnot [int] }) -join "`n"
    if ($codes.Count -ne 1 -or $codes[0] -ne $expected) { throw "Native exit code lost or stderr mistaken for failure: $expected" }
    foreach ($sentinel in @('NATIVE_STDOUT','Traceback (most recent call last):','FINAL_NATIVE_STDERR')) {
        if (-not $messages.Contains($sentinel)) { throw "Native stream truncated: $sentinel" }
    }
    if ($ErrorActionPreference -ne 'Stop') { throw 'Caller Stop preference was not restored' }
}
$global:LASTEXITCODE = 0
$caught = $false
try {
    Invoke-PrivateController (Join-Path $work 'NONEXISTENT.exe') @() 6>$null 2>$null
} catch { $caught = $true }
if (-not $caught -or $ErrorActionPreference -ne 'Stop') { throw 'Launch failure reused stale success or changed preference' }
Write-Host 'PASS: actual controller AST preserves stdout/full stderr/native exit and fails closed on launch error; NOT update acceptance'
