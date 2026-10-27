# install_ps2exe.ps1 — compile vira-updater.exe in CI without a flaky single shot.
#
# PSGallery intermittently refuses downloads. A transient mirror error must not
# be reported as a broken build, and a real outage must still fail the job.
param([int]$Attempts = 3)

$ErrorActionPreference = "Stop"
if ($Attempts -lt 1) { throw "at least one real attempt is required" }
$last = $null
for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    try {
        if (-not (Get-Module -ListAvailable -Name ps2exe)) {
            Install-Module ps2exe -Force -Scope CurrentUser -ErrorAction Stop
        }
        Import-Module ps2exe -ErrorAction Stop
        Write-Host "[ps2exe] ready after attempt $attempt"
        $global:LASTEXITCODE = 0
        return
    } catch {
        $last = $_
        Write-Warning "[ps2exe] attempt $attempt failed: $($_.Exception.Message)"
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds (15 * $attempt) }
    }
}
throw "ps2exe could not be installed after $Attempts real attempts: $($last.Exception.Message)"
