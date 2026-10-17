# Test-only native DLL fixture. NEVER copied into a release/install payload.
# Upstream's pinned onedir binary supplies Pango without installing system GTK.
# Distribution notices/corresponding-source compliance is a separate open gate.
$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true") { throw "isolated GitHub Actions runner required" }

$root = Join-Path $env:RUNNER_TEMP ("vira-pdf-proof-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $root | Out-Null
$archive = Join-Path $root "weasyprint-windows-onedir.zip"
$url = "https://github.com/Kozea/WeasyPrint/releases/download/v70.0/weasyprint-windows-onedir.zip"
Invoke-WebRequest -Uri $url -OutFile $archive
$expected = "ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53"
if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant() -ne $expected) {
    throw "official WeasyPrint 70.0 fixture SHA256 mismatch"
}
Expand-Archive -Path $archive -DestinationPath (Join-Path $root "upstream")
$dlls = @(Get-ChildItem (Join-Path $root "upstream") -Recurse -Filter "libpango-1.0-0.dll")
if ($dlls.Count -ne 1) { throw "expected exactly one upstream Pango DLL" }
$dllDir = $dlls[0].Directory.FullName
foreach ($name in @("libpangoft2-1.0-0.dll", "libgobject-2.0-0.dll", "libharfbuzz-0.dll", "libfontconfig-1.dll")) {
    if (-not (Test-Path (Join-Path $dllDir $name))) { throw "upstream fixture lacks $name" }
}

# Exercise actual app resources from a path containing spaces AND Persian.
$appRoot = Join-Path $root "VIRA چاپ بومی"
New-Item -ItemType Directory -Path $appRoot | Out-Null
Copy-Item -Recurse backend/app (Join-Path $appRoot "app")
# No system fonts: only @font-face can supply glyphs. Keep all caches disposable.
$emptyFonts = Join-Path $root "empty-fonts"
$cache = Join-Path $root "font-cache"
New-Item -ItemType Directory -Path $emptyFonts, $cache | Out-Null
$fontConfig = Join-Path $root "fonts.conf"
$escapedEmpty = [System.Security.SecurityElement]::Escape($emptyFonts.Replace('\', '/'))
$escapedCache = [System.Security.SecurityElement]::Escape($cache.Replace('\', '/'))
"<fontconfig><dir>$escapedEmpty</dir><cachedir>$escapedCache</cachedir></fontconfig>" | Set-Content -Encoding utf8 $fontConfig
@(
    "WEASYPRINT_DLL_DIRECTORIES=$dllDir"
    "FONTCONFIG_FILE=$fontConfig"
    "FONTCONFIG_PATH=$root"
    "VIRA_PDF_PROOF_APP_ROOT=$appRoot"
    "VIRA_PDF_UPSTREAM_ARCHIVE=$archive"
) | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
Write-Host "Native fixture: upstream WeasyPrint v70.0, verified SHA256 $expected"
Write-Host "DLLs: $dllDir; app: $appRoot; system fonts excluded"
