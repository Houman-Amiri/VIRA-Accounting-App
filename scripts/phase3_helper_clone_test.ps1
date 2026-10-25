# Actual updater function AST, synthetic filesystem faults only.
# Opaque python.exe bytes are NEVER executed; NOT compiled/native acceptance.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true') { throw 'Disposable Windows CI only' }
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'scripts/vira_updater.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Actual updater failed parsing' }
foreach ($name in @('Get-Sha256','Assert-PrivatePythonClone')) {
    $functions = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true))
    if ($functions.Count -ne 1) { throw "Exactly one actual function required: $name" }
    . ([scriptblock]::Create($functions[0].Extent.Text))
}
$checks = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Assert-PrivatePythonClone'},$true))
$invocations = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst] -and $n.CommandElements[-1].Extent.Text -eq '@privateArgs'},$true))
if ($checks.Count -ne 1 -or $invocations.Count -ne 1 -or $checks[0].Extent.EndOffset -ge $invocations[0].Extent.StartOffset) { throw 'Actual clone must be verified before interpreter execution' }
$work = Join-Path $env:RUNNER_TEMP ('phase3-clone-synthetic-' + [guid]::NewGuid().ToString('N'))
$cases = @('valid','truncated','same-size-corrupt','missing','extra-hidden','duplicate-case','escaped','missing-executable','directory-junction','root-junction','nested-corrupt','source-mutated-after-copy')
foreach ($case in $cases) {
    $base = Join-Path $work $case
    $original = Join-Path $base 'original'
    $runtime = Join-Path $base 'clone فارسی ! &'
    New-Item -ItemType Directory -Force (Join-Path $original 'DLLs') | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $original 'python.exe'),[Text.Encoding]::UTF8.GetBytes('OPAQUE NOT AN INTERPRETER'))
    [IO.File]::WriteAllBytes((Join-Path $original 'python311.zip'),[Text.Encoding]::UTF8.GetBytes('OPAQUE NOT A STDLIB'))
    [IO.File]::WriteAllBytes((Join-Path $original 'DLLs/opaque.pyd'),[Text.Encoding]::UTF8.GetBytes('OPAQUE NOT A DLL'))
    $files = @(Get-ChildItem -LiteralPath $original -Recurse -File | ForEach-Object {
        @{path=('python/' + [IO.Path]::GetRelativePath($original,$_.FullName).Replace('\','/'));size=$_.Length;sha256=(Get-Sha256 $_.FullName)}
    })
    # Non-Python anchored files must not be included in this subtree comparison.
    $files += @{path='backend/not-copied.py';size=1;sha256=('a'*64)}
    Copy-Item -LiteralPath $original -Destination $runtime -Recurse
    $expectedSuccess = $case -in @('valid','source-mutated-after-copy')
    switch ($case) {
        'truncated' { [IO.File]::WriteAllText((Join-Path $runtime 'python.exe'),'X') }
        'same-size-corrupt' {
            $p = Join-Path $runtime 'python.exe'
            $bytes = [IO.File]::ReadAllBytes($p); $bytes[0] = $bytes[0] -bxor 1
            [IO.File]::WriteAllBytes($p,$bytes)
        }
        'missing' { Remove-Item -LiteralPath (Join-Path $runtime 'python311.zip') }
        'extra-hidden' {
            $p = Join-Path $runtime 'extra.txt'; [IO.File]::WriteAllText($p,'UNANCHORED')
            [IO.File]::SetAttributes($p,[IO.FileAttributes]::Hidden)
        }
        'duplicate-case' { $files += @{path='python/PYTHON.EXE';size=$files[0].size;sha256=$files[0].sha256} }
        'escaped' { $files += @{path='python/../outside';size=1;sha256=('a'*64)} }
        'missing-executable' { $files = @($files | Where-Object { $_.path -cne 'python/python.exe' }) }
        'directory-junction' {
            New-Item -ItemType Junction -Path (Join-Path $runtime 'alias') -Target $original | Out-Null
        }
        'root-junction' {
            # Keep the fresh actual clone; point a separate root alias at it.
            $link = Join-Path $base 'root-alias'
            New-Item -ItemType Junction -Path $link -Target $runtime | Out-Null
            $runtime = $link
        }
        'nested-corrupt' { [IO.File]::WriteAllText((Join-Path $runtime 'DLLs/opaque.pyd'),'BAD') }
        'source-mutated-after-copy' { [IO.File]::WriteAllText((Join-Path $original 'python.exe'),'SOURCE CHANGED AFTER COPY') }
    }
    $succeeded = $true
    try { Assert-PrivatePythonClone $runtime $files } catch { $succeeded = $false }
    if ($succeeded -ne $expectedSuccess) { throw "Actual clone verifier fault behavior: $case" }
}
Write-Host 'PASS: twelve synthetic actual-AST Python clone controls; NOT executable/native acceptance'
