<#
.SYNOPSIS  Replace addons/Simulationcraft with a release of simulationcraft/simc-addon.
.PARAMETER Tag     Release tag (default: latest).
.PARAMETER OutDir  Destination folder (default: <repo>\addons\Simulationcraft).
#>
param(
  [string]$Tag,
  [string]$OutDir
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutDir) { $OutDir = Join-Path $root "addons\Simulationcraft" }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-TocVersion([string]$Dir) {
  $toc = Join-Path $Dir "Simulationcraft.toc"
  if (-not (Test-Path -LiteralPath $toc)) { return "(none)" }
  $m = Select-String -LiteralPath $toc -Pattern '^##\s*Version:\s*(.+)$' | Select-Object -First 1
  if ($m) { return $m.Matches[0].Groups[1].Value.Trim() }
  return "(unknown)"
}

$existing = Get-Item -LiteralPath $OutDir -Force -ErrorAction SilentlyContinue
if ($existing -and ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  throw "$OutDir is a link/junction; refusing to replace it."
}

$old = Get-TocVersion $OutDir
$api = "https://api.github.com/repos/simulationcraft/simc-addon/releases/" + $(if ($Tag) { "tags/$Tag" } else { "latest" })
$hdr = @{ "User-Agent" = "ToonOptimizer" }
$rel = Invoke-RestMethod -Uri $api -Headers $hdr
$asset = $rel.assets | Where-Object { $_.name -like "*.zip" -and $_.name -notlike "*nolib*" } | Select-Object -First 1
if (-not $asset) { throw "No packaged (with libs) .zip asset on release $($rel.tag_name); not using the source zipball." }

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("simc-addon-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  $zip = Join-Path $tmp "addon.zip"
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers $hdr -UseBasicParsing
  $ex = Join-Path $tmp "x"
  Expand-Archive -LiteralPath $zip -DestinationPath $ex
  $tocFile = Get-ChildItem -LiteralPath $ex -Recurse -Filter "Simulationcraft.toc" | Select-Object -First 1
  if (-not $tocFile) { throw "Simulationcraft.toc not found in $($asset.name)" }
  $src = $tocFile.Directory.FullName
  if (-not (Test-Path -LiteralPath (Join-Path $src "libs\LibStub"))) { throw "libs\LibStub missing in $($asset.name); refusing to replace $OutDir." }
  if ($existing) { Remove-Item -LiteralPath $OutDir -Recurse -Force }
  New-Item -ItemType Directory -Path (Split-Path -Parent $OutDir) -Force | Out-Null
  Copy-Item -LiteralPath $src -Destination $OutDir -Recurse
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
$new = Get-TocVersion $OutDir
Write-Host "Simulationcraft addon: $old -> $new ($($rel.tag_name), $($asset.name))"
Write-Host "Update the version in THIRD_PARTY.md if it changed."
