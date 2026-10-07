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

function ConvertTo-WowRoot([string]$Dir) {
  if (-not $Dir) { return $null }
  $d = $Dir.Trim().Trim('"', "'").Trim().TrimEnd('\', '/')
  if (-not $d) { return $null }
  # Anything at or below a _retail_ folder (e.g. ...\_retail_\Wow.exe) -> its parent is the root.
  if ($d -match '^(.*?)[\\/]_retail_(?:[\\/].*)?$') { return $Matches[1].TrimEnd('\', '/') }
  if ($d -ieq '_retail_') { return $null }
  try { if (Test-Path -LiteralPath $d -PathType Leaf) { $d = Split-Path -Parent $d } } catch {}
  return $d
}

function Test-WowDir([string]$Dir) {
  if (-not $Dir) { return $false }
  try { return [bool](Test-Path -LiteralPath (Join-Path $Dir "_retail_") -PathType Container) } catch { return $false }
}

# Returns @{ Path; Source }. Priority matches backend/src/toonopt/config.py.
function Resolve-WowDir {
  if ($WowDir) {
    $n = ConvertTo-WowRoot $WowDir
    if (-not (Test-WowDir $n)) {
      throw "-WowDir '$WowDir' does not contain a _retail_ folder. Pass the folder that contains _retail_."
    }
    return @{ Path = $n; Source = "-WowDir" }
  }

  $settings = Join-Path $root "data\settings.json"
  if (Test-Path -LiteralPath $settings) {
    try {
      $n = ConvertTo-WowRoot ((Get-Content -LiteralPath $settings -Raw | ConvertFrom-Json).wow_dir)
      if (Test-WowDir $n) { return @{ Path = $n; Source = "data/settings.json" } }
    } catch {}
  }

  $n = ConvertTo-WowRoot $env:WOW_DIR
  if (Test-WowDir $n) { return @{ Path = $n; Source = "WOW_DIR environment variable" } }

  $regKeys = @(
    @("HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft", "InstallPath"),
    @("HKLM:\SOFTWARE\Blizzard Entertainment\World of Warcraft", "InstallPath"),
    @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\World of Warcraft", "InstallLocation")
  )
  foreach ($k in $regKeys) {
    try {
      $v = (Get-ItemProperty -LiteralPath $k[0] -Name $k[1] -ErrorAction Stop).($k[1])
      $n = ConvertTo-WowRoot $v
      if (Test-WowDir $n) { return @{ Path = $n; Source = "registry" } }
    } catch {}
  }

  $subs = "World of Warcraft", "Games\World of Warcraft", "Program Files (x86)\World of Warcraft",
          "Program Files\World of Warcraft", "Blizzard\World of Warcraft", "Battle.net\World of Warcraft"
  $drives = @()
  try { $drives = [IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'Fixed' -and $_.IsReady } } catch {}
  foreach ($dr in $drives) {
    foreach ($s in $subs) {
      $c = Join-Path $dr.RootDirectory.FullName $s
      if (Test-WowDir $c) { return @{ Path = $c; Source = "drive scan" } }
    }
  }

  throw ("WoW folder not found. Pass -WowDir ""<folder that contains _retail_>"" " +
         "or set it in the app's Settings -> WoW directory.")
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

$found = Resolve-WowDir
$wow = $found.Path
$addons = Join-Path $wow "_retail_\Interface\AddOns"
if (-not (Test-Path -LiteralPath $addons)) { New-Item -ItemType Directory -Path $addons -Force | Out-Null }
Write-Host "WoW: $wow (from $($found.Source))"
if ($WowDir) {
  $saved = $null
  $sf = Join-Path $root "data\settings.json"
  if (Test-Path -LiteralPath $sf) { try { $saved = ConvertTo-WowRoot (Get-Content -LiteralPath $sf -Raw | ConvertFrom-Json).wow_dir } catch {} }
  if ($saved -ne $wow) { Write-Host "Tip: also set this in the app under Settings -> WoW directory so the backend uses the same folder." }
}

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
