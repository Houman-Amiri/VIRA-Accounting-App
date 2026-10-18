# Application QA only; not a native-build MIT sidecar derivative or release entry.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$Reference,
    [Parameter(Mandatory = $true)][string]$NativeProof
)
$ErrorActionPreference = "Stop"
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne "true") { throw "Private isolated Windows CI only" }
$candidate = Join-Path $env:RUNNER_TEMP "local-source-consumer-candidate"
uv run python scripts/prepare_pdf_consumer_candidate.py --work $WorkDir --reference $Reference --native-proof $NativeProof --out $candidate
if ($LASTEXITCODE -ne 0) { throw "local build to private consumer handoff failed" }
$previous = $env:VIRA_PDF_SOURCE_CANDIDATE
$expected = $env:VIRA_PDF_EXPECT_PANGO_VERSION
try {
    $env:VIRA_PDF_SOURCE_CANDIDATE = $candidate
    $env:VIRA_PDF_EXPECT_PANGO_VERSION = "1.58.0-vira-local-source"
    & ./scripts/pdf_payload_smoke.ps1
    if ($LASTEXITCODE -ne 0) { throw "relocated private payload PDF proof failed" }
} finally {
    $env:VIRA_PDF_SOURCE_CANDIDATE = $previous
    $env:VIRA_PDF_EXPECT_PANGO_VERSION = $expected
}
