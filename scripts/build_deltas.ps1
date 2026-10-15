# build_deltas.ps1 — delta update packages vs the last K release tags (Phase 8 §5)
#
# For each previous release base (K = 3):
#   - downloads that release's portable zip (base files) from GitHub Release assets
#   - diffs its install_manifest.json against the new build
#   - writes VIRA-v<target>-delta-from-v<base>.zip (update.json + files/ + patches/ + delete.json)
# Then rewrites latest.json with the deltas[] array and SHA256SUMS.txt.
#
# A base without a downloadable artifact is skipped (its users get the full
# installer fallback — never a corrupt delta).

param(
    [Parameter(Mandatory = $true)][string]$Version,   # vX.Y.Z or X.Y.Z
    [Parameter(Mandatory = $true)][string]$OutDir,    # dist-release (contains the new build + latest.json)
    [string]$AppDir = "",                             # new build dir (default: $OutDir\app)
    [int]$Keep = 3
)

$ErrorActionPreference = "Stop"
$v = $Version.TrimStart("v")
if (-not $AppDir) { $AppDir = Join-Path $OutDir "app" }
if (-not (Test-Path $AppDir)) { Write-Host "[build_deltas] no app dir at $AppDir — nothing to diff"; exit 0 }

$repo = $env:GITHUB_REPOSITORY
if (-not $repo) { $repo = "Houman-Amiri/VIRA-Accounting-App" }

# probe the known historical portable-asset names (public assets need no auth)
function Find-PortableUrl([string]$Repo, [string]$Tag, [string]$BaseV) {
    foreach ($name in @("vira-v$BaseV-portable.zip", "VIRA-v$BaseV.zip", "VIRA-v$BaseV-portable.zip")) {
        $url = "https://github.com/$Repo/releases/download/$Tag/$name"
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Head -SkipHttpErrorCheck -MaximumRedirection 5 -TimeoutSec 30
            $code = [int]$resp.StatusCode
        } catch { $code = 0; $msg = ("" + $_.Exception.Message -replace "[`r`n]", " ") }
        $script:probeLog += "$Tag/$name=HTTP$code"
        if ($code -in 200, 302) { return $url }
    }
    return $null
}

$tags = git tag --list "v*" --sort=-v:refname | Select-Object -First $Keep
$deltas = @()
$script:probeLog = @()
$probeHit = $false
$tmp = Join-Path ([IO.Path]::GetTempPath()) "vira-delta-base"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

foreach ($tag in $tags) {
    $baseV = $tag.TrimStart("v")
    if ($baseV -eq $v) { continue }
    $baseZip = Join-Path $tmp "base-$baseV.zip"
    Write-Host ("::notice title=build_deltas::tag $tag (v=$v) — probing portable asset")
    $zipUrl = Find-PortableUrl $repo $tag $baseV
    if ($zipUrl) { $probeHit = $true }
    if (-not $zipUrl) {
        Write-Host "[build_deltas] base $tag has no downloadable portable zip — skipping (full-installer fallback covers it)"
        Write-Host ("::notice title=build_deltas::$tag SKIP — no portable asset discovered")
        continue
    }
    try {
        Write-Host "[build_deltas] fetching base $zipUrl"
        Invoke-WebRequest -Uri $zipUrl -OutFile $baseZip -MaximumRetryCount 2 | Out-Null
    }
    catch {
        Write-Host "[build_deltas] base $tag not downloadable — skipping (full-installer fallback covers it)"
        Write-Host ("::notice title=build_deltas::$tag SKIP — download failed: " + ($_.Exception.Message -replace "`n", " "))
        continue
    }
    $baseDir = Join-Path $tmp "base-$baseV"
    if (Test-Path $baseDir) { Remove-Item $baseDir -Recurse -Force }
    Expand-Archive -Path $baseZip -DestinationPath $baseDir -Force
    $baseManifest = Get-ChildItem $baseDir -Recurse -Filter install_manifest.json | Select-Object -First 1
    if (-not $baseManifest) {
        Write-Host "[build_deltas] base $tag has no install_manifest.json — skipping"
        continue
    }
    $out = & uv run python scripts/gen_delta.py `
        --base-manifest $baseManifest.FullName `
        --base-dir $baseManifest.Directory.FullName `
        --target-dir $AppDir `
        --base-version $baseV `
        --target-version $v `
        --out $OutDir
    Write-Host ($out -join "`n")
    $zipName = "VIRA-v$v-delta-from-v$baseV.zip"
    $zipPath = Join-Path $OutDir $zipName
    if (Test-Path $zipPath) {
        Write-Host ("::notice title=build_deltas::$zipName BUILT ($((Get-Item $zipPath).Length) bytes)")
        $hash = (Get-FileHash -Algorithm SHA256 $zipPath).Hash.ToLower()
        $deltas += @{ from_version = $baseV; url = "https://github.com/$repo/releases/download/v$v/$zipName"; sha256 = $hash; size = (Get-Item $zipPath).Length }
    } else {
        Write-Host ("::notice title=build_deltas::$zipName MISSING after gen_delta — output: " + (($out | Out-String) -replace "`n", " | "))
    }
}
Write-Host ("[build_deltas] probe log: " + ($script:probeLog -join "; "))
Write-Host ("::notice title=build_deltas::done — $($deltas.Count) delta(s) from tags: $($tags -join ', ')")
if ($deltas.Count -eq 0 -and $probeHit) {
    throw "a portable base exists but 0 deltas were built — probe log: $($script:probeLog -join '; ')"
}

# ------------------------------------------------------ rewrite latest.json ---
$latestPath = Join-Path $OutDir "latest.json"
if (Test-Path $latestPath) {
    $latest = Get-Content $latestPath -Raw -Encoding utf8 | ConvertFrom-Json
    # finalize full_installer now that the Inno setup may exist
    $setup = Get-ChildItem $OutDir -Filter "VIRA-Setup-*.exe" | Select-Object -First 1
    if ($setup) {
        $latest.full_installer = [ordered]@{
            url  = "https://github.com/$repo/releases/download/v$v/$($setup.Name)"
            sha256 = (Get-FileHash -Algorithm SHA256 $setup.FullName).Hash.ToLower()
            size = $setup.Length
        }
    }
    $latest.deltas = @($deltas | ForEach-Object {
        [ordered]@{ from_version = $_.from_version; url = $_.url; sha256 = $_.sha256; size = $_.size }
    })
    ($latest | ConvertTo-Json -Depth 8) | Set-Content -Encoding utf8 $latestPath
    Write-Host "[build_deltas] latest.json updated with $($deltas.Count) delta(s)"
}

# -------------------------------------------------------------- SHA256SUMS ---
$assets = Get-ChildItem $OutDir -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" }
$sums = foreach ($a in $assets) {
    $h = Get-FileHash -Algorithm SHA256 $a.FullName
    "{0}  {1}" -f $h.Hash.ToLower(), $a.Name
}
$sums | Set-Content -Encoding ascii (Join-Path $OutDir "SHA256SUMS.txt")

# ----------------------------------------------- sign latest.json (Ed25519) ---
if ($env:VIRA_UPDATE_SIGNING_KEY) {
    $keyPath = Join-Path $tmp "update.key"
    Set-Content -Path $keyPath -Value $env:VIRA_UPDATE_SIGNING_KEY -Encoding ascii
    & uv run python scripts/sign_update.py sign --key $keyPath --file $latestPath
}
