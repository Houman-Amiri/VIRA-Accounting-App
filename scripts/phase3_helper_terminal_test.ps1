# Synthetic receipt/lock fault tests against the ACTUAL updater AST block.
# No compiled helper, interpreter, native DLL, installer or app is executed.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Disposable Windows CI only' }
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'scripts/vira_updater.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Actual updater failed parsing' }
$functions = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-Sha256'},$true))
if ($functions.Count -ne 1) { throw 'Exactly one actual SHA function required' }
. ([scriptblock]::Create($functions[0].Extent.Text))
$private = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.IfStatementAst] -and $n.Clauses[0].Item1.Extent.Text -eq '$PrivateSourceTransaction'},$true))
if ($private.Count -ne 1) { throw 'Exactly one explicit private branch required' }
$outer = @($private[0].Clauses[0].Item2.Statements | Where-Object { $_ -is [Management.Automation.Language.TryStatementAst] })
if ($outer.Count -ne 1) { throw 'Exactly one private transaction try/finally required' }
$publication = $outer[0].Finally.Statements[0]
if ($publication -isnot [Management.Automation.Language.TryStatementAst]) { throw 'Expected actual publication try/finally' }
$text = $publication.Body.Extent.Text
$body = [scriptblock]::Create($text.Substring(1,$text.Length-2))
$work = Join-Path $env:RUNNER_TEMP ('phase3-terminal-synthetic-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $work | Out-Null
$cases = @('commit','rollback','commit-exit-error','rollback-exit-zero','archive-drift','old-anchor-drift','target-anchor-drift','native-guard','write-guard','foreign-owner','missing-journal','malformed-journal','current-anchor-drift','journal-schema')
foreach ($case in $cases) {
    $base = Join-Path $work $case
    $privateHome = Join-Path $base 'private home فارسی ! &'
    $Stage = Join-Path $base 'payload'
    $attempt = Join-Path $base 'attempt'
    New-Item -ItemType Directory -Force $privateHome,$Stage,$attempt,(Join-Path $privateHome 'state/data/updates') | Out-Null
    $old = Join-Path $base 'old.json'
    $target = Join-Path $base 'target.json'
    [IO.File]::WriteAllText($old,'{"version":"99.30.0"}')
    [IO.File]::WriteAllText($target,'{"version":"99.30.1"}')
    Copy-Item -LiteralPath $target -Destination (Join-Path $privateHome 'anchor.json')
    Copy-Item -LiteralPath $target -Destination (Join-Path $Stage 'version.json')
    $privateOldAnchorHash = Get-Sha256 $old
    $privateTargetAnchorHash = Get-Sha256 $target
    $context = @{attempt=$attempt;archive_sha256=('a'*64)}
    $channelLock = Join-Path $privateHome '.native-channel.lock'
    $privateAttempt = 'current-synthetic-attempt'
    @{pid=$PID;attempt_id=$privateAttempt} | ConvertTo-Json | Set-Content -LiteralPath $channelLock -Encoding utf8
    $ResultPath = Join-Path $privateHome 'state/data/updates/last-result.json'
    $logPath = Join-Path $Stage 'update.log'
    $channelOwned = $true
    $privateCode = 0
    $journal = @{schema=1;role='PRIVATE_NATIVE_TRANSACTION_JOURNAL';state='committed';old_anchor_sha256=$privateOldAnchorHash;target_anchor_sha256=$privateTargetAnchorHash;archive_sha256=$context.archive_sha256}
    $expected = 'failed'
    $throws = $false
    switch ($case) {
        'commit' { $expected='committed' }
        'rollback' { $privateCode=1; $journal.state='rolled_back'; Copy-Item -LiteralPath $old -Destination (Join-Path $privateHome 'anchor.json'); $expected='rolled_back' }
        'commit-exit-error' { $privateCode=1 }
        'rollback-exit-zero' { $journal.state='rolled_back'; Copy-Item -LiteralPath $old -Destination (Join-Path $privateHome 'anchor.json') }
        'archive-drift' { $journal.archive_sha256=('b'*64) }
        'old-anchor-drift' { $journal.old_anchor_sha256=('b'*64) }
        'target-anchor-drift' { $journal.target_anchor_sha256=('b'*64) }
        'native-guard' { [IO.File]::WriteAllText((Join-Path $privateHome '.native-update.lock'),'synthetic retained guard') }
        'write-guard' { [IO.File]::WriteAllText((Join-Path $privateHome 'state/data/updates/.update.lock'),'synthetic retained guard') }
        'foreign-owner' { @{pid=$PID;attempt_id='foreign'} | ConvertTo-Json | Set-Content -LiteralPath $channelLock -Encoding utf8; $throws=$true }
        'malformed-journal' { $throws=$true }
        'current-anchor-drift' { [IO.File]::WriteAllText((Join-Path $privateHome 'anchor.json'),'{}') }
        'journal-schema' { $journal.schema=2 }
    }
    $journalPath = Join-Path $attempt 'result.json'
    if ($case -ne 'missing-journal') { $journal | ConvertTo-Json | Set-Content -LiteralPath $journalPath -Encoding utf8 }
    if ($case -eq 'malformed-journal') { [IO.File]::WriteAllText($journalPath,'NOT JSON') }
    $caught = $false
    try { . $body } catch { $caught = $true }
    if ($caught -ne $throws) { throw "Unexpected terminal exception behavior: $case" }
    if ($throws) {
        if ((Test-Path -LiteralPath $ResultPath) -or -not (Test-Path -LiteralPath $channelLock)) { throw "Unsafe result/foreign guard side effect: $case" }
    } else {
        $result = Get-Content -LiteralPath $ResultPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($result.state -ne $expected -or $result.verified -ne ($expected -eq 'committed') -or (Test-Path -LiteralPath $channelLock)) { throw "Wrong terminal result/cleanup: $case" }
    }
}
Write-Host 'PASS: fourteen synthetic actual-AST receipt/lock faults, NOT compiled-helper or native transaction acceptance'
