<#
.SYNOPSIS  Install the companion addons from addons\ into the WoW AddOns folder.
.PARAMETER WowDir  WoW root (the folder containing _retail_). Auto-detected if omitted.
.PARAMETER Link    Create junctions to the repo folders instead of copying.
.PARAMETER Force   Also replace a Simulationcraft install that is as new as the vendored one.
.PARAMETER Only    Install only these addon names.
#>
param(
  [string]$WowDir,
  [switch]$Link,
  [switch]$Force,
  [string[]]$Only
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$srcRoot = Join-Path $root "addons"

function Test-WowDir([string]$Dir) {
  return [bool]($Dir -and (Test-Path -LiteralPath (Join-Path $Dir "_retail_")))
}

function Resolve-WowDir {
  if ($WowDir) { return $WowDir }
  $cands = @()
  $settings = Join-Path $root "data\settings.json"
  if (Test-Path $settings) {
    try { $cands += (Get-Content $settings -Raw | ConvertFrom-Json).wow_dir } catch {}
  }
  $cands += $env:WOW_DIR
  try {
    $p = (Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft" -ErrorAction Stop).InstallPath
    if ($p) { $cands += ($p.TrimEnd('\', '/') -replace '[\\/]_retail_$', '') }
  } catch {}
  $cands += "C:\Program Files (x86)\World of Warcraft", "C:\Games\World of Warcraft"
  foreach ($c in $cands) { if (Test-WowDir $c) { return $c } }
  throw "WoW folder not found. Pass -WowDir <folder containing _retail_>."
}

function Get-TocVersion([string]$Dir, [string]$Name) {
  $toc = Join-Path $Dir "$Name.toc"
  if (-not (Test-Path -LiteralPath $toc)) { return $null }
  $m = Select-String -LiteralPath $toc -Pattern '^##\s*Version:\s*(.+)$' | Select-Object -First 1
  if ($m) { return $m.Matches[0].Groups[1].Value.Trim() }
  return $null
}

# "12.1.0-03" -> comparable [version]; unparsable -> 0.0
function ConvertTo-Ver([string]$s) {
  if ($s -and $s -match '(\d+(?:\.\d+){0,3})(?:[-.](\d+))?') {
    $t = $Matches[1]
    if ($Matches[2]) { $t += ".$($Matches[2])" }
    $parts = @($t.Split('.') | Select-Object -First 4)
    while ($parts.Count -lt 2) { $parts += "0" }
    try { return [version]($parts -join '.') } catch {}
  }
  return [version]"0.0"
}

function Test-Junction([string]$Path) {
  $i = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
  return [bool]($i -and ($i.Attributes -band [IO.FileAttributes]::ReparsePoint))
}

$wow = Resolve-WowDir
$addons = Join-Path $wow "_retail_\Interface\AddOns"
if (-not (Test-Path -LiteralPath $addons)) { New-Item -ItemType Directory -Path $addons -Force | Out-Null }
Write-Host "WoW: $wow"

if (Get-Process -Name "Wow", "WowB", "WowT" -ErrorAction SilentlyContinue) {
  Write-Warning "WoW is running. A newly added addon needs a full client restart (/reload is not enough)."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $root "runtime\addon-backups\$stamp"
$summary = @()

foreach ($dir in Get-ChildItem -LiteralPath $srcRoot -Directory) {
  $name = $dir.Name
  if ($Only -and ($Only -notcontains $name)) { continue }
  $target = Join-Path $addons $name
  $status = $null

  # Get-Item -Force also finds dangling junctions, which Test-Path reports as missing.
  if (Get-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue) {
    if (Test-Junction $target) {
      (Get-Item -LiteralPath $target -Force).Delete()   # removes the link only
    } else {
      if ($name -eq "Simulationcraft" -and -not $Force) {
        $inst = Get-TocVersion $target $name
        $vend = Get-TocVersion $dir.FullName $name
        if ((ConvertTo-Ver $inst) -ge (ConvertTo-Ver $vend)) {
          $summary += [pscustomobject]@{ Addon = $name; Result = "skipped (installed $inst >= vendored $vend; use -Force)" }
          continue
        }
      }
      New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
      # Copy + verify + delete: Move-Item fails across volumes in Windows PowerShell 5.1.
      $bak = Join-Path $backupRoot $name
      Copy-Item -LiteralPath $target -Destination $bak -Recurse
      if (-not (Test-Path -LiteralPath $bak)) { throw "Backup of $target failed; not replacing it." }
      Remove-Item -LiteralPath $target -Recurse -Force
      $status = "backed up to runtime\addon-backups\$stamp\$name"
    }
  }

  if ($Link) {
    New-Item -ItemType Junction -Path $target -Target $dir.FullName | Out-Null
    $how = "linked"
  } else {
    Copy-Item -LiteralPath $dir.FullName -Destination $target -Recurse
    $how = "copied"
  }
  $summary += [pscustomobject]@{ Addon = $name; Result = $(if ($status) { "$how; $status" } else { $how }) }
}

if (-not $summary) { Write-Warning "No addons matched." }
$summary | ForEach-Object { Write-Host ("  {0,-16} {1}" -f $_.Addon, $_.Result) }
Write-Host "In game: log in, /reload or log out once so ToonOptimizer can read your character."
