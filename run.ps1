<#
.SYNOPSIS  Start or stop ToonOptimizer.
.PARAMETER Build        Build the frontend and serve it from the backend only (no Vite dev server).
.PARAMETER NoBrowser    Don't open the browser.
.PARAMETER BackendPort  Port for the FastAPI/uvicorn backend (default 8790).
.PARAMETER FrontendPort Port for the Vite dev server (default 5173).
.PARAMETER Force        Start even if the target ports already look busy.
.PARAMETER Stop         Stop this app's processes on -BackendPort/-FrontendPort (default 8790/5173) and exit.
.PARAMETER All          With -Stop: also stop every ToonOptimizer uvicorn/vite/simc on ANY port
                        (including other sessions' and agents' test servers). Use with care.
#>
param(
  [switch]$Build,
  [switch]$NoBrowser,
  [int]$BackendPort = 8790,
  [int]$FrontendPort = 5173,
  [switch]$Force,
  [switch]$Stop,
  [switch]$All
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$simcDir = Join-Path $root "runtime\simc"

function Get-ListeningOwners([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $conns) { return @() }
  $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  $owners = @()
  foreach ($procId in $procIds) {
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    $owners += [PSCustomObject]@{
      Port        = $Port
      ProcessId   = $procId
      CommandLine = if ($cim) { $cim.CommandLine } else { "<unknown, process may have already exited>" }
    }
  }
  return $owners
}

function Stop-AppProcess {
  param([int]$ProcessId, [string]$Description, [hashtable]$Seen)
  if ($Seen.ContainsKey($ProcessId)) { return }
  $Seen[$ProcessId] = $true
  if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
  taskkill /T /F /PID $ProcessId 2>$null | Out-Null
  Write-Host "Stopped $Description (PID $ProcessId)"
}

function Invoke-Stop {
  $seen = @{}

  # PIDs holding either of our ports get killed regardless of command line, and give us a
  # backend-port allowlist for scoping the orphaned-reload-worker check below.
  $backendPortPids = @{}
  foreach ($port in @($BackendPort, $FrontendPort)) {
    foreach ($owner in (Get-ListeningOwners $port)) {
      if ($port -eq $BackendPort) { $backendPortPids[$owner.ProcessId] = $true }
      Stop-AppProcess -ProcessId $owner.ProcessId -Description "listener on port $port" -Seen $seen
    }
  }

  $allProcs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue

  # Without -All, only processes started for OUR two ports are touched, so agents' and other
  # sessions' test servers on other ports survive. Vite without --port defaults to 5173.
  foreach ($p in $allProcs) {
    if (-not $p.CommandLine) { continue }
    $portMatch = [regex]::Match($p.CommandLine, "--port[= ]+(\d+)")
    $cmdPort = if ($portMatch.Success) { [int]$portMatch.Groups[1].Value } else { $null }
    $portLabel = if ($cmdPort) { "$cmdPort" } else { "default port" }
    if ($p.Name -eq "node.exe" -and $p.CommandLine -match "vite\.js" -and $p.CommandLine -match [regex]::Escape($root)) {
      $vitePort = if ($cmdPort) { $cmdPort } else { 5173 }
      if ($All -or $vitePort -eq $FrontendPort) {
        Stop-AppProcess -ProcessId $p.ProcessId -Description "vite dev server on port $portLabel" -Seen $seen
      }
    }
    elseif ($p.CommandLine -match "uvicorn" -and $p.CommandLine -match "toonopt\.main:app") {
      if ($All -or $cmdPort -eq $BackendPort) {
        Stop-AppProcess -ProcessId $p.ProcessId -Description "uvicorn (toonopt.main:app) on port $portLabel" -Seen $seen
      }
    }
    elseif ($p.Name -eq "python.exe" -and $p.CommandLine -match "spawn_main") {
      $parentId = $p.ParentProcessId
      $parentAlive = $false
      if ($parentId) { $parentAlive = [bool](Get-Process -Id $parentId -ErrorAction SilentlyContinue) }
      $ownsBackendPort = $backendPortPids.ContainsKey($p.ProcessId)
      $isOurRepo = $p.CommandLine -match [regex]::Escape($root)
      if (-not $parentAlive -and ($ownsBackendPort -or ($All -and $isOurRepo))) {
        Stop-AppProcess -ProcessId $p.ProcessId -Description "orphaned reload worker" -Seen $seen
      }
    }
    elseif ($All -and $p.Name -eq "simc.exe" -and $p.CommandLine -match [regex]::Escape($simcDir)) {
      Stop-AppProcess -ProcessId $p.ProcessId -Description "simc.exe" -Seen $seen
    }
  }

  if ($seen.Count -eq 0) {
    Write-Host "Nothing to stop."
  }

  $deadline = (Get-Date).AddSeconds(5)
  $stillBusy = @()
  do {
    $stillBusy = @()
    foreach ($port in @($BackendPort, $FrontendPort)) {
      if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { $stillBusy += $port }
    }
    if ($stillBusy.Count -gt 0) { Start-Sleep -Milliseconds 250 }
  } while ($stillBusy.Count -gt 0 -and (Get-Date) -lt $deadline)

  if ($stillBusy.Count -gt 0) {
    Write-Host "Warning: still listening on port(s): $($stillBusy -join ', ')"
  } else {
    Write-Host "Ports $BackendPort and $FrontendPort are free."
  }
}

# Opens the browser from a background job once $HealthUrl answers, so the first page load
# doesn't hit a server that is still starting. Gives up waiting after 120s and opens anyway.
function Start-BrowserWhenReady([string]$HealthUrl, [string]$PageUrl) {
  Start-Job -ArgumentList $HealthUrl, $PageUrl -ScriptBlock {
    param($HealthUrl, $PageUrl)
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
      try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { break }
      } catch {}
      Start-Sleep -Milliseconds 500
    }
    Start-Process $PageUrl
  } | Out-Null
}

if ($Stop) {
  Invoke-Stop
  return
}

if (-not $Force) {
  $busy = @()
  foreach ($port in @($BackendPort, $FrontendPort)) { $busy += Get-ListeningOwners $port }
  if ($busy.Count -gt 0) {
    foreach ($b in $busy) {
      Write-Host "Port $($b.Port) is in use by PID $($b.ProcessId): $($b.CommandLine)"
    }
    Write-Host "Port $($busy[0].Port) is in use. Run .\run.ps1 -Stop first."
    exit 1
  }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found: https://docs.astral.sh/uv/" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm not found: install Node 20+" }

Push-Location $backend; uv sync --quiet; Pop-Location
if (-not (Test-Path (Join-Path $frontend "node_modules"))) { Push-Location $frontend; npm install; Pop-Location }

if ($BackendPort -ne 8790) {
  $env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"
} else {
  Remove-Item Env:\VITE_API_TARGET -ErrorAction SilentlyContinue
}

if ($Build) {
  Push-Location $frontend; npm run build; Pop-Location
  if (-not $NoBrowser) {
    Start-BrowserWhenReady "http://127.0.0.1:$BackendPort/api/health" "http://127.0.0.1:$BackendPort"
  }
  Push-Location $backend
  try { uv run uvicorn toonopt.main:app --host 127.0.0.1 --port $BackendPort } finally { Pop-Location }
} else {
  $api = Start-Process -PassThru -NoNewWindow -WorkingDirectory $backend -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "toonopt.main:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--reload", "--reload-dir", "src"
  try {
    # Polling /api/health through Vite's proxy waits for both Vite and the backend.
    if (-not $NoBrowser) {
      Start-BrowserWhenReady "http://localhost:$FrontendPort/api/health" "http://localhost:$FrontendPort"
    }
    Push-Location $frontend
    try { npm run dev -- --port $FrontendPort } finally { Pop-Location }
  } finally {
    if ($api -and -not $api.HasExited) {
      taskkill /T /F /PID $api.Id 2>$null | Out-Null
    }
  }
}
